from typing import Annotated

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


class ReadRequest(CourseRequest):
    evidence_ids: Annotated[list[Identifier], Field(max_length=8)]


class WindowRequest(CourseRequest):
    evidence_id: Identifier


class CourseEvidence(Contract):
    evidence_id: Identifier
    text: Annotated[str, Field(max_length=1200)]
    start_ms: Annotated[int, Field(ge=0)]
    end_ms: Annotated[int, Field(ge=0)]
    source_type: Annotated[str, Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def interval(self):
        if self.end_ms < self.start_ms:
            raise ValueError("Invalid Evidence interval")
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
