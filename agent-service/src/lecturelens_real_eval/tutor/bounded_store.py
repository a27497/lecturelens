"""V15 accounting in the existing checkpoint; no table/column migration."""

from lecturelens_agent.study.store import StudyError
from psycopg.types.json import Jsonb

from .store import TutorStore


def known_usage(usage):
    if not isinstance(usage, dict) or any(
        type(usage.get(k)) is not int or not 0 <= usage[k] <= 2**63 - 1
        for k in ("prompt_tokens", "completion_tokens")
    ):
        return None
    return {k: usage[k] for k in ("prompt_tokens", "completion_tokens")}


class BoundedStore(TutorStore):
    def check_admission(self):
        with self.connect() as conn:
            schema = conn.execute("SELECT current_schema() AS s").fetchone()["s"]
            public_legacy = conn.execute(
                "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename IN ('tutor_session','tutor_turn') LIMIT 1"
            ).fetchone()
            if not schema or schema == "public" or public_legacy:
                raise StudyError("TUTOR_V15_DEDICATED_SCHEMA_REQUIRED")

    def initialize(self):
        self.check_admission()
        super().initialize()

    @staticmethod
    def checkpoint(conn, turn_id, state):
        from .bounded_runtime import IDENTITY

        current = conn.execute(
            "SELECT checkpoint,model_calls FROM tutor_turn WHERE turn_id=%s", (turn_id,)
        ).fetchone()
        accounting = current["checkpoint"].get("call_accounting", []) if current else []
        if (
            current
            and state.get("repair_request")
            and not any(r["call_index"] == current["model_calls"] for r in accounting)
        ):
            accounting = [
                *accounting,
                {
                    "call_index": current["model_calls"],
                    "response_state": "prepaid_not_dispatched",
                    "usage_state": "not_run",
                    "usage": None,
                    "runtime_reserved_proxy": state["repair_request"][2],
                    "fee_state": "not_dispatched",
                    "charged_nano_usd": 0,
                    "reservation_released": False,
                },
            ]
        TutorStore.checkpoint(conn, turn_id, {**state, "candidate": IDENTITY, "call_accounting": accounting})

    def record_accounting(self, turn_id, index, values, usage=None):
        with self.connect() as conn:
            exists = conn.execute("SELECT 1 FROM tutor_turn WHERE turn_id=%s", (turn_id,)).fetchone()
            if not exists:
                return  # Deletion never recreates private course/session state.
            _, turn = self.rows(conn, turn_id)
            state = turn["checkpoint"]
            records = {row["call_index"]: row for row in state.get("call_accounting", [])}
            old = records.get(index, {})
            row = {**old, "call_index": index, **values}
            parsed = known_usage(usage)
            if parsed is not None:
                if old.get("usage_state") == "known" and old["usage"] != parsed:
                    raise StudyError("TUTOR_USAGE_CONFLICT")
                row.update(usage_state="known", usage=parsed)
                if old.get("usage_state") != "known":
                    conn.execute(
                        "UPDATE tutor_turn SET usage=usage || %s WHERE turn_id=%s", (Jsonb([parsed]), turn_id)
                    )
            elif old.get("usage_state") != "known":
                row.setdefault("usage_state", "unknown")
                row.setdefault("usage", None)
            else:
                row.update(usage_state="known", usage=old["usage"])
            records[index] = row
            # Accounting may settle after CANCEL/deadline; only numeric telemetry is
            # retained. Publication still requires the independent authority guards.
            TutorStore.checkpoint(conn, turn_id, {**state, "call_accounting": list(records.values())})

    @staticmethod
    def public_turn(row):
        return {**TutorStore.public_turn(row), "accounting": row["checkpoint"].get("call_accounting", [])}
