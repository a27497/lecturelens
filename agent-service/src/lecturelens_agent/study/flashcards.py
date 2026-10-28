"""Course-owned derived cards. Run publication, reviews and replay commit atomically."""

import uuid
from datetime import timedelta

from psycopg.types.json import Jsonb

from .scheduling import POLICY, new_state, schedule, utc_now
from .store import StudyError

SCHEMA = """
ALTER TABLE study_run DROP CONSTRAINT IF EXISTS study_run_task_kind_check;
ALTER TABLE study_run ADD CONSTRAINT study_run_task_kind_check
    CHECK(task_kind IN ('practice','feedback','flashcards'));
CREATE OR REPLACE FUNCTION study_card_worker_fence() RETURNS trigger AS $$
BEGIN
    IF NEW.task_kind='flashcards' AND NEW.status IN ('queued','running') THEN
        NEW.status := NEW.status || '_cards_v1';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE OR REPLACE TRIGGER study_card_worker_fence BEFORE INSERT OR UPDATE ON study_run
    FOR EACH ROW EXECUTE FUNCTION study_card_worker_fence();

CREATE TABLE IF NOT EXISTS study_deck (
    deck_id text PRIMARY KEY, run_id text NOT NULL UNIQUE REFERENCES study_run ON DELETE CASCADE,
    title text NOT NULL, policy jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS study_card (
    card_id text PRIMARY KEY, deck_id text NOT NULL REFERENCES study_deck ON DELETE CASCADE,
    ordinal integer NOT NULL, front text NOT NULL, back text NOT NULL, citations jsonb NOT NULL,
    schedule jsonb NOT NULL, due_at timestamptz NOT NULL, version integer NOT NULL DEFAULT 0,
    UNIQUE(deck_id,ordinal), CHECK(version>=0)
);
CREATE INDEX IF NOT EXISTS study_card_due ON study_card(due_at,card_id);
CREATE TABLE IF NOT EXISTS study_review_log (
    review_id text PRIMARY KEY, card_id text NOT NULL REFERENCES study_card ON DELETE CASCADE,
    request_key text NOT NULL, expected_version integer NOT NULL, rating text NOT NULL,
    reviewed_at timestamptz NOT NULL, before_state jsonb NOT NULL, after_state jsonb NOT NULL,
    policy jsonb NOT NULL, UNIQUE(card_id,request_key), UNIQUE(card_id,expected_version),
    CHECK(rating IN ('Again','Hard','Good','Easy'))
);
CREATE UNIQUE INDEX IF NOT EXISTS study_one_active_cards_run ON study_run(session_id)
    WHERE status IN ('queued','running','awaiting_approval','queued_scoped_v1','running_scoped_v1',
    'awaiting_approval_scoped_v1','queued_cards_v1','running_cards_v1');
"""

# All read/review paths join the authoritative signed scope, never a client-provided deck owner.
SCOPE_SQL = """ FROM study_card c JOIN study_deck d USING(deck_id)
JOIN study_run r USING(run_id) JOIN study_session s USING(session_id)
WHERE s.owner_id=%s AND s.course_id=%s AND s.revision=%s AND r.status='succeeded' """


def publish(conn, run, cards):
    deck_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cards:{run['run_id']}"))
    now = utc_now()
    conn.execute(
        "INSERT INTO study_deck VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        (deck_id, run["run_id"], "证据闪卡（Mock 演示）", Jsonb(POLICY), now),
    )
    for index, card in enumerate(cards):
        card_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{deck_id}:{index}"))
        conn.execute(
            "INSERT INTO study_card(card_id,deck_id,ordinal,front,back,citations,schedule,due_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (
                card_id,
                deck_id,
                index,
                card["front"],
                card["back"],
                Jsonb(card["citations"]),
                Jsonb(new_state(now)),
                now,
            ),
        )
    return deck_id


def card_command(store, conn, command):
    scope = (command.owner_id, command.course_id, command.revision)
    now = utc_now()
    if command.operation == "DUE_CARDS":
        cards = conn.execute(
            "SELECT c.*,d.title,s.revision"
            + SCOPE_SQL
            + " AND c.due_at<=%s ORDER BY c.due_at,c.card_id LIMIT 50",
            (*scope, now),
        ).fetchall()
        counts = conn.execute(
            "SELECT count(*) FILTER (WHERE c.due_at<=%s) AS due_count, count(*) AS total_count, "
            "min(c.due_at) FILTER (WHERE c.due_at>%s) AS next_due_at" + SCOPE_SQL,
            (now, now, *scope),
        ).fetchone()
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        reviewed = conn.execute(
            "SELECT count(DISTINCT l.card_id) AS n FROM study_review_log l JOIN study_card c USING(card_id) "
            "JOIN study_deck d USING(deck_id) JOIN study_run r USING(run_id) "
            "JOIN study_session s USING(session_id) WHERE s.owner_id=%s AND s.course_id=%s "
            "AND s.revision=%s AND l.reviewed_at>=%s AND l.reviewed_at<%s",
            (*scope, day, day + timedelta(days=1)),
        ).fetchone()["n"]
        generation = conn.execute(
            "SELECT r.* FROM study_run r JOIN study_session s USING(session_id) "
            "WHERE s.owner_id=%s AND s.course_id=%s AND s.revision=%s AND r.task_kind='flashcards' "
            "ORDER BY r.created_at DESC LIMIT 1",
            scope,
        ).fetchone()
        return {
            **counts,
            "cards": cards,
            "reviewed_today": reviewed,
            "day_timezone": "UTC",
            "generation": store._view(conn, generation)["run"] if generation else None,
            "server_now": now,
        }
    row = conn.execute(
        "SELECT c.*,s.revision" + SCOPE_SQL + " AND c.card_id=%s FOR UPDATE OF c",
        (*scope, command.card_id),
    ).fetchone()
    if not row:
        raise StudyError("CARD_NOT_FOUND_OR_STALE", 404)
    if command.operation == "READ_CARD":
        return {"card": row}
    prior = conn.execute(
        "SELECT * FROM study_review_log WHERE card_id=%s AND request_key=%s",
        (command.card_id, command.request_key),
    ).fetchone()
    if prior:
        if prior["rating"] != command.rating or prior["expected_version"] != command.expected_version:
            raise StudyError("REQUEST_KEY_CONFLICT")
        return {"review": prior, "replayed": True}
    if row["version"] != command.expected_version:
        raise StudyError("CARD_VERSION_CONFLICT")
    if row["due_at"] > now:
        raise StudyError("CARD_NOT_DUE")
    after = schedule(row["schedule"], command.rating, now)
    review = conn.execute(
        "INSERT INTO study_review_log VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            str(uuid.uuid4()),
            command.card_id,
            command.request_key,
            command.expected_version,
            command.rating,
            now,
            Jsonb(row["schedule"]),
            Jsonb(after),
            Jsonb(POLICY),
        ),
    ).fetchone()
    conn.execute(
        "UPDATE study_card SET schedule=%s,due_at=%s,version=version+1 WHERE card_id=%s",
        (Jsonb(after), after["due"], command.card_id),
    )
    return {"review": review, "replayed": False}
