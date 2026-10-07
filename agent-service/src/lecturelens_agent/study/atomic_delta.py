"""Run-local reuse of exact, supported claim judgments, with fail-closed binding."""

import hashlib
import json
import re
from collections import Counter
from typing import Annotated, Literal

from pydantic import Field

from ..contracts import Contract
from .atomic import AtomicAssessment, AtomicClaim, atomic_claims

VERSION = "atomic_basis_v2"
SUPPORT_POLICY = "course_relations_v2"
DELTA_MODE = "atomic_delta_support_v1"


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class EvidenceBasis(Contract):
    evidence_id: str
    text_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class AtomicBasis(Contract):
    version: Literal["atomic_basis_v2"] = VERSION
    support_policy: Literal["course_entailment_v1", "course_relations_v1", "course_relations_v2"] | None = (
        None
    )
    answer_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    goal_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    evidence_ids: Annotated[list[str], Field(max_length=8)]
    evidence: Annotated[list[EvidenceBasis], Field(max_length=8)]


class DeltaSummary(Contract):
    reused_ids: Annotated[list[str], Field(max_length=24)] = []
    rechecked_ids: Annotated[list[str], Field(max_length=24)] = []
    reused_from: dict[str, str] = {}
    deleted_fingerprints: Annotated[list[str], Field(max_length=24)] = []
    ledger_reused_ids: Annotated[list[str], Field(max_length=24)] = []
    ledger_fact_ids: dict[str, str] = {}


def basis(body):
    cited = set(body["candidate"]["evidence_ids"])
    return AtomicBasis(
        support_policy=SUPPORT_POLICY if body.get("relation_review") else "course_entailment_v1",
        answer_sha256=digest(body["candidate"]["explanation"]),
        goal_sha256=digest(body["goal"]),
        evidence_ids=sorted(cited),
        evidence=[
            EvidenceBasis(evidence_id=e["evidence_id"], text_sha256=digest(e["text"]))
            for e in body["evidence"]
            if e["evidence_id"] in cited
        ],
    )


def claim_fingerprint(claim, citations):
    # Positions, wire aliases and unrelated citations do not identify a claim.
    # Reuse separately binds the judgment's actual sources and exact hashes.
    return digest(
        {
            **{key: claim[key] for key in ("normalized_claim", "claim_type")},
            "source_text": claim["source_text"].strip(),
        }
    )


def legacy_claim_fingerprint(claim, citations):
    # Retain validation of older checkpoint proofs whose identity included
    # the candidate-wide citation set. They are never rewritten in place.
    return digest(
        {
            **{key: claim[key] for key in ("source_text", "normalized_claim", "claim_type")},
            # Boundary whitespace may move when a neighboring unit is added or
            # removed. Literal/internal whitespace and every qualifier remain.
            "source_text": claim["source_text"].strip(),
            "evidence_ids": sorted(set(citations)),
        }
    )


def context_dependent(claim):
    return claim["claim_type"] == "qualification" or bool(
        re.search(
            r"\b(?:it|its|they|them|their|this|that|these|those)\b|它|他们|它们|其|这个|那个|该|此",
            claim["source_text"],
            re.I,
        )
    )


