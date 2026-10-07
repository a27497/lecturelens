"""Run-local, source-constrained revision of rejected atomic spans.

The first candidate and its review are checkpointed before the next decision.
The model proposes replacement text. Before assembly, the server permits only
deletion, literal narrowing, or reuse of an already verified fact/source.
Unproved proposals become deletions. The assembled answer receives full review.
"""

import re
from copy import deepcopy

from .atomic import AtomicAssessment, atomic_claims
from .atomic_delta import digest
from .freeze_certification import BARE_PREDICATE
from .goal_obligations import carries_obligation, freeze_obligations, missing_obligations
from .goals import goal_constraints
from .semantic import review_goal
from .strengthening import _COUNTS, operation_counts, strengthening_guards

_PUNCTUATION = " ,，。.;；:：!?！？()（）\n\t"
_SCOPE = re.compile(
    r"可能|或许|也许|最多|至多|大约|约|只有|仅|只|若|如果|除非|否则|不|没|无|左|右|大于|小于"
    r"|\b(?:may|might|could|possibly|potentially|at most|only|if|unless|not|no|left|right|some)\b",
    re.I,
)
_ATTRIBUTION = re.compile(
    r"^\s*(课程|老师|教师|教授|讲者|the course|the instructor)\s*(?:说|指出|强调|提到|解释|says?|notes?|emphasizes?)",
    re.I,
)
_CONTINUATION = re.compile(r"^\s*(?:并|还|也|and\b|also\b)", re.I)
_OPERATION = re.compile(r"比较|检查|选取|处理|调查|\b(?:compare|check|select|inspect|process)\w*\b", re.I)


class UnfulfilledGoal(ValueError):
    """An obligation cannot survive using the permitted, source-bound edits."""

    def __init__(self, missing):
        super().__init__("Revision cannot publish an incomplete goal")
        self.missing = missing


class InsufficientGoalEvidence(UnfulfilledGoal):
    """A frozen obligation has no compatible current Evidence proof."""


def validate_transaction(transaction):
    if transaction.get("transaction_sha256") != digest(
        {k: v for k, v in transaction.items() if k != "transaction_sha256"}
    ):
        raise ValueError("Frozen revision transaction changed")


def obligation_view(transaction):
    validate_transaction(transaction)
    return [
        {k: v for k, v in o.items() if k != "evidence_hashes"}
        for o in transaction["goal_obligations"]["obligations"]
    ]


def _content(text):
    return "".join(char for char in text if char not in _PUNCTUATION)


def _deletion_only(original, proposed):
    old, new = _content(original), _content(proposed)
    if not new or len(new) >= len(old):
        return False
    remaining = iter(old)
    if not all(any(char == prior for prior in remaining) for char in new):
        return False
    # Removing a condition, negation, direction, or modality can strengthen
    # the remaining words even if every character was present before.
    return all(match.group().lower() in proposed.lower() for match in _SCOPE.finditer(original))


def _source_bound(proposed, sources):
    """Negative preflight; literal narrowing still supplies the positive bound."""
    from .freeze_certification import certify_assessments

    try:
        claims = atomic_claims(proposed)
        source_map = {f"s{index}": source for index, source in enumerate(sources)}
        checks = [
            AtomicAssessment(**claim, supported=True, model_supported=True, evidence_ids=list(source_map))
            for claim in claims
        ]
        checks = certify_assessments(checks, source_map)
    except (ValueError, TypeError):
        return False
    return all(
        check.supported and not strengthening_guards(claim, sources)
        for check, claim in zip(checks, claims, strict=True)
    )


def _known_narrowing(original, guards):
    # Remove only rejected qualifiers. The remaining words still need a
    # current, hash-bound source and the negative preflight checks below.
    def remove(match):
        unit = match.group("unit") or match.group("engunit")
        return unit

    narrowed = original
    if operation_counts(narrowed):
        narrowed = _COUNTS.sub(remove, narrowed)
    if "position_specialization" in guards:
        narrowed = re.sub(
            r"中间|中点|中位|\b(?:middle|midpoint|central)\s+(?=element|item|position)\b",
            "",
            narrowed,
            flags=re.I,
        )
    if "freeze_dependent_scope" in guards:
        # A removed rejected premise cannot justify its branch. A literal
        # consequence can be reconsidered independently only with a frozen
        # obligation, live source preflight, and subsequent atomic review.
        narrowed = re.sub(r"^\s*(?:则|那么|then\b)\s*", "", narrowed, flags=re.I)
    return narrowed


def _bridge(original, following=""):
    stripped = original.strip()
    if stripped.startswith(("（", "(")) and stripped.endswith(("，", ",", "。", ".", "；", ";")):
        return stripped[-1]
    subject = _ATTRIBUTION.match(original)
    if subject and _CONTINUATION.match(following):
        # The rejected predicate is gone; the independently supported next
        # clause retains only its existing grammatical subject.
        return subject.group(1)
    return ""


