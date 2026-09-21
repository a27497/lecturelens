"""Observed teaching methods, bound to exact authorized source spans.

This is a private planning observation, not a proof of pedagogical support.
"""

from typing import Annotated

from pydantic import Field

from ..contracts import Contract


class MethodSelection(Contract):
    operation: Annotated[str, Field(min_length=1, max_length=120)]
    input: Annotated[str, Field(min_length=1, max_length=100)]
    output: Annotated[str, Field(min_length=1, max_length=100)]
    evidence_id: Annotated[str, Field(min_length=1, max_length=128)]


class MethodObservation(MethodSelection):
    quote: Annotated[str, Field(min_length=1, max_length=1200)]


def latest_coverage(history):
    for item in reversed(history):
        if "course_coverage" in item["result"]:
            return item["result"]["course_coverage"]
        if item["tool"] == "search_course_evidence":
            break
    return None


METHOD_SYSTEM = """
Also extract up to TWO methods actually demonstrated by these passages for the requested learner application. Prioritize an elementary check actually performed in a worked example over a broad topic description. When the goal asks to check supplied coordinates, observe the demonstrated substitution/check (if present), not only drawing a line or solving for an unknown coordinate. Do not invent a check absent from the source.
For each method record its operation, input kind and output kind in the learner language, each <=80 characters. Select one observed evidence_id that demonstrates it. Python will bind the exact authorized passage; do not transcribe or invent a quotation. These are course observations, not a proposal for a new problem. Record demonstrated methods independently of goal coverage: even an absent goal may have related observed methods. For answerable goals give at least one method; give none only if no relevant method is demonstrated. An absent judgment is advisory, not permission to widen the observed operation. Repetition of a check for multiple inputs keeps the same operation and per-input output.
Keep the operation and output as narrow as the actual demonstration. New numbers or a deliberately mistaken execution of that SAME operation are transferable. A new operation, classification of all possible outcomes, general theorem, or extra output is a DIFFERENT task requiring its own teaching evidence. Do not widen a demonstrated check into a general classification just because you know the mathematics. Do not describe anything as demonstrated solely because it is logically derivable. Select a source that actually shows the operation and output; its identifier establishes provenance, not semantic support.
"""


class MethodAlignment(Contract):
    operation: Annotated[str, Field(min_length=1, max_length=180)]
    output: Annotated[str, Field(min_length=1, max_length=100)]
    matches: bool
