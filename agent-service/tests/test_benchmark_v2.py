"""Mechanics use hand-computed toy ranks; heldout queries are not executed here."""

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from lecturelens_agent.benchmark.core import retrieval_metrics
from lecturelens_agent.benchmark_v2.run import write
from lecturelens_agent.benchmark_v2.statistics import (
    bootstrap_weights,
    course_sign_flip,
    failure_buckets,
    latency_interval,
    mean_interval,
    report,
    validate_v2,
    wilson,
)

DATA = Path(__file__).resolve().parents[2] / "eval/retrieval-v2"


def toy_cases():
    return [
        {"course": "a", "family": "first"},
        {"course": "a", "family": "first"},
        {"course": "a", "family": "second"},
        {"course": "b", "family": "third"},
    ]


def test_dataset_plan_integrity_without_scoring_real_queries():
    corpus = json.loads((DATA / "corpus.json").read_text())
    cases = json.loads((DATA / "cases.json").read_text())
    plan = json.loads((DATA / "split-plan.json").read_text())
    validate_v2(corpus, cases, plan)
    assert len(cases["cases"]) == 120
    assert sum(c["split"] == "holdout" for c in cases["cases"]) == 40
    assert sum(c.get("cross_lecture", False) for c in cases["cases"]) == 24
    assert sum(c["language"] == "zh" for c in cases["cases"]) == 60
    assert sum(not c["answerable"] for c in cases["cases"]) == 24
    assert cases["annotation"]["human_annotators"] == 0
    assert sum(len(c["evidence"]) for c in corpus["courses"].values()) == 735


@pytest.mark.parametrize("fault", ["split", "query", "lecture", "fact"])
def test_invalid_split_duplicate_or_false_cross_lecture_is_rejected(fault):
    corpus = json.loads((DATA / "corpus.json").read_text())
    cases = json.loads((DATA / "cases.json").read_text())
    plan = json.loads((DATA / "split-plan.json").read_text())
    if fault == "split":
        plan["holdout_courses"].append("algorithms")
    elif fault == "query":
        cases["cases"][1]["query"] = cases["cases"][0]["query"]
    elif fault == "fact":
        cases["cases"][0]["aspects"][0]["required_fact"] = ""
    else:
        cross = next(c for c in cases["cases"] if c.get("cross_lecture"))
        cross["aspects"][1] = copy.deepcopy(cross["aspects"][0])
    with pytest.raises(ValueError):
        validate_v2(corpus, cases, plan)


def test_bootstrap_is_deterministic_and_never_splits_a_family():
    cases = toy_cases()
    a = bootstrap_weights(cases, 100, 17)
    assert np.array_equal(a, bootstrap_weights(cases, 100, 17))
    assert np.array_equal(a[:, 0], a[:, 1])
    assert set(a[:, 3]) == {1}  # One fixed-course family cannot vanish.
    hierarchical = bootstrap_weights(cases, 100, 17, courses=True)
    assert 0 in hierarchical[:, 3]  # Whole course may be absent, never an unpaired method draw.


def test_hand_computed_paired_constant_effect_and_ci():
    weights = bootstrap_weights(toy_cases(), 200, 23, courses=True)
    result = mean_interval([0.25, 0.25, 0.25, 0.25], weights)
    assert result == {"estimate": 0.25, "ci": [0.25, 0.25], "n": 4}
    assert mean_interval([0, 0, 0, 0], weights)["ci"] == [0, 0]
    assert course_sign_flip([0.25] * 4, toy_cases()) == 0.5
    assert course_sign_flip([0] * 4, toy_cases()) == 1


def test_hand_calculated_latency_linear_percentile_and_wilson():
    weights = np.ones((10, 4), dtype=int)
    assert latency_interval([10, 20, 30, 40], weights, 0.95) == {
        "estimate_ms": 38.5,
        "ci95_ms": [38.5, 38.5],
        "n": 4,
    }
    bounds = wilson(8, 8)
    assert bounds[0] == pytest.approx(0.6755924351161198)
    assert bounds[1] == pytest.approx(1)
    assert wilson(0, 0) is None


def case():
    return {
        "answerable": True,
        "aspects": [{"evidence_ids": ["a", "a-zh"]}, {"evidence_ids": ["b"]}],
        "hard_negative_ids": ["wrong"],
    }


LOOKUP = {k: {"equivalence_group": "a" if k == "a-zh" else k} for k in ["a", "a-zh", "b", "noise", "wrong"]}


def row(*ids):
    return {"hits": [{"evidence_id": eid} for eid in ids]}


def test_hand_counted_gold_id_recall_differs_from_fact_coverage():
    values = retrieval_metrics(["a", "a-zh", "noise"], case(), 3)
    assert values["recall"] == 2 / 3
    assert values["evidence_coverage"] == 0.5
    assert failure_buckets(row("a", "a-zh", "noise", "b"), case(), LOOKUP) == [
        "ranked_below_context",
        "original_translation_duplicate",
    ]


def test_missing_aspect_and_hard_negative_tags_remain_diagnostic():
    assert failure_buckets(row("wrong", "noise", "a"), case(), LOOKUP) == [
        "not_recalled_in_candidates",
        "hard_negative_in_context",
    ]
    assert failure_buckets(row("a", "b"), case(), LOOKUP) == []
    assert failure_buckets({**row(), "error_type": "TimeoutError"}, case(), LOOKUP) == ["retrieval_error"]


def test_no_answer_is_not_manufactured_recall_or_reader_refusal():
    absent = {"answerable": False}
    assert retrieval_metrics(["a"], absent, 3) is None
    assert failure_buckets(row("a"), absent, LOOKUP) == ["no_answer_candidate_returned"]
    assert failure_buckets(row(), absent, LOOKUP) == []


def test_duplicate_or_missing_observations_rejected_before_aggregation():
    cases = {"cases": [{"id": "toy"}]}
    with pytest.raises(ValueError, match="Missing, duplicate"):
        report([], cases, {}, {})
    with pytest.raises(ValueError, match="Missing, duplicate"):
        report([{"case_id": "toy", "strategy": "dense"}] * 2, cases, {}, {})


def test_holdout_reservation_is_exclusive_and_not_replaced(tmp_path):
    ledger = tmp_path / "holdout-attempt.json"
    write(ledger, {"reserved": True, "freeze": "first"})
    with pytest.raises(FileExistsError):
        write(ledger, {"reserved": True, "freeze": "second"})
    assert json.loads(ledger.read_text()) == {"reserved": True, "freeze": "first"}