def freeze_revision(history, semantic, evidence=()):
    prior = next(
        (
            h
            for h in reversed(history)
            if h.get("tool") == "create_explanation"
            and h.get("result", {}).get("quality", {}).get("atomic_basis")
        ),
        None,
    )
    if prior is None:
        return None
    saved = prior["result"].get("revision_transaction")
    if saved is not None:
        validate_transaction(saved)
        if (
            saved["answer"] != prior["arguments"]["explanation"]
            or saved["goal_obligations"]["resolved_goal"] != semantic["resolved_goal"]
            or saved["goal_obligations"]["raw_question"]
            != (semantic.get("raw_question") or semantic["resolved_goal"])
        ):
            raise ValueError("Revision cannot change its frozen answer or learner goal")
        return deepcopy(saved)
    quality = prior["result"]["quality"]
    answer = prior["arguments"]["explanation"]
    if quality["atomic_basis"].get("answer_sha256") != digest(answer):
        return None
    goal_hash = quality["atomic_basis"].get("goal_sha256")
    if goal_hash is not None and goal_hash != digest(
        review_goal(
            {**semantic, "previous_turns": semantic.get("previous_turns", [])},
            "explanation",
        )
    ):
        return None
    claims = atomic_claims(answer)
    try:
        checks = [AtomicAssessment.model_validate(c) for c in quality["atomic_assessments"]]
    except (KeyError, ValueError, TypeError):
        return None
    if len(checks) != len(claims) or {c.id for c in checks} != {c["id"] for c in claims}:
        return None
    by_id = {c.id: c for c in checks}
    for claim in claims:
        check = by_id[claim["id"]]
        if any(getattr(check, key) != value for key, value in claim.items()):
            return None
    supported = [
        c
        for c in claims
        if by_id[c["id"]].supported
        and by_id[c["id"]].model_supported is True
        and not by_id[c["id"]].strengthening_guards
    ]
    rejected = [
        {
            **c,
            "strengthening_guards": by_id[c["id"]].strengthening_guards,
            "evidence_ids": by_id[c["id"]].evidence_ids,
        }
        for c in claims
        if not by_id[c["id"]].supported
    ]
    if not rejected or len(supported) + len(rejected) != len(claims):
        return None
    transaction = {
        "answer": answer,
        "supported": supported,
        "rejected": rejected,
        "required_goals": goal_constraints(semantic.get("raw_question") or semantic["resolved_goal"]),
        "resolved_goal": semantic["resolved_goal"],
        "title": prior["arguments"]["title"],
        "evidence_ids": prior["arguments"]["evidence_ids"],
        "evidence_basis": {
            item["evidence_id"]: item["text_sha256"] for item in quality["atomic_basis"].get("evidence", [])
        }
        if isinstance(quality["atomic_basis"], dict)
        else {},
    }
    transaction["goal_obligations"] = freeze_obligations(semantic, evidence, transaction["evidence_basis"])
    transaction["transaction_sha256"] = digest(transaction)
    return transaction


def validated_edits(rejected_ids, edits):
    if not isinstance(edits, list):
        raise ValueError("Revision edits must be a list")
    if len(edits) != len(rejected_ids) or {e.get("id") for e in edits if isinstance(e, dict)} != set(
        rejected_ids
    ):
        raise ValueError("Every rejected span needs exactly one edit")
    replacements = {}
    for edit in edits:
        if (
            not isinstance(edit, dict)
            or set(edit) != {"id", "replacement"}
            or not isinstance(edit["replacement"], str)
        ):
            raise ValueError("Invalid revision edit")
        if len(edit["replacement"]) > 1000:
            raise ValueError("Revision replacement too long")
        replacements[edit["id"]] = edit["replacement"]
    return replacements


