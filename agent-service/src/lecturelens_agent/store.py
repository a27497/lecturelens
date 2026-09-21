"""Durable, version-fenced vector projection. No source text is persisted."""

import hashlib
import json

import psycopg

# Additive v2 schema; remove the disposable v1 cache once at migration time.
SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS retrieval_schema_version (version integer PRIMARY KEY);
CREATE TABLE IF NOT EXISTS evidence_index (
    owner_id bigint NOT NULL, course_id text NOT NULL,
    sequence bigint NOT NULL, revision bigint NOT NULL,
    index_version text NOT NULL, state text NOT NULL,
    snapshot_id text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(owner_id, course_id)
);
CREATE TABLE IF NOT EXISTS indexed_evidence (
    owner_id bigint NOT NULL, course_id text NOT NULL, evidence_id text NOT NULL,
    content_hash text NOT NULL, start_ms bigint NOT NULL, end_ms bigint NOT NULL,
    PRIMARY KEY(owner_id, course_id, evidence_id),
    FOREIGN KEY(owner_id, course_id) REFERENCES evidence_index ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS evidence_vector (
    owner_id bigint NOT NULL, course_id text NOT NULL, evidence_id text NOT NULL,
    chunk_id integer NOT NULL, chunk_hash text NOT NULL, embedding vector NOT NULL,
    PRIMARY KEY(owner_id, course_id, evidence_id, chunk_id),
    FOREIGN KEY(owner_id, course_id, evidence_id) REFERENCES indexed_evidence ON DELETE CASCADE
);
"""


class StaleSync(Exception):
    pass


class VectorStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def connect(self):
        return psycopg.connect(self.dsn, connect_timeout=5, options="-c statement_timeout=15000")

    def initialize(self):
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(7812249)")
            conn.execute(SCHEMA)
            if conn.execute(
                "INSERT INTO retrieval_schema_version VALUES (2) ON CONFLICT DO NOTHING RETURNING version"
            ).fetchone():
                conn.execute("DROP TABLE IF EXISTS retrieval_vector; DROP TABLE IF EXISTS retrieval_snapshot")

    def _head(self, conn, request, version):
        conn.execute(
            """INSERT INTO evidence_index VALUES (%s,%s,-1,0,%s,'PENDING','',now())
               ON CONFLICT DO NOTHING""",
            (request.owner_id, request.course_id, version),
        )
        row = conn.execute(
            """SELECT sequence,revision,index_version,state,snapshot_id FROM evidence_index
               WHERE owner_id=%s AND course_id=%s FOR UPDATE""",
            (request.owner_id, request.course_id),
        ).fetchone()
        if request.sequence < row[0] or (row[3] == "DELETED" and request.operation != "DELETE"):
            raise StaleSync("Obsolete sync")
        if request.sequence == row[0] and request.revision != row[1] and request.operation != "DELETE":
            raise StaleSync("Conflicting revision")
        return row

    @staticmethod
    def _response(request, version, state, missing=()):
        return dict(
            request_id=request.request_id,
            owner_id=request.owner_id,
            course_id=request.course_id,
            revision=request.revision,
            sequence=request.sequence,
            index_version=version,
            state=state,
            missing_ids=list(missing),
        )

    def plan(self, request, version):
        with self.connect() as conn:
            head = self._head(conn, request, version)
            ids = set()
            known_hashes = set()
            if head[2] == version:
                ids = {
                    r[0]
                    for r in conn.execute(
                        "SELECT evidence_id FROM indexed_evidence WHERE owner_id=%s AND course_id=%s",
                        (request.owner_id, request.course_id),
                    )
                }
                known_hashes = {
                    r[0]
                    for r in conn.execute(
                        "SELECT content_hash FROM indexed_evidence WHERE owner_id=%s AND course_id=%s",
                        (request.owner_id, request.course_id),
                    )
                }
            metadata = (
                {
                    r[0]: tuple(r[1:])
                    for r in conn.execute(
                        "SELECT evidence_id,content_hash,start_ms,end_ms FROM indexed_evidence WHERE owner_id=%s AND course_id=%s",
                        (request.owner_id, request.course_id),
                    )
                }
                if head[2] == version
                else {}
            )
            if any(
                item.evidence_id in metadata
                and metadata[item.evidence_id] != (item.content_hash, item.start_ms, item.end_ms)
                for item in request.manifest
            ):
                raise ValueError("Immutable manifest conflict")
            ready = (
                head[0] == request.sequence
                and head[1] == request.revision
                and head[2] == version
                and head[3] == "READY"
                and ids == set(request.evidence_ids)
            )
            return self._response(
                request,
                version,
                "READY" if ready else "PENDING",
                sorted(
                    item.evidence_id
                    for item in request.manifest
                    if item.evidence_id not in ids and item.content_hash not in known_hashes
                ),
            )

    def reusable_vectors(self, request, version, hashes):
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT v.chunk_hash,v.embedding::text FROM evidence_vector v JOIN evidence_index i
                   USING(owner_id,course_id) WHERE owner_id=%s AND course_id=%s
                   AND i.index_version=%s AND i.state <> 'DELETED' AND v.chunk_hash=ANY(%s)""",
                (request.owner_id, request.course_id, version, hashes),
            ).fetchall()
            return {key: json.loads(vector) for key, vector in rows}

    def apply(self, request, version, chunks, hashes, vectors):
        with self.connect() as conn:
            head = self._head(conn, request, version)
            if head[2] != version:
                conn.execute(
                    "DELETE FROM indexed_evidence WHERE owner_id=%s AND course_id=%s",
                    (request.owner_id, request.course_id),
                )
            # New revisions have new evidence IDs. Copy vectors by content hash before deleting
            # the old manifest, so unchanged text need not cross the network again.
            for item in request.manifest:
                prior = conn.execute(
                    """SELECT content_hash,start_ms,end_ms FROM indexed_evidence
                    WHERE owner_id=%s AND course_id=%s AND evidence_id=%s""",
                    (request.owner_id, request.course_id, item.evidence_id),
                ).fetchone()
                if prior:
                    if prior != (item.content_hash, item.start_ms, item.end_ms):
                        raise ValueError("Immutable manifest conflict")
                    continue
                source = conn.execute(
                    """SELECT evidence_id FROM indexed_evidence
                    WHERE owner_id=%s AND course_id=%s AND content_hash=%s LIMIT 1""",
                    (request.owner_id, request.course_id, item.content_hash),
                ).fetchone()
                if source:
                    conn.execute(
                        "INSERT INTO indexed_evidence VALUES (%s,%s,%s,%s,%s,%s)",
                        (
                            request.owner_id,
                            request.course_id,
                            item.evidence_id,
                            item.content_hash,
                            item.start_ms,
                            item.end_ms,
                        ),
                    )
                    conn.execute(
                        """INSERT INTO evidence_vector
                        SELECT owner_id,course_id,%s,chunk_id,chunk_hash,embedding FROM evidence_vector
                        WHERE owner_id=%s AND course_id=%s AND evidence_id=%s""",
                        (item.evidence_id, request.owner_id, request.course_id, source[0]),
                    )
            for item in request.upserts:
                fingerprint = hashlib.sha256(item.text.encode()).hexdigest()
                prior = conn.execute(
                    """SELECT content_hash,start_ms,end_ms FROM indexed_evidence
                       WHERE owner_id=%s AND course_id=%s AND evidence_id=%s""",
                    (request.owner_id, request.course_id, item.evidence_id),
                ).fetchone()
                if prior is not None:
                    if prior != (fingerprint, item.start_ms, item.end_ms):
                        raise ValueError("Immutable evidence conflict")
                    continue
                conn.execute(
                    "INSERT INTO indexed_evidence VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        request.owner_id,
                        request.course_id,
                        item.evidence_id,
                        fingerprint,
                        item.start_ms,
                        item.end_ms,
                    ),
                )
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO evidence_vector VALUES (%s,%s,%s,%s,%s,%s::vector)",
                        [
                            (
                                request.owner_id,
                                request.course_id,
                                item.evidence_id,
                                i,
                                key,
                                json.dumps(vector),
                            )
                            for i, ((evidence, _), key, vector) in enumerate(
                                zip(chunks, hashes, vectors, strict=True)
                            )
                            if evidence.evidence_id == item.evidence_id
                        ],
                    )
            conn.execute(
                """DELETE FROM indexed_evidence WHERE owner_id=%s AND course_id=%s
                            AND NOT (evidence_id=ANY(%s))""",
                (request.owner_id, request.course_id, request.evidence_ids),
            )
            count = conn.execute(
                "SELECT count(*) FROM indexed_evidence WHERE owner_id=%s AND course_id=%s",
                (request.owner_id, request.course_id),
            ).fetchone()[0]
            if count != len(request.evidence_ids):
                raise ValueError("Incomplete delta; plan again")
            total_chunks = conn.execute(
                "SELECT count(*) FROM evidence_vector WHERE owner_id=%s AND course_id=%s",
                (request.owner_id, request.course_id),
            ).fetchone()[0]
            if total_chunks > 5000:
                raise ValueError("Chunk limit exceeded")
            key = hashlib.sha256(
                json.dumps(
                    [
                        request.owner_id,
                        request.course_id,
                        request.revision,
                        version,
                        sorted(request.evidence_ids),
                    ]
                ).encode()
            ).hexdigest()
            conn.execute(
                """UPDATE evidence_index SET sequence=%s,revision=%s,index_version=%s,state='READY',
                            snapshot_id=%s,updated_at=now() WHERE owner_id=%s AND course_id=%s""",
                (request.sequence, request.revision, version, key, request.owner_id, request.course_id),
            )
            return self._response(request, version, "READY")

    def delete(self, request, version):
        with self.connect() as conn:
            self._head(conn, request, version)
            conn.execute(
                "DELETE FROM indexed_evidence WHERE owner_id=%s AND course_id=%s",
                (request.owner_id, request.course_id),
            )
            conn.execute(
                """UPDATE evidence_index SET sequence=%s,revision=%s,state='DELETED',snapshot_id='',updated_at=now()
                            WHERE owner_id=%s AND course_id=%s""",
                (request.sequence, request.revision, request.owner_id, request.course_id),
            )
            return self._response(request, version, "DELETED")

    def ready_snapshot(self, request, version):
        with self.connect() as conn:
            row = conn.execute(
                """SELECT snapshot_id FROM evidence_index WHERE owner_id=%s AND course_id=%s
                                  AND revision=%s AND index_version=%s AND state='READY'""",
                (request.owner_id, request.course_id, request.revision, version),
            ).fetchone()
            return row[0] if row else None

    def search(self, snapshot_id, request, index_version, vector):
        window = request.time_window
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT v.evidence_id,max(1-(v.embedding <=> %s::vector)) AS score
                   FROM evidence_vector v JOIN indexed_evidence e USING(owner_id,course_id,evidence_id)
                   JOIN evidence_index i USING(owner_id,course_id)
                   WHERE i.snapshot_id=%s AND i.owner_id=%s AND i.course_id=%s AND i.revision=%s
                   AND i.index_version=%s AND i.state='READY' AND v.evidence_id=ANY(%s)
                   AND e.start_ms<=%s AND e.end_ms>=%s
                   GROUP BY v.evidence_id ORDER BY score DESC,v.evidence_id LIMIT %s""",
                (
                    json.dumps(vector),
                    snapshot_id,
                    request.owner_id,
                    request.course_id,
                    request.revision,
                    index_version,
                    request.allowed_evidence_ids,
                    window.end_ms if window else 9223372036854775807,
                    window.start_ms if window else 0,
                    request.top_k,
                ),
            ).fetchall()
            # A concurrent delete/replacement must not become an empty successful retrieval.
            active = conn.execute(
                """SELECT 1 FROM evidence_index WHERE owner_id=%s AND course_id=%s
                                     AND snapshot_id=%s AND state='READY'""",
                (request.owner_id, request.course_id, snapshot_id),
            ).fetchone()
            if not active:
                raise StaleSync("Index changed during retrieval")
            return [{"evidence_id": row[0], "score": row[1]} for row in rows]
