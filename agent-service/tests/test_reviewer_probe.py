import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def probe_module():
    path = ROOT / "scripts/eval/probe-study-reviewer.py"
    spec = importlib.util.spec_from_file_location("reviewer_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dataset():
    return json.loads((ROOT / "eval/reviewer-probe/cases.json").read_text())


def test_fixed_probe_cases_have_balanced_labels_and_do_not_send_labels():
    probe = probe_module()
    data = dataset()
    cases = probe.validate_cases(data)
    assert len(cases) == 8 and sum(c["expected"]["accept"] for c in cases) == 4
    for case in cases:
        case["expected"]["reason"] = "PRIVATE_LABEL_MUST_NOT_REACH_MODEL"
        case["pair"] = "PRIVATE_PAIR_MUST_NOT_REACH_MODEL"
        encoded = json.dumps(probe.messages_for(case, []))
        assert "PRIVATE_LABEL" not in encoded and "PRIVATE_PAIR" not in encoded
        assert case["id"] not in encoded
        assert json.loads(probe.messages_for(case, [])[-1]["content"])["goal"] == case["goal"]


def test_probe_timeout_cannot_be_scored_as_correct_rejection():
    probe = probe_module()
    data = dataset()
    case = next(c for c in data["cases"] if not c["expected"]["accept"])
    result = probe.summarize(
        data,
        [
            {
                "case_id": case["id"],
                "identity": {"source": "frozen"},
                "status": "failed",
                "seconds": 30,
                "error_code": "MODEL_UNAVAILABLE",
            }
        ],
    )
    assert result["errors"] == 1 and result["correct"] == 0
    assert result["false_accepts"] == result["false_rejects"] == 0
    assert not result["all_labels_matched"]
    assert result["calls_without_complete_usage"] == 1
    assert not any(result["pairs_both_correct"].values())


def test_probe_distinguishes_binary_rejection_from_target_defect_detection():
    probe = probe_module()
    data = dataset()
    rows = [
        {
            "case_id": c["id"],
            "identity": {"source": "frozen"},
            "status": "ok",
            "seconds": 1,
            "response": {"review": {"issues": [] if c["expected"]["accept"] else ["language_mismatch"]}},
            "usage": {"prompt_tokens": 7, "completion_tokens": 2},
        }
        for c in data["cases"]
    ]
    result = probe.summarize(data, rows)
    assert result["correct"] == 8 and result["target_code_hits"] == 0
    assert result["known_prompt_tokens"] == 56
    # Binary agreement alone says nothing about identifying the actual failure.
    assert result["full_l2_gate_assessed"] is False
    rows[0]["response"]["review"]["issues"] = ["incorrect_answer"]
    assert probe.summarize(data, rows)["false_rejects"] == 1


def test_probe_rejects_duplicate_mixed_or_holdout_trials():
    probe = probe_module()
    data = dataset()
    row = {"case_id": data["cases"][0]["id"], "identity": {"source": "one"}, "status": "failed", "seconds": 1}
    with pytest.raises(ValueError, match="Duplicate"):
        probe.summarize(data, [row, row])
    other = {**copy.deepcopy(row), "case_id": data["cases"][1]["id"], "identity": {"source": "two"}}
    with pytest.raises(ValueError, match="Mixed"):
        probe.summarize(data, [row, other])
    data["cases"][0]["split"] = "holdout"
    with pytest.raises(ValueError, match="development"):
        probe.validate_cases(data)


def test_probe_refuses_to_overwrite_prior_records(tmp_path):
    probe = probe_module()
    path = tmp_path / "identity.json"
    probe.write_new(path, {"source": "one"})
    with pytest.raises(FileExistsError):
        probe.write_new(path, {"source": "two"})
    assert json.loads(path.read_text()) == {"source": "one"}


def test_holdout_requires_frozen_candidate_and_new_drafts_and_explicit_split():
    probe = probe_module()
    development = dataset()
    data = copy.deepcopy(development)
    data["frozen_candidate_sha256"] = "frozen-runtime"
    for case in data["cases"]:
        case["split"] = "holdout"
        case["id"] = "new-" + case["id"]
    with pytest.raises(ValueError, match="development"):
        probe.validate_cases(data)
    with pytest.raises(ValueError, match="frozen source"):
        probe.validate_holdout(data, "changed-runtime", development)
    with pytest.raises(ValueError, match="reuses"):
        probe.validate_holdout(data, "frozen-runtime", development)
    for case in data["cases"]:
        key = "title" if case["candidate"]["kind"] == "practice" else "reason"
        case["candidate"][key] += " New task"
    assert len(probe.validate_holdout(data, "frozen-runtime", development)) == 8
    # This guard catches exact reuse, not semantic near-duplicates; report that limitation.
    data["cases"][0]["id"] = development["cases"][0]["id"]
    with pytest.raises(ValueError, match="reuses"):
        probe.validate_holdout(data, "frozen-runtime", development)


def test_new_holdout_cannot_reuse_a_previously_evaluated_holdout():
    probe = probe_module()
    development = dataset()
    previous = copy.deepcopy(development)
    for case in previous["cases"]:
        case["id"] = "previous-" + case["id"]
        case["split"] = "holdout"
        key = "title" if case["candidate"]["kind"] == "practice" else "reason"
        case["candidate"][key] += " Previous holdout"
    current = copy.deepcopy(previous)
    current["frozen_candidate_sha256"] = "new-runtime"
    for case in current["cases"]:
        case["id"] = "new-" + case["id"]
    with pytest.raises(ValueError, match="previously seen"):
        probe.validate_holdout(current, "new-runtime", development, [previous])


def test_goal_probe_raw_accuracy_does_not_inherit_policy_veto():
    spec = importlib.util.spec_from_file_location("method_probe", ROOT / "scripts/eval/probe-method-scope.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = {
        "explanation": {"issue": "none"},
        "question_1": {"issue": "none", "answer_check": {"matches": True}},
        "question_2": {"issue": "none"},
        "goal_checks": [{"matches": True}],
        "explanation_checks": [{"supported": True}],
        "application_method_check": {"matches": True},
    }
    assert module.raw_model_accept(data)
    data["explanation_checks"][0]["supported"] = False
    assert not module.raw_model_accept(data)
    data["explanation_checks"][0]["supported"] = True
    data["goal_checks"][0]["matches"] = False
    assert not module.raw_model_accept(data)
