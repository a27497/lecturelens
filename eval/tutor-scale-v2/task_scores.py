"""Full scheduled denominators plus independently labeled task judgments."""

from records import execution_counts
from shared import agreement, citation_metrics


def assessment(rows, labels, eligible, value):
    units = [r for r in rows if eligible(r)]
    scorable = [r for r in units if r["status"] == "completed"]
    judged = []
    for r in scorable:
        label = labels.get(r["turn_key"], {})
        v = value(r, label) if label.get("complete") else None
        if type(v) is bool:
            judged.append(v)
    positive = sum(judged)
    n = len(judged)
    return dict(
        applicable_planned=len(units),
        scorable_completed=len(scorable),
        assessed=n,
        missing_annotations=len(scorable) - n,
        execution_unscorable=len(units) - len(scorable),
        positive=positive if n else None,
        negative=n - positive if n else None,
        rate_assessed=positive / n if n else None,
        confirmed_positive_over_planned=positive / len(units) if n and units else None,
        status="ANNOTATED_SUBSET" if n else "NOT_RUN",
    )


def citation_inventory_value(r, label, support=False):
    if r["outcome"] not in ("answered", "socratic_prompt"):
        return False
    required = [c for c in label["claims"] if c["requires_citation"]]
    if not required:
        return False
    if not support:
        return all(c["citation_ids"] for c in required)
    supported = {c["claim_id"] for c in label["citation_checks"] if c["label"] == "supported"}
    return all(c["claim_id"] in supported for c in required)


def summarize(run, labels, secondary=None):
    rows = run["rows"]
    secondary = secondary or {}

    def expected_answer(r):
        return not r["script"]["expected_insufficient"]

    task = assessment(rows, labels, lambda r: True, lambda r, label: label.get("task_correct"))
    refusal = assessment(
        rows,
        labels,
        lambda r: r["script"]["expected_insufficient"] or r["outcome"] == "insufficient_evidence",
        lambda r, label: label.get("abstention_correct"),
    )
    expected_refusal = assessment(
        rows,
        labels,
        lambda r: r["script"]["expected_insufficient"],
        lambda r, label: label.get("abstention_correct"),
    )
    context = assessment(
        rows,
        labels,
        lambda r: r["script"]["context_followup"],
        lambda r, label: label.get("context_consistent"),
    )
    inventory = [
        labels[r["turn_key"]]
        for r in rows
        if r["status"] == "completed" and labels.get(r["turn_key"], {}).get("complete")
    ]
    quotes = citation_metrics(inventory)
    quotes["scope"] = "COMPLETED_TURNS_WITH_HUMAN_VERIFIED_CLAIM_INVENTORY_ONLY"
    presence = assessment(rows, labels, expected_answer, lambda r, label: citation_inventory_value(r, label))
    coverage = assessment(
        rows, labels, expected_answer, lambda r, label: citation_inventory_value(r, label, True)
    )
    kind = (run["config"] or {}).get("data_kind", "UNKNOWN")
    pairs = []
    double = []
    for r in rows:
        if not expected_answer(r):
            continue
        human = labels.get(r["turn_key"], {})
        h = human.get("overall_supported") if human.get("complete") and r["status"] == "completed" else None
        # A fake reviewer is never a real independently annotated model/human pair.
        judge = (
            (r.get("review") or {}).get("answer_supported")
            if kind == "REAL" and r["status"] == "completed" and not (r.get("review") or {}).get("error")
            else None
        )
        model = "supported" if judge is True else "unsupported" if judge is False else None
        pairs.append((model, h))
        if r["turn_key"] in secondary:
            other = secondary[r["turn_key"]]
            double.append(
                (
                    h,
                    other.get("overall_supported")
                    if other.get("complete") and r["status"] == "completed"
                    else None,
                )
            )
    counts = execution_counts(rows)
    counts.update(
        annotated_inventory_turns=len(inventory),
        task_assessed_turns=task["assessed"],
        task_missing_annotations=task["missing_annotations"],
    )
    return dict(
        schema="tutor-scale-task-scores-v2",
        data_kind=kind,
        execution=counts,
        quality_status="NOT_RUN"
        if not inventory
        else "MOCK_NOT_QUALITY"
        if kind != "REAL"
        else "ANNOTATED_SUBSET_ONLY",
        task_correctness=task,
        refusal_correctness=refusal,
        expected_abstention_correctness=expected_refusal,
        cross_turn_consistency=context,
        citation_metrics=quotes,
        expected_answer_citation_presence=presence,
        expected_answer_supported_citation_coverage=coverage,
        outcome_counts=dict(
            expected_answer_turns=sum(expected_answer(r) for r in rows),
            expected_abstention_turns=sum(not expected_answer(r) for r in rows),
            abstentions_on_expected_answer=sum(
                expected_answer(r) and r["status"] == "completed" and r["outcome"] == "insufficient_evidence"
                for r in rows
            ),
            uncited_answers_on_expected_answer=sum(
                expected_answer(r)
                and r["status"] == "completed"
                and r["outcome"] in ("answered", "socratic_prompt")
                and not r["citations"]
                for r in rows
            ),
            abstentions_on_expected_abstention=sum(
                not expected_answer(r)
                and r["status"] == "completed"
                and r["outcome"] == "insufficient_evidence"
                for r in rows
            ),
        ),
        model_human_support_agreement=agreement(pairs),
        independent_human_overlap_support_agreement=agreement(double),
        note="No PASS gate. Rates with assessed denominator describe that subset; confirmed/planned is a "
        "conservative lower bound after some labels exist, never imputed human failures. "
        "Execution failure/missing always remains in the planned denominator. "
        "Claim-pair accuracy must be read with both claim and planned-turn coverage.",
    )
