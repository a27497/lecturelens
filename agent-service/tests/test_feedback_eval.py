import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from lecturelens_agent.study.store import StudyError

script = Path(__file__).resolve().parents[2] / "scripts/eval/evaluate-feedback.py"
spec = importlib.util.spec_from_file_location("feedback_eval", script)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def test_aggregate_call_ledger_counts_failures_and_is_atomic(tmp_path):
    ledger = tmp_path / "ledger.jsonl"

    def reserve(index):
        try:
            evaluation.reserve_call(ledger, str(index), False, limit=3)
            return "reserved"
        except StudyError:
            return "stopped"

    with ThreadPoolExecutor(max_workers=5) as pool:
        outcomes = list(pool.map(reserve, range(5)))
    assert outcomes.count("reserved") == 3
    assert outcomes.count("stopped") == 2
    assert [json.loads(line)["ordinal"] for line in ledger.read_text().splitlines()] == [1, 2, 3]
    with pytest.raises(StudyError):
        evaluation.reserve_call(ledger, "after-restart", True, limit=3)


def test_feedback_evaluation_does_not_relax_authority_scope_or_missing_sources():
    scope = {"owner_id": 1, "course_id": "course", "revision": 1}
    authority = evaluation.FixedEvidence(scope, [{"evidence_id": "e1", "text": "source", "start_ms": 0}])
    with pytest.raises(StudyError):
        authority.read(scope | {"owner_id": 2})
    with pytest.raises(StudyError):
        authority.read(scope, "READ", evidence_ids=["absent"])
    assert authority.read(scope, "READ", evidence_ids=["e1"])["evidence"][0]["text"] == "source"


def test_unlimited_authorization_keeps_existing_ledger_and_finite_caps(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    evaluation.reserve_call(ledger, "original", False, limit=1)
    evaluation.reserve_call(ledger, "authorized-continuation", True, limit=None)
    records = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert [r["ordinal"] for r in records] == [1, 2]
    assert records[0]["case_id"] == "original"
    assert records[1]["purpose"] == "review"
    with pytest.raises(StudyError):
        evaluation.reserve_call(ledger, "finite-cap-still-enforced", False, limit=2)


def test_evaluation_caps_dataset_size_and_rejects_blank_answers():
    data = json.loads((script.parents[2] / "eval/feedback-v1/development.json").read_text())
    assert len(evaluation.validate_cases(data)) == 6
    data["cases"][0]["learner_answer"] = " \n"
    with pytest.raises(ValueError):
        evaluation.validate_cases(data)


def test_replayed_window_matches_java_modality_and_time_order():
    scope = {"owner_id": 1, "course_id": "course", "revision": 1}
    evidence = [
        {"evidence_id": key, "source_type": kind, "start_ms": start, "end_ms": end, "text": key}
        for key, kind, start, end in [
            ("later", "SUBTITLE", 20, 30),
            ("translation", "SUBTITLE_TRANSLATION", 10, 20),
            ("anchor", "SUBTITLE", 10, 20),
            ("earlier", "SUBTITLE", 0, 10),
        ]
    ]
    result = evaluation.FixedEvidence(scope, evidence).read(scope, "WINDOW", evidence_id="anchor")
    assert [e["evidence_id"] for e in result["evidence"]] == ["earlier", "anchor", "later"]