def constrained_edits(transaction, edits, evidence=(), supported_facts=()):
    """Replace unproved model edits with safe deletion before assembly.

    Evidence must be the current authoritative read and match the frozen proof
    hash. A model proposal never turns a provisional claim into a proof.
    """
    validate_transaction(transaction)
    replacements = validated_edits({c["id"] for c in transaction["rejected"]}, edits)
    live = {item["evidence_id"]: item["text"][:1200] for item in evidence}
    proof = transaction.get("evidence_basis", {})
    certified_sources = {key: text for key, text in live.items() if proof.get(key) == digest(text)}
    reusable = {_content(fact["text"]) for fact in supported_facts if fact.get("text")}
    constrained = []
    for claim in transaction["rejected"]:
        original = claim["source_text"]
        following = transaction["answer"][claim["end"] :]
        proposed = replacements[claim["id"]]
        sources = [
            certified_sources[ref] for ref in claim.get("evidence_ids", []) if ref in certified_sources
        ]
        sources = sources or list(certified_sources.values())
        narrowed = _known_narrowing(original, claim.get("strengthening_guards", []))
        dependent = "freeze_dependent_scope" in claim.get("strengthening_guards", [])
        needed = any(carries_obligation(o, narrowed) for o in transaction["goal_obligations"]["obligations"])
        safe_narrowing = bool(
            sources
            and (not dependent or needed)
            and _deletion_only(original, narrowed)
            and _source_bound(narrowed, sources)
        )
        if not proposed.strip(_PUNCTUATION):
            accepted = (
                narrowed
                if safe_narrowing and _OPERATION.search(narrowed)
                else proposed
                if proposed.strip()
                else _bridge(original, following)
            )
        elif _content(proposed) in reusable and _source_bound(proposed, list(certified_sources.values())):
            accepted = proposed
        elif sources and _deletion_only(original, proposed) and _source_bound(proposed, sources):
            accepted = proposed
        else:
            accepted = narrowed if safe_narrowing else _bridge(original, following)
        constrained.append({"id": claim["id"], "replacement": accepted})
    # Deleting/narrowing a rejected clause may also remove a required action.
    # Reconsider only its existing literal words, never fill from surrounding
    # prose or synthesize facts from source/task-shape observations.
    provisional = _assemble(transaction, constrained)
    missing = missing_obligations(transaction["goal_obligations"], provisional)
    for claim, edit in zip(transaction["rejected"], constrained, strict=True):
        narrowed = _known_narrowing(claim["source_text"], claim.get("strengthening_guards", []))
        if not any(carries_obligation(o, narrowed) for o in missing):
            continue
        sources = [
            certified_sources[ref] for ref in claim.get("evidence_ids", []) if ref in certified_sources
        ]
        sources = sources or list(certified_sources.values())
        if sources and _deletion_only(claim["source_text"], narrowed) and _source_bound(narrowed, sources):
            edit["replacement"] = narrowed
            missing = missing_obligations(
                transaction["goal_obligations"], _assemble(transaction, constrained)
            )
    return constrained


def _assemble(transaction, edits):
    replacements = validated_edits({c["id"] for c in transaction["rejected"]}, edits)
    original = transaction["answer"]
    pieces, cursor = [], 0
    for claim in transaction["rejected"]:
        left = original[cursor : claim["start"]]
        replacement = replacements[claim["id"]]
        if replacement.startswith((".", ",", ";", "!", "?", "。", "，", "；", "！", "？")):
            # Keep the existing boundary-formatting contract. Only terminal
            # separators move; protected factual/internal text and its frozen
            # exact provenance remain unchanged.
            left = left.rstrip()
            if replacement.startswith((".", "!", "?", "。", "！", "？")) and left.endswith(
                (",", "，", ";", "；")
            ):
                left = left[:-1]
        pieces.extend((left, replacement))
        cursor = claim["end"]
    pieces.append(original[cursor:])
    return "".join(pieces)


def assemble_revision(transaction, edits, *, evidence=(), supported_facts=(), completion_audit=None):
    edits = constrained_edits(transaction, edits, evidence, supported_facts)
    for claim, edit in zip(transaction["rejected"], edits, strict=True):
        # Removing a sentence's leading clause can orphan its protected
        # predicates. Rechecking true words cannot recover their lost subject
        # or condition; a literal narrowing that retains the binding may.
        remainder = transaction["answer"][claim["end"] : claim["context_end"]]
        if (
            claim["start"] == claim["context_start"]
            and not edit["replacement"].strip(_PUNCTUATION)
            and BARE_PREDICATE.match(remainder)
            and any(
                c["context_start"] == claim["context_start"] and c["start"] >= claim["end"]
                for c in transaction["supported"]
            )
        ):
            raise UnfulfilledGoal(
                [
                    {
                        "id": claim["id"],
                        "kind": "revision_context",
                        "requirement": "Retain the source-bound subject/condition of the remaining predicate.",
                    }
                ]
            )
    answer = _assemble(transaction, edits)
    missing = missing_obligations(transaction["goal_obligations"], answer, evidence)
    if missing:
        from .goal_completion import complete_obligations

        answer, additions, missing, insufficient = complete_obligations(
            transaction,
            answer,
            evidence,
            supported_facts,
            _source_bound,
        )
        if completion_audit is not None:
            completion_audit.extend(additions)
        if missing:
            error = InsufficientGoalEvidence if insufficient else UnfulfilledGoal
            raise error(missing)
    if len(answer) > 1500 or len(answer.strip()) < 10:
        raise ValueError("Assembled revision length invalid")
    # Unsupported replacement can alter the meaning of adjacent text. The
    # normal full review must reassess every extracted claim and goal.
    atomic_claims(answer)
    return {"title": transaction["title"], "explanation": answer, "evidence_ids": transaction["evidence_ids"]}
