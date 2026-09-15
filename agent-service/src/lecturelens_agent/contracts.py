from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=128)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Evidence(Contract):
    evidence_id: Identifier
    text: Annotated[str, Field(min_length=1, max_length=8000)]
    start_ms: Annotated[int, Field(ge=0)]
    end_ms: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_ms < self.start_ms or not self.text.strip():
            raise ValueError("Invalid evidence time range or blank text")
        return self


class TimeWindow(Contract):
    start_ms: Annotated[int, Field(ge=0)]
    end_ms: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_ms < self.start_ms:
            raise ValueError("Reversed time window")
        return self


class RetrieveRequest(Contract):
    request_id: Identifier
    owner_id: Annotated[int, Field(ge=1)]
    course_id: Identifier
    revision: Annotated[int, Field(ge=0)]
    query: Annotated[str, Field(min_length=1, max_length=500)]
    evidence: Annotated[list[Evidence], Field(min_length=1, max_length=2000)]
    top_k: Annotated[int, Field(ge=1, le=8)] = 8
    time_window: TimeWindow | None = None

    @model_validator(mode="after")
    def bounded_snapshot(self):
        if not self.query.strip():
            raise ValueError("Blank query")
        if len({e.evidence_id for e in self.evidence}) != len(self.evidence):
            raise ValueError("Duplicate evidence ID")
        if sum(len(e.text) for e in self.evidence) > 750_000:
            raise ValueError("Snapshot too large")
        return self


class Hit(Contract):
    evidence_id: Identifier
    score: Annotated[float, Field(ge=-1.000001, le=1.000001, allow_inf_nan=False)]


class RetrieveResponse(Contract):
    request_id: str
    owner_id: int
    course_id: str
    revision: int
    index_version: str
    snapshot_id: str
    cache_hit: bool
    hits: list[Hit]
