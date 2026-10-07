"""Bound source/answer observations; quote membership never proves entailment."""

from typing import Annotated, Literal

from pydantic import Field

from ..contracts import Contract

POLICY = "course_relations_v2"


class SourceQuote(Contract):
    evidence_id: str
    quote: Annotated[str, Field(min_length=1, max_length=240)]


class RelationSupport(Contract):
    source_relation: Literal["definition", "rule", "procedure", "example", "mixed"]
    grounds: Annotated[list[SourceQuote], Field(max_length=8)]
    claim_quote: Annotated[str, Field(min_length=1, max_length=160)]
    # A model attention cue, never a corrective command or a trusted taxonomy.
    gap: Literal["none", "untaught_property", "omitted_condition", "changed_scope", "reversed_relation"] = (
        "none"
    )


def validate_relation(proof, claim, refs, evidence, supported):
    if proof is None or proof.claim_quote not in claim["source_text"]:
        raise ValueError("Relation proof must quote its exact target claim")
    if (supported and {q.evidence_id for q in proof.grounds} != set(refs)) or not set(refs) <= {
        q.evidence_id for q in proof.grounds
    }:
        raise ValueError("Relation quotes must bind every own cited Evidence ID")
    if supported and proof.gap != "none":
        raise ValueError("A reported support gap cannot certify a supported claim")
    if supported and not proof.grounds:
        raise ValueError("Supported relation requires a source quote")
    if any(q.evidence_id not in evidence or q.quote not in evidence[q.evidence_id] for q in proof.grounds):
        raise ValueError("Relation quotes must occur in their own authorized source")


RELATION_SYSTEM = """
RELATION CONTRACT: Check source relations FIRST, before goal completion. For every exact target return relation={source_relation,grounds,claim_quote,gap} BEFORE supported/evidence_ids. source_relation is definition/rule/procedure/example/mixed. grounds=[{evidence_id,quote}] copies short exact source text (<=240 characters each); claim_quote copies <=160 characters from this TARGET, not another clause. Both are literal strings, not paraphrases. Judge the FULL target in its containing answer sentence, resolving its subject/conditions there. True requires gap=none and grounds for every own evidence_ids item. For false, grounds may quote an own passage that shows the missing support even when evidence_ids=[]; those are rejection observations, not supporting citations. No invented corrections.
Actively identify the gap before judging: none, untaught_property (unstated attribute/metric), omitted_condition (lost prerequisite), changed_scope (wrong subject/variant, generalized example, new restriction or stronger modality), reversed_relation (sufficient/necessary exchanged). Never use a gap label as a proposed factual correction. Only exact answer/source observations guide repair. In goal_checks use AT MOST 3 representative answer_claim_ids, even when there are more checked claims.
A definition/general permission governs its class; a following example does not restrict it unless explicitly required. An example's attributes do not become class properties. (A or B)->C supports B->C; (A and B)->C does not support A->C. Do not exchange if and only-if. A narrower sufficient condition need not list every alternative. Distinguish descriptive implications from procedural instructions: 'if guard, perform action' enables that step under its guard within the taught procedure; preserving that guard is valid without inventing other paths. Earlier stopping does not imply a later action's resource condition; stopping events may coincide. A sequence proves no unstated ranking criterion: mark untaught_property instead of filling a metric from outside knowledge. Not guaranteed does not mean impossible. A counterexample to A->B must satisfy A while B fails, and remain consistent with the source. Learner goals resolve wording but supply no premises. Do not emit free-form explanations for rejected claims.
"""


def review_system(original):
    # Replace duplicated source instructions rather than charging two parallel
    # contracts to every review and correction in the persistent Run budget.
    lines = []
    for line in original.splitlines():
        if line.startswith(("For EACH target,", "Check the actual cited subject,")):
            continue
        if line.startswith("claim_checks: EVERY atomic_claims") and "Preserve quantity" in line:
            line = (
                "claim_checks: Every offered target exactly once, no reused IDs/course_fact. "
                "Judge the FULL candidate.explanation[start:end] (Unicode offsets); "
                "resolve its subject/conditions using context_start:context_end. "
                "All source IDs must be allowed candidate-owned IDs. "
                + line[line.index("Preserve quantity") :]
            )
        lines.append(line)
    return RELATION_SYSTEM + "\n".join(lines)
