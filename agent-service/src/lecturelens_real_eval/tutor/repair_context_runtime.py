"""Opt-in v12: keep format repair within the existing context reservation bounds."""

import json

from lecturelens_agent.study.store import StudyError

from .grounded_runtime import GroundedTutorRuntime


class RepairContextTutorRuntime(GroundedTutorRuntime):
    def request(self, session, turn, state, history):
        messages, schemas, amount = super().request(session, turn, state, history)
        repair = next(
            (
                observation
                for observation in reversed(state["observations"])
                if observation.get("error") == "TUTOR_FINISH_REPAIR_REQUIRED"
            ),
            None,
        )
        if repair is None:
            return messages, schemas, amount
        keep = repair.get("keep_ids")
        if (
            not isinstance(keep, list)
            or len(keep) > 4
            or any(not isinstance(eid, str) for eid in keep)
            or len(set(keep)) != len(keep)
            or not set(keep) <= set(state["selected"])
        ):
            raise StudyError("TUTOR_PROTOCOL_FAILURE")
        body = json.loads(messages[-1]["content"])
        # The parent re-READs the entire authorized union first. Only the model's
        # repair view shrinks: checkpoint authority, history and observations survive.
        # The rejected finish already instructs removal of claims relying on other IDs.
        by_id = {e["evidence_id"]: e for e in body["evidence"]}
        body["evidence"] = [by_id[eid] for eid in keep]
        messages[-1]["content"] = json.dumps(body, ensure_ascii=False, default=str)
        messages[0]["content"] = messages[0]["content"].replace(
            "Evidence contains the ordered union of this turn's search observations; history does not authorize citations.",
            "During finish-format repair Evidence contains the kept citation sources; "
            "search observations retain this turn's authorized union. History does not authorize citations.",
        )
        # Reserve the actual projected request, including unchanged schemas and the
        # existing output allowance; never refund prior calls or enlarge any cap.
        amount = len(json.dumps([messages, schemas], ensure_ascii=False).encode()) + 1200
        return messages, schemas, amount
