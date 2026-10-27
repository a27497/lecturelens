from typing import Annotated, Literal

from pydantic import Field, model_validator

from lecturelens_agent.contracts import Contract, Identifier
from lecturelens_agent.study.contracts import StudyScope


class Command(StudyScope):
    operation: Literal["CREATE", "LIST", "GET", "TURN", "CANCEL"]
    session_id: Identifier | None = None
    client_turn_id: Identifier | None = None
    request_key: Identifier | None = None
    text: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    socratic: Annotated[bool, Field(strict=True)] = False

    @model_validator(mode="after")
    def required(self):
        if self.operation == "CREATE" and not self.request_key:
            raise ValueError("Request key required")
        if self.operation in {"GET", "TURN", "CANCEL"} and not self.session_id:
            raise ValueError("Session required")
        if self.operation in {"TURN", "CANCEL"} and not self.client_turn_id:
            raise ValueError("Client turn id required")
        if self.operation == "TURN" and not (self.text or "").strip():
            raise ValueError("Learner text required")
        return self


class Search(Contract):
    query: Annotated[str, Field(min_length=1, max_length=500)]


class Finish(Contract):
    outcome: Literal["answered", "socratic_prompt", "insufficient_evidence"]
    text: Annotated[str, Field(min_length=1, max_length=1600)]
    evidence_ids: Annotated[list[Identifier], Field(max_length=4)]
    evaluation: Annotated[str, Field(max_length=500)] = ""


class FinishProposal(Finish):
    """Private validation only: defer exactly the three publication size limits.

    Retain strict types, required fields, identifier constraints and extra-field
    rejection, including invalid items beyond the first four declared citations.
    Never use this schema for model tools or publication.
    """

    text: Annotated[str, Field(min_length=1)]
    evidence_ids: list[Identifier]
    evaluation: str = ""


def validate_proposal(name, arguments):
    return (FinishProposal if name == "finish_tutor_turn" else TOOLS[name]).model_validate(arguments)


TOOLS = {"search_tutor_evidence": Search, "finish_tutor_turn": Finish}
ABSTENTION = "I don't know from this course. Try asking about a topic covered in this lecture."
