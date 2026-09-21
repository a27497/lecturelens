"""Exact learner constraints and private observations, never inferred course facts."""

import re
from typing import Annotated

from pydantic import Field

from ..contracts import Contract


def goal_constraints(goal):
    # Keep every character (including a final tail), with at most six addresses.
    # These are syntactic clauses, not a claim that language has been understood.
    parts = re.findall(r"[^。；;\n]+[。；;\n]*|[。；;\n]+", goal)
    parts = parts[:5] + (["".join(parts[5:])] if len(parts) > 5 else [])
    return [{"id": f"g{i + 1}", "text": part} for i, part in enumerate(parts)]


class GoalCheck(Contract):
    id: Annotated[str, Field(pattern=r"^g[1-6]$")]
    observation: Annotated[str, Field(min_length=1, max_length=160)]
    matches: bool


def refusal_text(goal):
    if re.search(r"[\u3400-\u9fff]", goal):
        return "当前检索到的课程片段不足以支持这项学习目标。请补充相关课程内容，或缩小问题范围。"
    return (
        "The retrieved course passages do not provide enough support for this learning goal. "
        "Please provide relevant course material or narrow the request."
    )


GOAL_SYSTEM = """
Use learner language. Resolve own_evidence.text_ref via passages. Sources are bound by field; do not return citation IDs. Computation-verified results are supplied for checking task conditions, not for re-solving. Check the requested new inputs, never require the exact classroom example. goal_checks: EVERY supplied id once. Compare ALL demands with actual inputs AND answers: counts/signs/order/exclusions/all/exactly-one/neither. For arithmetic conditions give EACH substituted result, even when one failure decides. A correct answer to a different task fails. For a requested correction exercise, identify the actual erroneous claim the question asks to correct; a plain verification question without an error is not a correction exercise. Observations <=160 characters, not repeated requests. matches=false rejects. No invented constraints. Goal checks compare the candidate with the learner request ONLY; course support belongs in the separate source checks. A request for a learner to perform checks is fulfilled by the question plus its verified_results; it does not require repeating every exercise calculation in the explanation.
"""


def explanation_claims(text):
    # Address every sentence without splitting decimal points. This is a syntactic
    # observation boundary, not a promise that each sentence contains one fact.
    parts = re.split(r"(?<=[。！？!?；;])|(?<=\.)\s+(?=[A-Z])", text)
    parts = [part for part in parts if part.strip()]
    parts = parts[:5] + (["".join(parts[5:])] if len(parts) > 5 else [])
    return [{"id": f"x{i + 1}", "text": part} for i, part in enumerate(parts)]


class ClaimCheck(Contract):
    id: Annotated[str, Field(pattern=r"^x[1-6]$")]
    course_fact: Annotated[str, Field(min_length=1, max_length=120)]
    evidence_ids: Annotated[list[str], Field(min_length=1, max_length=8)]
    supported: bool


CLAIM_SYSTEM = """
explanation_checks: EVERY explanation_claims id once. First state what the explanation's OWN citations teach (course_fact <=120 characters), then supported only if they support ALL claims in that sentence. Its sources are bound to the explanation; do not return citation IDs. Other fields' passages, uncited course facts, and true external knowledge cannot support it. Check later clauses too; do not silently drop them. A source teaching one equation and its solution line does NOT support a claim about multiple equations or their intersection. A topic heading does not teach an unstated relationship. For each claim, distinguish what the cited passage actually says from true mathematical background; if that relationship is absent, supported=false even when the claim is mathematically correct. An intersecting-lines example does not prove general uniqueness. No untaught solution counts. Demonstrated methods support new inputs. False means remove the claim or cite its actual source.
"""


def joint_relation_without_source_signal(claim, source_texts):
    """Conservative negative signal in the supported English/Chinese scope.

    A matching word is NOT a proof of entailment. Independent semantic review
    remains mandatory; unfamiliar wording may need clearer supporting context.
    """
    relation = bool(
        re.search(
            r"方程组.*(?:交点|公共点|所有方程|各条直线|同时)|(?:system|equations?).*(?:intersection|common point|all equations|both lines)",
            claim,
            re.I,
        )
    )
    source = re.sub(r"\s+", "", " ".join(source_texts)).lower()
    signal = re.search(
        r"both(?:lines|equations)|simultaneous|intersect|commonpoint|共同|交点|同时.{0,30}(?:方程|直线)|所有方程",
        source,
    )
    return relation and not signal


def missing_explicit_correction_task(goal, application_question):
    """Reject an explicit correction request whose application shows no error/claim.

    This is a narrow task-shape guard, not a general language understanding test.
    Negated/ambiguous requests are left to the semantic reviewer.
    """
    if re.search(
        r"(?:不要|无需|不必|不需要).{0,12}(?:纠错|纠正)|(?:no|not).{0,12}(?:correct|fix)", goal, re.I
    ):
        return False
    requested = re.search(
        r"一道.{0,12}(?:纠错|纠正)|(?:纠错|纠正).{0,20}(?:题|练习)|(?:correct|fix).{0,30}(?:mistake|error|misconception)",
        goal,
        re.I,
    )
    actual = re.search(
        r"纠|错|同学|声称|说法|断言|claims?|says?|asserts?|mistake|incorrect|error|correct|fix",
        application_question,
        re.I,
    )
    return bool(requested and not actual)
