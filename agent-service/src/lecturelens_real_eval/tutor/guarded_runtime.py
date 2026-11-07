"""V17 closes the AST/display lexical gap without editing the frozen v16 runtime."""

import json
import re

from psycopg.types.json import Jsonb

from lecturelens_agent.study.store import StudyError

from .verified_runtime import VerifiedProposal, VerifiedStore, VerifiedTutorRuntime
from .verified_runtime import calculate as value_calculate

IDENTITY = "p8-tutor-verified-v17-development"
VALUE_CHARACTERS = r"[0-9a-z +*/%().,\[\]-]{1,120}"


def calculate(expression):
    # ast.parse ignores comments; rendering the original expression would expose
    # unchecked prose. Require the complete displayed string to be value syntax.
    if not re.fullmatch(VALUE_CHARACTERS, expression):
        raise StudyError("TUTOR_CALCULATION_INVALID")
    return value_calculate(expression)


class GuardedStore(VerifiedStore):
    @staticmethod
    def checkpoint(conn, turn_id, state):
        VerifiedStore.checkpoint(conn, turn_id, state)
        conn.execute(
            "UPDATE tutor_turn SET checkpoint=jsonb_set(checkpoint,'{candidate}',%s) WHERE turn_id=%s",
            (Jsonb(IDENTITY), turn_id),
        )


class GuardedTutorRuntime(VerifiedTutorRuntime):
    def __init__(self, store, authority, provider=None):
        super().__init__(store, authority, provider)
        self.store = GuardedStore(store.dsn)

    def request(self, session, turn, state, history):
        messages, schemas, _ = super().request(session, turn, state, history)
        messages[0]["content"] += (
            "\nEvery displayed calculation expression must entirely match the ASCII value grammar: no comments, control characters or extra prose."
        )
        for schema in schemas:
            if schema["function"]["name"] == "finish_tutor_turn":
                schema["function"]["parameters"]["$defs"]["CalculationBlock"]["properties"]["expression"][
                    "pattern"
                ] = "^" + VALUE_CHARACTERS + "$"
        return messages, schemas, len(json.dumps([messages, schemas], ensure_ascii=False).encode()) + 1200

    def act(self, turn_id, state, history):
        response = state["response"]
        if isinstance(response, dict) and response.get("name") == "finish_tutor_turn":
            if response["name"] not in self.allowed_names(state):
                raise StudyError("TUTOR_PROTOCOL_FAILURE")
            proposal = VerifiedProposal.model_validate(response["arguments"]).model_dump()
            invalid = any(
                item["kind"] == "calculation" and not re.fullmatch(VALUE_CHARACTERS, item["expression"])
                for item in proposal["blocks"]
            )
            if invalid:
                items = (
                    proposal["blocks"]
                    + proposal["evaluation_blocks"]
                    + ([proposal["hint"]] if proposal["hint"] else [])
                )
                ids = list(dict.fromkeys(item["evidence_id"] for item in items))
                if not set(ids) <= set(state["selected"]):
                    raise StudyError("TUTOR_CITATION_MISMATCH")
                with self.store.connect() as conn:
                    session, turn = self.store.rows(conn, turn_id)
                    self.guard(session, turn)
                    self.read_evidence(session, ids)
                return self.repair(
                    turn_id,
                    state,
                    proposal,
                    "VALUE_EXPRESSION_LEXER: the entire expression is displayed. Select only bounded ASCII value syntax, without comments, controls or prose. Preserve requested conclusions; one correction within existing budgets.",
                )
        return super().act(turn_id, state, history)
