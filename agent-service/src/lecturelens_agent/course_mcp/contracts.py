from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..contracts import Contract, Identifier
from ..study.contracts import StudyScope


class JavaProof(Contract):
    timestamp: Annotated[str, Field(pattern=r"^[0-9]{1,12}$")]
    signature: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CourseRequest(StudyScope):
    authorization: JavaProof


class SearchRequest(CourseRequest):
    query: Annotated[str, Field(min_length=1, max_length=500)]
    start_ms: Annotated[int, Field(ge=0)] | None = None
    end_ms: Annotated[int, Field(ge=0)] | None = None


class HitSpan(Contract):
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def bounded(self):
        if not 0 < self.end - self.start <= 240:
            raise ValueError("Invalid Evidence hit span")
        return self


class LocatedRequest(CourseRequest):
    hit_spans: Annotated[dict[Identifier, HitSpan], Field(max_length=8)] | None = None
    hit_hashes: (
        Annotated[dict[Identifier, Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]], Field(max_length=8)]
        | None
    ) = None


class ReadRequest(LocatedRequest):
    evidence_ids: Annotated[list[Identifier], Field(max_length=8)]


class WindowRequest(LocatedRequest):
    evidence_id: Identifier


class CourseEvidence(Contract):
    evidence_id: Identifier
    text: Annotated[str, Field(max_length=1200)]
    start_ms: Annotated[int, Field(ge=0)]
    end_ms: Annotated[int, Field(ge=0)]
    source_type: Annotated[str, Field(min_length=1, max_length=64)]
    text_start: Annotated[int, Field(ge=0)] | None = None
    text_end: Annotated[int, Field(ge=0)] | None = None
    match_start: Annotated[int, Field(ge=0)] | None = None
    match_end: Annotated[int, Field(gt=0)] | None = None
    match_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    canonical_length: Annotated[int, Field(ge=0)] | None = None
    match_resolution: Literal["UNIQUE_HASH", "AMBIGUOUS_TEXT"] | None = None

    @model_validator(mode="after")
    def interval(self):
        if self.end_ms < self.start_ms:
            raise ValueError("Invalid Evidence interval")
        for start, end in ((self.text_start, self.text_end), (self.match_start, self.match_end)):
            if (start is None) != (end is None) or (start is not None and end < start):
                raise ValueError("Invalid Evidence text interval")
        if self.text_start is not None and self.text_end - self.text_start != len(self.text):
            raise ValueError("Evidence window offsets must match its Unicode text")
        if self.match_start is not None and not 0 < self.match_end - self.match_start <= 240:
            raise ValueError("Invalid Evidence hit span")
        if self.canonical_length is not None and any(
            end is not None and end > self.canonical_length for end in (self.text_end, self.match_end)
        ):
            raise ValueError("Evidence offsets exceed the canonical source")
        return self


class CourseResult(StudyScope):
    evidence: Annotated[list[CourseEvidence], Field(max_length=8)]


# Names and argument schemas are fixed, not dynamically supplied to the model.
# Agent injects scope + Java proof after its existing tool argument validation.
TOOLS = {
    "get_course_revision": (
        "CHECK",
        CourseRequest,
        "Check the supplied course revision with Java authority.",
    ),
    "search_course_evidence": (
        "SEARCH",
        SearchRequest,
        "Search current authorized course Evidence, including adjacent context.",
    ),
    "get_course_evidence": ("READ", ReadRequest, "Read up to eight exact current Evidence IDs."),
    "get_evidence_context": ("WINDOW", WindowRequest, "Read the anchor and adjacent same-source Evidence."),
}
ACTION_TO_TOOL = {value[0]: name for name, value in TOOLS.items()}


def authority_payload(name, arguments):
    action, schema, _ = TOOLS[name]
    # exclude_unset preserves absence vs explicit null in the signed request.
    request = schema.model_validate(arguments).model_dump(exclude_unset=True)
    proof = request.pop("authorization")
    return {**request, "action": action}, proof
