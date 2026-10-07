"""Extractive completion of missing frozen requirements, never a support verdict.

Current hash-bound Evidence may supply a literal quotation for final review.
An extraction is provisional: it cannot authorize publication or enter Ledger
until the ordinary Atomic, Evidence and whole-goal checks accept it.
"""

import json
import re

from .atomic_delta import digest
from .goal_obligations import carries_obligation, missing_obligations
from .ledger import valid_fact


def source_sentences(text):
    """Preserve a whole sentence's qualifiers and exact source offsets."""
    start = 0
    for boundary in re.finditer(r"[。！？!?\n]|(?<!\d)\.|\.(?!\d)", text):
        end = boundary.end()
        if text[start:end].strip():
            yield start, end, text[start:end]
        start = end
    if text[start:].strip():
        yield start, len(text), text[start:]


def complete_obligations(transaction, answer, evidence, facts, preflight):
    """Append only missing requirements; return proof spans and unresolved kinds.

    A missing wording obligation is not evidence insufficiency. Only absence
    of its frozen, live proof allows refusal. Extraction failure with live
    proof instead stops without converting that failure into an abstention.
    """
    live = {e["evidence_id"]: e["text"][:1200] for e in evidence}
    basis = transaction["evidence_basis"]
    live = {ref: text for ref, text in live.items() if basis.get(ref) == digest(text)}
    additions, insufficient = [], []
    for obligation in missing_obligations(transaction["goal_obligations"], answer, evidence):
        refs = [
            ref
            for ref in obligation.get("evidence_ids", [])
            if ref in live and obligation["evidence_hashes"].get(ref) == digest(live[ref])
        ]
        refs = [ref for ref in refs if carries_obligation(obligation, live[ref])]
        if not refs:
            insufficient.append(obligation)
            continue
        chosen = None
        for fact in facts:
            verified = valid_fact(fact, fact)
            verified = verified.model_dump() if verified else None
            if (
                verified
                and carries_obligation(obligation, verified["text"])
                and all(
                    ref in live and verified["evidence_hashes"].get(ref) == digest(live[ref])
                    for ref in verified["evidence_ids"]
                )
                and set(verified["evidence_ids"]) & set(refs)
                and preflight(verified["text"], [live[ref] for ref in verified["evidence_ids"]])
            ):
                chosen = dict(
                    text=verified["text"],
                    fact_id=verified["fact_id"],
                    evidence_ids=verified["evidence_ids"],
                    evidence_hashes=verified["evidence_hashes"],
                )
                break
        if chosen is None:
            # Quoting the entire sentence preserves conditions, modality and
            # quantities. No inference/paraphrase is licensed by a feature
            # match; the independent reviewer must establish sufficiency.
            for ref in live:
                if ref not in refs:
                    continue
                spans = sorted(source_sentences(live[ref]), key=lambda s: (len(s[2]), s[0]))
                for start, end, literal in spans:
                    text = "课程原文：" + json.dumps(literal.strip(), ensure_ascii=False) + "。"
                    if (
                        carries_obligation(obligation, literal)
                        and len(text) <= 600
                        and preflight(text, [live[ref]])
                    ):
                        chosen = dict(
                            text=text,
                            source_text=literal,
                            start=start,
                            end=end,
                            evidence_ids=[ref],
                            evidence_hashes={ref: digest(live[ref])},
                        )
                        break
                if chosen is not None:
                    break
        if chosen is not None:
            answer += "\n" + chosen["text"]
            additions.append(dict(obligation_id=obligation["id"], **chosen))
    missing = missing_obligations(transaction["goal_obligations"], answer, evidence)
    return answer, additions, missing, insufficient
