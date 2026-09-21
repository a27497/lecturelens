import importlib.util
from pathlib import Path

import pytest


def report_module():
    path = Path(__file__).resolve().parents[2] / "scripts/eval/report-study.py"
    spec = importlib.util.spec_from_file_location("study_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_eval_keeps_timeouts_in_quantiles_and_requires_semantic_review():
    cases = [{"id": "ok", "expected_outcome": "practice"}, {"id": "timeout", "expected_outcome": "practice"}]
    rows = [
        {
            "case_id": "ok",
            "run": {"status": "succeeded"},
            "artifact": {"questions": [{}, {}], "citations": [{}]},
            "elapsed_seconds": 15,
            "provenance_valid": True,
        },
        {
            "case_id": "timeout",
            "run": {"status": "budget_exceeded"},
            "artifact": None,
            "elapsed_seconds": 90.5,
            "provenance_valid": False,
        },
    ]
    result = report_module().summarize(cases, rows, {})
    assert result["p95_all_seconds"] == 90.5
    assert result["semantic_supported_pass"] == 0 and result["structure_pass"] == 1
    assert not result["passed"] and result["gates"]["complete"]
    assert not report_module().summarize(cases, rows[:1], {})["gates"]["complete"]


def test_eval_does_not_count_unrelated_practice_as_abstention():
    cases = [{"id": "absent", "expected_outcome": "insufficient_evidence"}]
    rows = [
        {
            "case_id": "absent",
            "run": {"status": "succeeded"},
            "artifact": {"kind": "practice", "questions": [{}, {}], "citations": [{}]},
            "elapsed_seconds": 10,
            "provenance_valid": True,
        }
    ]
    reviews = {"absent": {"reviewer": "test reviewer", "reason": "Unsupported topic", "grounded": True}}
    result = report_module().summarize(cases, rows, reviews)
    assert result["insufficient_pass"] == 0 and not result["passed"]


def test_eval_cannot_hide_a_serious_unsupported_answer_in_aggregate_pass_rate():
    cases = [{"id": str(i), "expected_outcome": "practice"} for i in range(10)]
    rows = [
        {
            "case_id": case["id"],
            "run": {"status": "succeeded"},
            "artifact": {"questions": [{}, {}], "citations": [{}]},
            "elapsed_seconds": 10,
            "provenance_valid": True,
        }
        for case in cases
    ]
    reviews = {
        case["id"]: {
            "reviewer": "test",
            "reason": "reviewed",
            "grounded": True,
            "answers_correct": True,
            "questions_distinct": True,
            "serious_unsupported": False,
        }
        for case in cases
    }
    assert report_module().summarize(cases, rows, reviews)["passed"]
    reviews["0"].update(grounded=False, serious_unsupported=True)
    result = report_module().summarize(cases, rows, reviews)
    assert result["semantic_supported_pass"] == 9
    assert not result["gates"]["no_serious_unsupported"] and not result["passed"]


def test_eval_rejects_mixed_candidates_and_changed_dataset():
    report = report_module()
    baseline = {"dataset_sha256": "frozen", "runtime": {"source_sha256": "baseline", "deadline": 90}}
    candidate = {"dataset_sha256": "frozen", "runtime": {"source_sha256": "candidate", "deadline": 90}}
    report.validate_cohort([baseline], "frozen")
    with pytest.raises(AssertionError, match="Mixed"):
        report.validate_cohort([baseline, candidate], "frozen")
    with pytest.raises(AssertionError, match="Dataset"):
        report.validate_cohort([baseline], "edited")


def test_managed_pilot_rejects_holdouts_and_duplicate_cases(tmp_path):
    import json

    path = Path(__file__).resolve().parents[2] / "scripts/eval/pilot-managed-study.py"
    spec = importlib.util.spec_from_file_location("managed_pilot_validation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dataset = tmp_path / "cases.json"
    dataset.write_text(json.dumps({"cases": [{"id": "a", "split": "holdout"}]}))
    with pytest.raises(ValueError, match="development"):
        module.pilot_cases(dataset)
    dataset.write_text(json.dumps({"cases": [{"id": "a", "split": "development"}] * 2}))
    with pytest.raises(ValueError, match="uniquely"):
        module.pilot_cases(dataset)


def test_seeded_repair_uses_observed_aliases_then_delegates_review_and_repair():
    import json

    from test_study_quality import review_input

    path = Path(__file__).resolve().parents[2] / "scripts/eval/pilot-managed-study.py"
    spec = importlib.util.spec_from_file_location("seeded_pilot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Delegate:
        def decide(self, messages, timeout):
            return {"name": "real_repair_decision", "usage": {"completion_tokens": 9}}

        def review(self, messages, timeout):
            return {"review": {"issues": ["incorrect_answer"]}, "usage": {"completion_tokens": 5}}

    body = review_input()
    candidate = body["candidate"]
    evidence = [
        {"evidence_id": "e1", "start_ms": 0, "end_ms": 1},
        {"evidence_id": "e2", "start_ms": 1, "end_ms": 2},
    ]
    calls = []
    provider = module.SeededRunProvider(Delegate(), candidate, evidence, calls)

    def messages(context):
        return [{"role": "user", "content": json.dumps(context)}]

    assert (
        provider.decide(messages({"goal": "Explain", "history": []}), 1)["name"] == "search_course_evidence"
    )
    context = {
        "history": [{"tool": "search_course_evidence"}],
        "evidence": [
            {"evidence_id": "e7", "start_ms": 0, "end_ms": 1},
            {"evidence_id": "e8", "start_ms": 1, "end_ms": 2},
        ],
    }
    seeded = provider.decide(messages(context), 1)
    assert seeded["arguments"]["questions"][1]["evidence_ids"] == ["e8"]
    assert candidate["questions"][1]["evidence_ids"] == ["e2"]
    assert provider.review(messages(body), 1)["review"]["issues"] == ["incorrect_answer"]
    context["history"].append({"tool": "create_practice_set"})
    # A fresh adapter after a checkpoint still delegates; it does not re-inject the seed.
    restored = module.SeededRunProvider(Delegate(), candidate, evidence, calls)
    assert restored.decide(messages(context), 1)["name"] == "real_repair_decision"
    assert [call["seeded"] for call in calls] == [True, True, False, False]
    assert calls[-1]["usage"]["completion_tokens"] == 9
    context["history"].pop()
    context["evidence"].pop()
    with pytest.raises(ValueError, match="absent"):
        provider.decide(messages(context), 1)


def test_seeded_pilot_rejects_unbounded_or_nonpractice_seeds(tmp_path):
    import json

    from test_study_quality import review_input

    path = Path(__file__).resolve().parents[2] / "scripts/eval/pilot-managed-study.py"
    spec = importlib.util.spec_from_file_location("seeded_pilot_limits", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    candidate = review_input()["candidate"] | {"title": "Seeded example"}
    cases = [{"id": str(i), "split": "development", "candidate": candidate} for i in range(3)]
    dataset = tmp_path / "cases.json"
    dataset.write_text(json.dumps({"cases": cases}))
    with pytest.raises(ValueError, match="at most two"):
        module.pilot_cases(dataset, seeded=True)
    cases = cases[:1]
    cases[0]["candidate"] = {"kind": "insufficient_evidence", "reason": "unsupported"}
    dataset.write_text(json.dumps({"cases": cases}))
    with pytest.raises(ValueError, match="practice"):
        module.pilot_cases(dataset, seeded=True)


def test_seeded_pilot_retains_failed_review_arguments_redacts_key_and_restores_client():
    import json
    from types import SimpleNamespace

    from test_study_quality import accepted_verdict, review_input

    from lecturelens_agent.study.provider import ChatProvider, ModelResponseError

    path = Path(__file__).resolve().parents[2] / "scripts/eval/pilot-managed-study.py"
    spec = importlib.util.spec_from_file_location("seeded_pilot_wire", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client = ChatProvider("http://127.0.0.1:9/v1", "test", "private-test-key")
    args = accepted_verdict()
    args["answer_checks"][0]["evidence"] = ["unknown"]
    args["answer_checks"][0]["answer"] = "private-test-key"
    wire = {
        "calls": [{"name": "assess_study_candidate", "arguments": args}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10},
    }
    client._request = lambda *args, **kwargs: wire
    original = client._request
    delegate = SimpleNamespace(clients={"review": client}, review=client.review)
    calls = []
    provider = module.SeededRunProvider(delegate, {}, [], calls)
    with pytest.raises(ModelResponseError, match="MODEL_REVIEW_CONTRACT"):
        provider.review([{"role": "user", "content": json.dumps(review_input())}], 10)
    assert client._request is original
    assert len(calls) == 1 and calls[0]["status"] == "failed"
    assert calls[0]["wire_responses"][0]["calls"][0]["arguments"]["answer_checks"][0]["evidence"] == [
        "unknown"
    ]
    assert calls[0]["usage"] == wire["usage"]
    assert calls[0]["diagnostics"]["stage"] == "review_schema"
    assert "private-test-key" not in json.dumps(calls)
    assert args["answer_checks"][0]["answer"] == "private-test-key"  # Recording does not mutate the trial.


def test_ordinary_recorded_pilot_does_not_inject_search_or_a_candidate():
    import json
    from types import SimpleNamespace

    path = Path(__file__).resolve().parents[2] / "scripts/eval/pilot-managed-study.py"
    spec = importlib.util.spec_from_file_location("ordinary_recording", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    delegated = []

    def decide(messages, timeout):
        delegated.append(messages)
        return {"name": "model_selected_tool", "usage": {"completion_tokens": 2}}

    calls = []
    provider = module.RecordedRunProvider(SimpleNamespace(decide=decide), None, [], calls)
    for history in [[], [{"tool": "search_course_evidence"}]]:
        result = provider.decide([{"role": "user", "content": json.dumps({"history": history})}], 1)
        assert result["name"] == "model_selected_tool"
    assert len(delegated) == 2 and all(not call["seeded"] for call in calls)


def test_recording_keeps_invalid_argument_json_privately_and_restores_observer(monkeypatch):
    import json
    from types import SimpleNamespace

    import httpx

    from lecturelens_agent.study.provider import ChatProvider, ModelResponseError

    path = Path(__file__).resolve().parents[2] / "scripts/eval/pilot-managed-study.py"
    spec = importlib.util.spec_from_file_location("raw_recording", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wire = {
        "usage": {"prompt_tokens": 21, "completion_tokens": 9},
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "search_course_evidence",
                                "arguments": '{"query":"private-key\ninvalid newline"}',
                            },
                        }
                    ],
                }
            }
        ],
    }
    factory = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: factory(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=wire)),
            **kwargs,
        ),
    )
    client = ChatProvider("http://127.0.0.1:9/v1", "test", "private-key")
    calls = []
    provider = module.RecordedRunProvider(
        SimpleNamespace(clients={"decision": client}, decide=client.decide), None, [], calls
    )
    with pytest.raises(ModelResponseError, match="MODEL_TOOL_CONTRACT"):
        provider.decide([{"role": "user", "content": '{"goal":"test"}'}], 1)
    assert calls[0]["diagnostics"]["reason"] == "arguments_json"
    assert len(calls[0]["raw_responses"]) == 1 and calls[0]["wire_responses"] == []
    assert "private-key" not in json.dumps(calls)
    assert "[REDACTED]" in calls[0]["raw_responses"][0]
    assert client.response_observer is None
