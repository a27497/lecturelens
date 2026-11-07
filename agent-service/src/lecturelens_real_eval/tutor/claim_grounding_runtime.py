"""Opt-in v13: retain question/solution context and make claim grounding explicit."""

import copy
import hashlib
import json
import re

from lecturelens_real_eval.runner import SnapshotAuthority

from .grounded_runtime import passages
from .repair_context_runtime import RepairContextTutorRuntime

CONTEXT_VERSION = "question-solution-passages-v1"
GROUNDING = (
    "Evidence is retrieved excerpts, not complete course coverage: a search miss does not prove "
    "whole-unit absence. Before finishing, check every requested part and learner correction against "
    "the excerpts and actual history. Attach a supporting observed citation to every factual result, "
    "explanation and recommendation, including applications and optional additions; a nearby citation "
    "is not automatically support. Identify derivations as such and check all their premises in the "
    "cited text. An example does not establish a universal rule or an exact quotation. Never invent "
    "missing configuration or user artifacts."
)


def lesson_passages(rows):
    """Keep a short question with its immediately following solution, source-only.

    Parent windows split at every heading, including Solution. Joining only that
    structural continuation preserves the missing code/output without fetching
    evaluation references or enlarging the 1,000-character grouping bound.
    Indivisible oversized parent blocks and all runtime limits remain unchanged.
    """
    groups = []
    for row in passages(rows):
        if (
            groups
            and re.match(r"^#{1,6} Solution\b", row["text"])
            and "?" in groups[-1]["text"]
            and row["source_path"] == groups[-1]["source_path"]
            and row["line_start"] > groups[-1]["line_end"]
            and len(groups[-1]["text"]) + 2 + len(row["text"]) <= 1000
        ):
            previous = groups[-1]
            previous.update(
                text=previous["text"] + "\n\n" + row["text"],
                line_end=row["line_end"],
                member_evidence_ids=previous["member_evidence_ids"] + row["member_evidence_ids"],
                member_locations=previous["member_locations"] + row["member_locations"],
            )
        else:
            groups.append(copy.deepcopy(row))
    for row in groups:
        row.update(
            evidence_id=hashlib.sha256(
                json.dumps([CONTEXT_VERSION, row["member_evidence_ids"]]).encode()
            ).hexdigest(),
            content_hash=hashlib.sha256(row["text"].encode()).hexdigest(),
            context_version=CONTEXT_VERSION,
            source_url=row["source_url"].split("#")[0] + f"#L{row['line_start']}-L{row['line_end']}",
        )
    return groups


class LessonAuthority(SnapshotAuthority):
    def __init__(self, snapshot):
        derived = copy.deepcopy(snapshot)
        for lecture in derived["lectures"].values():
            lecture["evidence"] = lesson_passages(lecture["evidence"])
        super().__init__(derived)


class ClaimGroundingTutorRuntime(RepairContextTutorRuntime):
    """Explicit development selection only; no semantic grader or citation auto-fill."""

    def request(self, session, turn, state, history):
        messages, schemas, _ = super().request(session, turn, state, history)
        messages[0]["content"] += "\n" + GROUNDING
        amount = len(json.dumps([messages, schemas], ensure_ascii=False).encode()) + 1200
        return messages, schemas, amount
