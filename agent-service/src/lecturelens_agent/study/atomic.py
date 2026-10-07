"""Lossless answer span units, not extracted or independently established facts.

Syntactic boundaries expose modifiers separately. Unknown syntax remains in a
larger unit and must be fully supported; no wording is silently discarded.
"""

import re
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..contracts import Contract
from .relation_support import RelationSupport

MAX_CLAIMS = 24
_LINK = re.compile(
    r"\b(?:and|but|because|therefore|until|unless|if|only if|so that|as a result)\b"
    r"|并且|以及|但是|然而|而是|而非|只是|但|而|因此|所以|从而|直到|除非|如果|因为|由于|只要|只有|否则|导致|意味着",
    re.I,
)
_DISCOURSE = re.compile(
    r"具体来说|具体而言|换句话说|例如|比如|此外|首先|其次|最后"
    r"|\b(?:in particular|specifically|for example|in other words|first|next|finally)\b",
    re.I,
)


def expression_parenthesis(answer, start):
    # Function arguments and arithmetic groups are part of an assertion, not
    # independent prose qualifiers. Unknown or prose syntax remains split.
    close = answer.find(")" if answer[start] == "(" else "）", start + 1)
    if close < 0:
        return False
    inside = answer[start + 1 : close]
    if not re.fullmatch(r"[A-Za-z0-9_α-ωΑ-Ω₀-₉⁰-⁹ᵏⁿ+*/^=<>≤≥−. ,\-]{1,80}", inside):
        return False
    preceding = answer[start - 1] if start else ""
    return bool(re.fullmatch(r"[A-Za-z0-9_α-ωΑ-Ω₀-₉⁰-⁹]", preceding)) or bool(
        re.search(r"[+*/^=<>≤≥−\-]", inside)
    )


def structural_prefix(text):
    text = text.strip()
    return bool(
        re.fullmatch(r"\d+[.)、]", text)
        or text.endswith((":", "："))
        or re.fullmatch(r"(?:#{1,6}\s+.+|\*\*[^*\n]+\*\*)[：:]?", text)
        or _LINK.fullmatch(text.strip("，,：: "))
        or re.fullmatch(
            r"(?:具体来说|具体而言|换句话说|例如|比如|此外|首先|其次|最后|in particular|specifically|for example|in other words|first|next|finally)[，,:： ]*",
            text,
            re.I,
        )
        or re.fullmatch(
            r"(?:根据课程(?:内容)?|(?:课程(?:中)?|老师|教师|教授)(?:指出|说明|强调|提到|说)|according to (?:the )?(?:course|lesson|source))[，,:： ]*",
            text,
            re.I,
        )
        or re.fullmatch(
            r"(?:并|还)?(?:课程|老师|教师|教授|讲者|他|她)?(?:还|也|又)?(?:进一步|接着|随后|继续)?(?:说|说明|强调|指出|提到|解释(?:说)?|总结)[，,:： ]*",
            text,
        )
    )


class AtomicClaim(Contract):
    id: Annotated[str, Field(pattern=r"^a(?:[1-9]|1[0-9]|2[0-4])$")]
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]
    source_text: Annotated[str, Field(min_length=1, max_length=3000)]
    normalized_claim: Annotated[str, Field(min_length=1, max_length=3000)]
    claim_type: Literal["assertion", "qualification"] = "assertion"
    # Context resolves omitted subjects and the scope of a condition/negation;
    # it never substitutes for the exact target span under verification.
    context_start: Annotated[int, Field(ge=0)]
    context_end: Annotated[int, Field(gt=0)]
    context_text: Annotated[str, Field(min_length=1, max_length=3000)]


class AtomicAssessment(AtomicClaim):
    relation: RelationSupport | None = None
    supported: bool
    evidence_ids: Annotated[list[str], Field(max_length=8)]
    fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    model_supported: bool | None = None
    strengthening_guards: Annotated[list[str], Field(max_length=8)] = []

    @model_validator(mode="after")
    def supported_requires_evidence(self):
        if self.supported and not self.evidence_ids:
            raise ValueError("Supported atomic claims require Evidence")
        return self


