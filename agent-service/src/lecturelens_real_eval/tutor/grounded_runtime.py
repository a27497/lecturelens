"""Explicit v11 development variant; no application/default registration."""

import copy
import hashlib
import json
import re

from lecturelens_real_eval.runner import SnapshotAuthority

from .python_runtime import FINISH_LIMITS as PARENT_LIMITS
from .python_runtime import SYSTEM as PARENT_SYSTEM
from .python_runtime import PythonTutorRuntime

CONTEXT_VERSION = "adjacent-source-passages-v1"
GUIDANCE = (
    "Answer every part of the learner's question using the observed source. Distinguish ordinal positions "
    "from literal index labels; check the source's counting convention before translating between them. "
    "If a required detail is missing, use the remaining search when available, otherwise abstain under the "
    "existing rules. Prefer task-critical facts over optional background. During format repair retain only "
    "claims supported by kept citations; do not add unverified whole-unit scope assertions."
)
FINISH_LIMITS = PARENT_LIMITS + " " + GUIDANCE
SYSTEM = PARENT_SYSTEM.replace(PARENT_LIMITS, FINISH_LIMITS, 1)


def passages(rows):
    """Join adjacent source blocks, never references; retain exact member provenance.

    Code and output often have no lexical query overlap. Ranking these bounded passages
    keeps their explanatory prose attached. Oversize original blocks remain indivisible;
    inherited request/turn bounds still fail closed rather than silently truncating them.
    """
    result, group = [], []

    def flush():
        if not group:
            return
        text = "\n\n".join(e["text"] for e in group)
        members = [e["evidence_id"] for e in group]
        eid = hashlib.sha256(json.dumps([CONTEXT_VERSION, members]).encode()).hexdigest()
        result.append(
            {
                **group[0],
                "evidence_id": eid,
                "text": text,
                "content_hash": hashlib.sha256(text.encode()).hexdigest(),
                "line_end": group[-1]["line_end"],
                "source_url": group[0]["source_url"].split("#")[0]
                + f"#L{group[0]['line_start']}-L{group[-1]['line_end']}",
                "member_evidence_ids": members,
                "member_locations": [
                    {k: e[k] for k in ("evidence_id", "line_start", "line_end", "content_hash")}
                    for e in group
                ],
                "context_version": CONTEXT_VERSION,
            }
        )
        group.clear()

    for row in rows:
        # Never cross a source, heading or out-of-order boundary; no source bytes change.
        if group and (
            row["source_path"] != group[-1]["source_path"]
            or row["line_start"] <= group[-1]["line_end"]
            or re.match(r"^#{1,6} ", row["text"])
            or len(group) >= 6
            or sum(len(e["text"]) + 2 for e in group) + len(row["text"]) > 1000
        ):
            flush()
        group.append(row)
    flush()
    return result


class PassageAuthority(SnapshotAuthority):
    def __init__(self, snapshot):
        derived = copy.deepcopy(snapshot)
        for lecture in derived["lectures"].values():
            lecture["evidence"] = passages(lecture["evidence"])
        super().__init__(derived)


class GroundedTutorRuntime(PythonTutorRuntime):
    def request(self, session, turn, state, history):
        messages, schemas, _ = super().request(session, turn, state, history)
        messages[0] = {"role": "system", "content": SYSTEM}
        for schema in schemas:
            if schema["function"]["name"] == "finish_tutor_turn":
                schema["function"]["description"] = FINISH_LIMITS
        amount = len(json.dumps([messages, schemas], ensure_ascii=False).encode()) + 1200
        return messages, schemas, amount
