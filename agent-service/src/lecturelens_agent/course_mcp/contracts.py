from typing import Annotated

from pydantic import Field

from ..contracts import Contract
from ..study.evidence_contract import (
    CourseEvidence as CourseEvidence,
)
from ..study.evidence_contract import (
    CourseResult as CourseResult,
)
from ..study.evidence_contract import (
    EvidenceReadRequest,
    EvidenceRequest,
    EvidenceSearchRequest,
    EvidenceWindowRequest,
)


class JavaProof(Contract):
    timestamp: Annotated[str, Field(pattern=r"^[0-9]{1,12}$")]
    signature: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CourseRequest(EvidenceRequest):
    authorization: JavaProof


class SearchRequest(EvidenceSearchRequest, CourseRequest):
    pass


class ReadRequest(EvidenceReadRequest, CourseRequest):
    pass


class WindowRequest(EvidenceWindowRequest, CourseRequest):
    pass


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