def atomic_claims(answer):
    """Partition the original Python string; indices are Unicode code points.

    Parenthetical assertions keep their delimiters and cannot hide inside an
    accepted main clause. Quoted literals/code are not cut at their punctuation.
    All non-whitespace characters belong to exactly one verified unit.
    """
    cuts, sentences = {0, len(answer)}, [0]
    quote, parens, index = None, [], 0
    while index < len(answer):
        char = answer[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'`" and not (
            char == "'"
            and index
            and index + 1 < len(answer)
            and answer[index - 1].isalnum()
            and answer[index + 1].isalnum()
        ):
            quote = char
        elif char in "(（":
            if not parens and not expression_parenthesis(answer, index):
                cuts.add(index)
            parens.append((char, index in cuts))
        elif char in ")）" and parens:
            _, split = parens.pop()
            if not parens and split:
                cuts.add(index + 1)
        elif not parens:
            if char in "。！？!?；;\n" or (
                char == "."
                and not (
                    index
                    and index + 1 < len(answer)
                    and answer[index - 1].isdigit()
                    and answer[index + 1].isdigit()
                )
            ):
                cuts.add(index + 1)
                sentences.append(index + 1)
            elif char in ",，" and not (
                index
                and index + 1 < len(answer)
                and answer[index - 1].isdigit()
                and answer[index + 1].isdigit()
            ):
                cuts.add(index + 1)
            else:
                # A connective inside a discourse word is not a clause boundary.
                # Retain the whole marker; the merge below still verifies it
                # together with the following assertion, including qualifiers.
                marker = _DISCOURSE.match(answer, index)
                if marker:
                    index = marker.end() - 1
                    index += 1
                    continue
                match = _LINK.match(answer, index)
                if match:
                    cuts.add(index)
                    index = match.end() - 1
        index += 1

    # Always attach boundary whitespace to the preceding unit. Otherwise a
    # following connective changes an unchanged sentence's exact source_text,
    # making safe revision reuse depend on the deleted clause's syntax.
    def trailing_space(point):
        if point == 0:
            return point
        while point < len(answer) and answer[point].isspace():
            point += 1
        return point

    cuts = {trailing_space(point) for point in cuts}
    sentences = sorted({trailing_space(point) for point in [*sentences, len(answer)]})
    boundaries = sorted(cuts)
    units = []
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        if not re.search(r"\w", answer[start:end]) and units:
            units[-1][1] = end
        elif not re.search(r"\w", answer[start:end]) and not units:
            continue
        else:
            units.append([units[-1][1] if units else 0, end])
    # Formatting and bare discourse markers acquire meaning from the following
    # assertion. Merge their exact spans, never discard or auto-accept wording:
    # a factual heading or a stronger consequence is still fully reviewed.
    index = 0
    while index < len(units) - 1:
        start, end = units[index]
        if structural_prefix(answer[start:end]):
            units[index + 1][0] = start
            units.pop(index)
        else:
            index += 1
    result = []
    for start, end in units:
        text = answer[start:end]
        if not text.strip():
            continue
        context_start = max(point for point in sentences if point <= start)
        context_end = next(point for point in sentences if point >= end)
        result.append(
            dict(
                id=f"a{len(result) + 1}",
                start=start,
                end=end,
                source_text=text,
                normalized_claim=" ".join(text.split()),
                claim_type="qualification"
                if text.lstrip().startswith(("(", "（")) or _LINK.match(text.lstrip())
                else "assertion",
                context_start=context_start,
                context_end=context_end,
                context_text=answer[context_start:context_end],
            )
        )
    if not result or len(result) > MAX_CLAIMS:
        raise ValueError("Answer requires between 1 and 24 exact claim units")
    validate_claims(answer, result)
    return result


def validate_claims(answer, claims):
    cursor = 0
    for index, value in enumerate(claims, 1):
        claim = AtomicClaim.model_validate(value)
        if claim.id != f"a{index}" or not cursor <= claim.start < claim.end <= len(answer):
            raise ValueError("Claim spans must be ordered, unique and within the exact answer")
        if answer[cursor : claim.start].strip():
            raise ValueError("Claim coverage must retain every factual qualifier")
        if answer[claim.start : claim.end] != claim.source_text:
            raise ValueError("candidate[start:end] must equal source_text")
        if claim.normalized_claim != " ".join(claim.source_text.split()):
            raise ValueError("Normalization cannot remove or paraphrase a qualifier")
        if not 0 <= claim.context_start <= claim.start < claim.end <= claim.context_end <= len(answer):
            raise ValueError("Claim context must contain the exact target span")
        if answer[claim.context_start : claim.context_end] != claim.context_text:
            raise ValueError("Claim context must be bound to the same answer")
        cursor = claim.end
    if answer[cursor:].strip():
        raise ValueError("Claim coverage must retain the answer tail")