def _run_delta_plan(body):
    """Recompute the plan from checkpointed observations, never model reuse flags.

    This function is consumed only from the current Run history after the same
    Java authority/revision guard. Evidence view changes also invalidate reuse.
    """
    claims = body["atomic_claims"]
    all_ids = [c["id"] for c in claims]
    prior = body.get("prior_atomic_review")
    empty = ({}, DeltaSummary(rechecked_ids=all_ids))
    if not prior or not prior.get("quality", {}).get("atomic_basis"):
        return empty
    current_basis = basis(body)
    try:
        old_basis = AtomicBasis.model_validate(prior["quality"]["atomic_basis"])
        old_answer = prior["candidate"]["explanation"]
        old_claims = atomic_claims(old_answer)
        old_assessments = [AtomicAssessment.model_validate(c) for c in prior["quality"]["atomic_assessments"]]
    except (ValueError, KeyError, TypeError):
        return empty
    if (
        old_basis.support_policy != current_basis.support_policy
        or old_basis.answer_sha256 != digest(old_answer)
        or old_basis.goal_sha256 != current_basis.goal_sha256
        or set(prior["candidate"]["evidence_ids"]) != set(old_basis.evidence_ids)
    ):
        return empty
    old_by_id = {c["id"]: c for c in old_claims}
    if len(old_assessments) != len(old_claims) or {c.id for c in old_assessments} != set(old_by_id):
        return empty
    by_fingerprint = {}
    old_counts = Counter((c["normalized_claim"], c["claim_type"]) for c in old_claims)
    new_counts = Counter((c["normalized_claim"], c["claim_type"]) for c in claims)
    for check in old_assessments:
        raw = check.model_dump()
        source = old_by_id[check.id]
        if {key: raw[key] for key in AtomicClaim.model_fields} != source:
            return empty
        fingerprint = claim_fingerprint(source, old_basis.evidence_ids)
        if (
            check.fingerprint not in {fingerprint, legacy_claim_fingerprint(source, old_basis.evidence_ids)}
            or len(set(check.evidence_ids)) != len(check.evidence_ids)
            or not set(check.evidence_ids) <= set(old_basis.evidence_ids)
        ):
            return empty
        by_fingerprint[fingerprint] = check
    reused, origins = {}, {}
    old_hashes = {e.evidence_id: e.text_sha256 for e in old_basis.evidence}
    current_hashes = {e.evidence_id: e.text_sha256 for e in current_basis.evidence}
    sources = {e["evidence_id"]: e["text"] for e in body["evidence"]}
    from .strengthening import strengthening_guards

    for claim in claims:
        fingerprint = claim_fingerprint(claim, old_basis.evidence_ids)
        previous = by_fingerprint.get(fingerprint)
        key = (claim["normalized_claim"], claim["claim_type"])
        if (
            previous is None
            or not previous.supported
            or previous.model_supported is not True
            or previous.strengthening_guards
            or not set(previous.evidence_ids) <= set(current_basis.evidence_ids)
            or any(
                old_hashes.get(ref) != current_hashes.get(ref) or ref not in current_hashes
                for ref in previous.evidence_ids
            )
            or old_counts[key] != 1
            or new_counts[key] != 1
            or previous.context_text != claim["context_text"]
            or strengthening_guards(claim, [sources[ref] for ref in previous.evidence_ids])
        ):
            continue
        # New spans are rebound to the current text, including shifted IDs.
        if body.get("relation_review"):
            from .relation_support import validate_relation

            try:
                validate_relation(previous.relation, claim, previous.evidence_ids, sources, True)
            except ValueError:
                continue
        reused[claim["id"]] = AtomicAssessment(
            **claim,
            **previous.model_dump(exclude=set(AtomicClaim.model_fields) | {"fingerprint"}),
            fingerprint=claim_fingerprint(claim, current_basis.evidence_ids),
        )
        origins[claim["id"]] = previous.id
    # Adding an unrelated own citation cannot invalidate an unchanged proof.
    # Every reused judgment still binds its actual cited sources under the
    # current authority/version; removed or changed proof sources recheck.
    current_fingerprints = {claim_fingerprint(c, old_basis.evidence_ids) for c in claims}
    summary = DeltaSummary(
        reused_ids=list(reused),
        rechecked_ids=[key for key in all_ids if key not in reused],
        reused_from=origins,
        deleted_fingerprints=[key for key in by_fingerprint if key not in current_fingerprints],
    )
    return reused, summary


def delta_plan(body):
    reused, plan = _run_delta_plan(body)
    from .ledger import matching_facts

    for key, (assessment, fact_id) in matching_facts(body).items():
        if key not in reused:
            reused[key] = assessment
            plan.ledger_reused_ids.append(key)
            plan.ledger_fact_ids[key] = fact_id
    plan.reused_ids = [c["id"] for c in body["atomic_claims"] if c["id"] in reused]
    plan.rechecked_ids = [c["id"] for c in body["atomic_claims"] if c["id"] not in reused]
    return reused, plan
