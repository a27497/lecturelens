import hashlib
from typing import Annotated, Literal

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


class Scope(Contract):
    request_id: Identifier
    owner_id: Annotated[int, Field(ge=1)]
    course_id: Identifier
    revision: Annotated[int, Field(ge=0)]


class RetrieveRequest(Scope):
    query: Annotated[str, Field(min_length=1, max_length=500)]
    allowed_evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=2000)]
    top_k: Annotated[int, Field(ge=1, le=8)] = 8
    time_window: TimeWindow | None = None

    @model_validator(mode="after")
    def valid_query(self):
        if not self.query.strip():
            raise ValueError("Blank query")
        return self


class EvidenceMetadata(Contract):
    evidence_id: Identifier
    content_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    start_ms: Annotated[int, Field(ge=0)]
    end_ms: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_ms < self.start_ms:
            raise ValueError("Reversed metadata time range")
        return self


class SyncRequest(Scope):
    sequence: Annotated[int, Field(ge=0)]
    operation: Literal["PLAN", "APPLY", "DELETE"]
    manifest: Annotated[list[EvidenceMetadata], Field(max_length=2000)] = []

    upserts: Annotated[list[Evidence], Field(max_length=2000)] = []
    index_version: str | None = None

    @property
    def evidence_ids(self):
        return [item.evidence_id for item in self.manifest]

    @model_validator(mode="after")
    def valid_delta(self):
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Duplicate evidence ID")
        metadata = {item.evidence_id: item for item in self.manifest}
        for item in self.upserts:
            entry = metadata.get(item.evidence_id)
            if (
                entry is None
                or entry.content_hash != hashlib.sha256(item.text.encode()).hexdigest()
                or (entry.start_ms, entry.end_ms) != (item.start_ms, item.end_ms)
            ):
                raise ValueError("Manifest does not match upsert")
        ids = [e.evidence_id for e in self.upserts]
        if len(set(ids)) != len(ids) or not set(ids) <= set(self.evidence_ids):
            raise ValueError("Invalid upserts")
        if self.operation != "APPLY" and self.upserts:
            raise ValueError("Unexpected upserts")
        if self.operation == "DELETE" and self.evidence_ids:
            raise ValueError("Unexpected manifest")
        if sum(len(e.text) for e in self.upserts) > 750_000:
            raise ValueError("Delta too large")
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
