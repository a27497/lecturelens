"""Frozen revision requirements; task-shape signals are never support proofs.

These negative coverage checks supplement the independent whole-goal review.
They neither certify a fact nor infer an unstated position or branching rule.
"""

import re

from .atomic_delta import digest
from .explanation_intent import concrete_actions
from .goals import goal_constraints

_COMPARISON = re.compile(r"比较|\bcompar(?:e|es|ing|isons?)\b", re.I)
_OPERANDS = re.compile(r"左右|左.{0,24}右|邻居|相邻|\bleft\b.{0,60}\bright\b|\bneighbou?r\w*\b", re.I)
_INPUT = re.compile(
    r"减半|规模.{0,12}一半|一半.{0,12}(?:输入|子问题)|\bhalv\w*\b|half[ -]siz\w*"
    r"|\b[Tt]\s*\(\s*[A-Za-z]\s*/\s*2\s*\)|t of n over 2|t\(n\)除以2",
    re.I,
)
_STOP = re.compile(
    r"基础情况|基本情况|base[ -]case|\b(?:stops?|until)\b|停止|终止|直到|[Tt]\s*\(\s*1\s*\)", re.I
)
_FEATURES = {
    "comparison_operands": (
        "Name the source-taught compared objects, without adding their position.",
        lambda text: bool(_COMPARISON.search(text) and _OPERANDS.search(text)),
    ),
    "input_change": (
        "Keep the source-taught change of input/subproblem size; do not invent its selection rule.",
        lambda text: bool(_INPUT.search(text)),
    ),
    "stopping_case": (
        "Keep the source-taught stopping/base case and its supported outcome.",
        lambda text: bool(_STOP.search(text)),
    ),
}


def freeze_obligations(semantic, evidence, evidence_basis):
    resolved = semantic["resolved_goal"]
    raw = semantic.get("raw_question") or resolved
    obligations = [
        {"id": c["id"], "kind": "whole_goal", "requirement": c["text"]} for c in goal_constraints(resolved)
    ]
    sources = {
        e["evidence_id"]: e["text"][:1200]
        for e in evidence
        if evidence_basis.get(e["evidence_id"]) == digest(e["text"][:1200])
    }
    # Whole-procedure clarification can inherit its referent, never a new
    # component demand. Explicit component questions remain component-sized.
    component = re.search(r"Θ\s*\(\s*1\s*\)|θ\s*1|常数项|常量项|constant (?:term|cost)", raw, re.I)
    procedural = concrete_actions(raw) and not component
    exclusions = re.findall(
        r"(?:不要|无需|不必|不用|不需要|do not|don't|without)\s*[^，,。.;；]{0,100}",
        raw,
        re.I,
    )
    for kind, (requirement, present) in _FEATURES.items():
        refs = sorted(key for key, text in sources.items() if present(text))
        if not procedural or any(present(text) for text in exclusions) or not (refs or present(raw)):
            continue
        obligations.append(
            dict(
                id="procedure_" + kind,
                kind=kind,
                requirement=requirement,
                evidence_ids=refs,
                evidence_hashes={key: evidence_basis[key] for key in refs},
            )
        )
    return {"raw_question": raw, "resolved_goal": resolved, "obligations": obligations}


def missing_obligations(frozen, answer, evidence=None):
    sources = None if evidence is None else {e["evidence_id"]: digest(e["text"][:1200]) for e in evidence}
    return [
        o
        for o in frozen["obligations"]
        if o["kind"] in _FEATURES
        and (
            not _FEATURES[o["kind"]][1](answer)
            or not o["evidence_ids"]
            or (
                sources is not None
                and not any(sources.get(ref) == o["evidence_hashes"][ref] for ref in o["evidence_ids"])
            )
        )
    ]


def carries_obligation(obligation, text):
    """Lexical shape only: never promote a hit to semantic satisfaction."""
    return obligation["kind"] in _FEATURES and _FEATURES[obligation["kind"]][1](text)
