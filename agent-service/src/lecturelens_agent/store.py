"""A bounded, disposable vector projection; Java remains the evidence authority."""

import json

import psycopg

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS retrieval_snapshot (
    snapshot_id text PRIMARY KEY,
    owner_id bigint NOT NULL,
    course_id text NOT NULL,
    revision bigint NOT NULL,
    index_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS retrieval_snapshot_expiry ON retrieval_snapshot(created_at);
CREATE TABLE IF NOT EXISTS retrieval_vector (
    snapshot_id text NOT NULL REFERENCES retrieval_snapshot(snapshot_id) ON DELETE CASCADE,
    chunk_id integer NOT NULL,
    evidence_id text NOT NULL,
    start_ms bigint NOT NULL,
    end_ms bigint NOT NULL,
    embedding vector NOT NULL,
    PRIMARY KEY(snapshot_id, chunk_id)
);
"""


class VectorStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def connect(self):
        return psycopg.connect(self.dsn, connect_timeout=5, options="-c statement_timeout=15000")

    def initialize(self):
        with self.connect() as conn:
            conn.execute(SCHEMA)

    def contains(self, snapshot_id):
        with self.connect() as conn:
            # Logical expiry is absolute; physical removal is swept on the next retrieval request.
            conn.execute("DELETE FROM retrieval_snapshot WHERE created_at < now() - interval '24 hours'")
            return (
                conn.execute(
                    "SELECT 1 FROM retrieval_snapshot WHERE snapshot_id=%s", (snapshot_id,)
                ).fetchone()
                is not None
            )

    def save(self, snapshot_id, request, index_version, chunks, vectors):
        # Embedding is complete before opening this short publication transaction.
        with self.connect() as conn:
            inserted = conn.execute(
                """INSERT INTO retrieval_snapshot(snapshot_id,owner_id,course_id,revision,index_version)
                   VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING snapshot_id""",
                (snapshot_id, request.owner_id, request.course_id, request.revision, index_version),
            ).fetchone()
            if inserted:
                with conn.cursor() as cur:
                    cur.executemany(
                        """INSERT INTO retrieval_vector
                           (snapshot_id,chunk_id,evidence_id,start_ms,end_ms,embedding)
                           VALUES (%s,%s,%s,%s,%s,%s::vector)""",
                        [
                            (
                                snapshot_id,
                                i,
                                chunk[0].evidence_id,
                                chunk[0].start_ms,
                                chunk[0].end_ms,
                                json.dumps(vector),
                            )
                            for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
                        ],
                    )

    def search(self, snapshot_id, request, index_version, vector):
        window = request.time_window
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT v.evidence_id, max(1 - (v.embedding <=> %s::vector)) AS score
                   FROM retrieval_vector v JOIN retrieval_snapshot s USING(snapshot_id)
                   WHERE s.snapshot_id=%s AND s.owner_id=%s AND s.course_id=%s
                     AND s.revision=%s AND s.index_version=%s
                     AND s.created_at >= now() - interval '24 hours'
                     AND v.start_ms <= %s AND v.end_ms >= %s
                   GROUP BY v.evidence_id ORDER BY score DESC, v.evidence_id LIMIT %s""",
                (
                    json.dumps(vector),
                    snapshot_id,
                    request.owner_id,
                    request.course_id,
                    request.revision,
                    index_version,
                    window.end_ms if window else 9223372036854775807,
                    window.start_ms if window else 0,
                    request.top_k,
                ),
            ).fetchall()
            return [{"evidence_id": row[0], "score": row[1]} for row in rows]
