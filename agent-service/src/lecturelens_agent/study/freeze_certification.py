"""Certify provisional Atomic support before it can protect revision spans.

The model's true judgment is necessary, never sufficient. A proof must keep
the source's quantity/modal scope and must not turn a comparison or a reduced
subproblem into an unstated choice rule. Dependent clauses inherit a rejected
condition within their sentence. These are negative checks, not entailment.
"""

import re

from .atomic import AtomicAssessment
from .strengthening import _COUNT_HEDGE, _POSSIBLE_COUNT, operation_counts

_CHOICE = re.compile(r"选择|选取|确定|决定|挑选|\b(?:choose|select|decide|determine|pick)\w*\b", re.I)
_ALTERNATIVE = re.compile(
    r"其中一个|一侧|一边|半边|左半|右半|邻居|方向|分支|子数组"
    r"|\b(?:one\s+of|either|side|half|neighbou?r|direction|branch|subarray)\b",
    re.I,
)
_CONDITION = re.compile(
    r"^\s*(?:若|如果|否则|除非|只有|则|因此|所以|由于|因为|\b(?:if|else|unless|only if|then|therefore|because)\b)",
    re.I,
)
_INDEPENDENT = re.compile(
    r"^\s*(?:每次|每一步|随后|接着|另外|此外|同时|\b(?:each|every|next|afterward|furthermore|also)\b)", re.I
)
_GLOBAL = re.compile(
    r"\b(?:all|every|each|always|never|must|inevitably)\b|所有|全部|任何|每个|始终|必然|一定", re.I
)
_WEAK = re.compile(
    r"\b(?:some|sometimes|may|might|could|possibly|potentially)\b|有些|某些|部分|有时|可能|或许", re.I
)
_COMPARATOR = re.compile(
    r"不小于|不大于|大于|小于|高于|低于|≥|≤|(?<![<>=])(?:>=|<=|>|<)(?![<>=])"
    r"|\b(?:greater|less|higher|lower|at least|at most)\b",
    re.I,
)
_HYPOTHETICAL = re.compile(
    r"例如|比如|举例|假设|设想|\b(?:for example|e\.g\.|suppose|hypothetically)\b", re.I
)
BARE_PREDICATE = re.compile(
    r"^\s*(?:不能|可以|允许|必须|需要|分别|只能|仅能|不会|不可|则|那么|直到|除非"
    r"|\b(?:cannot|can't|can|must|may|should|is|are|was|were|has|have|does|then|until|unless)\b)",
    re.I,
)


def _choice_rule(text):
    # Requiring the verb and its alternative in one clause prevents a source
    # about merely choosing an element from licensing a directional decision.
    for clause in re.split(r"[。.!?！？；;，,]", text):
        verb = _CHOICE.search(clause)
        alternative = _ALTERNATIVE.search(clause)
        if verb and alternative and abs(verb.start() - alternative.start()) <= 80:
            return True
    return False


def _possible_count(source, count):
    for match in _POSSIBLE_COUNT.finditer(source):
        if count in operation_counts(match[0]):
            return True
    return False


def _reasons(claim, sources):
    target = claim.source_text
    reasons = []
    # "Possibly/at most two" is not a proof of an unqualified exact two,
    # including when "each step" was extracted into an adjacent Atomic unit.
    if not (_COUNT_HEDGE.search(target) or _HYPOTHETICAL.search(target)) and any(
        _possible_count(source, count) for count in operation_counts(target) for source in sources
    ):
        reasons.append("freeze_count_modality")
    if _choice_rule(target) and not any(_choice_rule(source) for source in sources):
        reasons.append("freeze_choice_relation")
    if (
        _CONDITION.match(target)
        and _COMPARATOR.search(target)
        and not any(_COMPARATOR.search(source) for source in sources)
    ):
        reasons.append("freeze_condition_predicate")
    # An explicit absolute claim cannot inherit authority from a merely
    # possible/sometimes source. Existing Atomic review still decides whether
    # the action and subject actually match; this only blocks a stronger scope.
    if (
        _GLOBAL.search(target)
        and any(_WEAK.search(source) for source in sources)
        and not any(_GLOBAL.search(source) and not _WEAK.search(source) for source in sources)
    ):
        reasons.append("freeze_global_scope")
    return reasons


def certify_assessments(assessments, evidence):
    """Return complete assessments with uncertified claims left editable."""
    certified = []
    for check in assessments:
        sources = [evidence[ref] for ref in check.evidence_ids]
        reasons = _reasons(check, sources) if check.supported else []
        certified.append(
            AtomicAssessment.model_validate(
                {
                    **check.model_dump(),
                    "supported": check.supported and not reasons,
                    "strengthening_guards": list(dict.fromkeys([*check.strengthening_guards, *reasons])),
                }
            )
        )
    # A rejected conditional or decision scope cannot leave its consequent
    # protected merely because Atomic extraction put it in another unit.
    rejected_scope = None
    rejected_head = None
    for index, check in enumerate(certified):
        if rejected_scope != (check.context_start, check.context_end):
            rejected_scope = None
        if rejected_head != (check.context_start, check.context_end):
            rejected_head = None
        if _INDEPENDENT.match(check.source_text):
            rejected_scope = None
            rejected_head = None
        if not check.supported and check.start == check.context_start:
            rejected_head = (check.context_start, check.context_end)
        if not check.supported and (
            _CONDITION.match(check.source_text) or "freeze_choice_relation" in check.strengthening_guards
        ):
            rejected_scope = (check.context_start, check.context_end)
            continue
        if (
            rejected_scope or (rejected_head and BARE_PREDICATE.match(check.source_text))
        ) and check.supported:
            certified[index] = AtomicAssessment.model_validate(
                {
                    **check.model_dump(),
                    "supported": False,
                    "strengthening_guards": [*check.strengthening_guards, "freeze_dependent_scope"],
                }
            )
    return certified
