"""Evidence request and result contracts shared by both transports."""

from typing import Annotated

from pydantic import Field, model_validator

from ..contracts import Contract, Identifier
from .contracts import StudyScope
from .learning_scope import LearningScope


class EvidenceRequest(StudyScope):
    learning_scope: LearningScope | None = None


class EvidenceSearchRequest(EvidenceRequest):
    expand_to_course: Annotated[bool, Field(strict=True)] = False
    query: Annotated[str, Field(min_length=1, max_length=500)]
    start_ms: Annotated[int, Field(ge=0, le=2**63 - 1)] | None = None
    end_ms: Annotated[int, Field(ge=0, le=2**63 - 1)] | None = None

    @model_validator(mode="after")
    def valid_window(self):
        if not self.query.strip() or (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("Invalid query or time window")
        if self.start_ms is not None and self.start_ms > self.end_ms:
            raise ValueError("Reversed time window")
        return self


class EvidenceReadRequest(EvidenceRequest):
    evidence_ids: Annotated[list[Identifier], Field(max_length=8)]


class EvidenceWindowRequest(EvidenceRequest):
    evidence_id: Identifier


class CourseEvidence(Contract):
    evidence_id: Identifier
    text: Annotated[str, Field(max_length=1200)]
    start_ms: Annotated[int, Field(ge=0, le=2**63 - 1)]
    end_ms: Annotated[int, Field(ge=0, le=2**63 - 1)]
    source_type: Annotated[str, Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def interval(self):
        if self.end_ms < self.start_ms:
            raise ValueError("Invalid Evidence interval")
        return self


class CourseResult(StudyScope):
    learning_scope: LearningScope | None = None
    evidence: Annotated[list[CourseEvidence], Field(max_length=8)]


EVIDENCE_REQUESTS = {
    "CHECK": EvidenceRequest,
    "SEARCH": EvidenceSearchRequest,
    "READ": EvidenceReadRequest,
    "WINDOW": EvidenceWindowRequest,
}
