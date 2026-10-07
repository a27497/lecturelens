import copy
import json
from contextlib import contextmanager

import httpx
import pytest
from test_study import read, setup, start  # noqa: F401

from lecturelens_agent.study.provider import ChatProvider, ModelResponseError
from lecturelens_agent.study.quality import review_messages as current_review_messages
from lecturelens_agent.study.quality import review_schema
from lecturelens_agent.study.review_diagnostics import contract_detail
from lecturelens_agent.study.telemetry import _span


@pytest.fixture(autouse=True)
def legacy_answer_review(monkeypatch):
    monkeypatch.setattr("lecturelens_agent.study.runtime.review_messages", review_messages)


def review_messages(*args, **kwargs):
    """Historical v1 contract/replay regression; atomic default is tested separately."""
    return current_review_messages(*args, **kwargs, answer_review_mode="answer_support_v1")


KEY = "private-api-key-sentinel"
SESSION = "private-t4-diagnostic-session"
_HTTP_CLIENT = httpx.Client


def messages():
    return review_messages(
        "Explain stopping.",
        {
            "kind": "explanation",
            "title": "Stopping",
            "explanation": "An algorithm needs a stopping condition.",
            "evidence_ids": ["canonical"],
        },
        [{"evidence_id": "canonical", "text": "An algorithm needs a stopping condition."}],
    )


def valid():
    return {
        "goal_checks": [
            {
                "id": "g1",
                "observation": "It explains stopping.",
                "matches": True,
                "answer_quotes": ["An algorithm needs a stopping condition."],
            }
        ],
        "explanation_checks": [
            {
                "id": "x1",
                "course_fact": "Algorithms need a stopping condition.",
                "evidence_ids": ["e1"],
                "supported": True,
            }
        ],
    }


@contextmanager
def scoped(monkeypatch, enabled=True):
    if enabled:
        monkeypatch.setenv("AGENT_PRIVATE_REVIEW_TELEMETRY_SESSION", SESSION)
    token = _span.set({"session_id": SESSION})
    try:
        yield
    finally:
        _span.reset(token)


def mock_provider(monkeypatch, verdict):
    recorded = []
    client = _HTTP_CLIENT

    def handle(request):
        recorded.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "assess_study_candidate",
                                        "arguments": json.dumps(verdict),
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(handle), **kwargs)
    )
    return ChatProvider("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3-max", KEY), recorded


@pytest.mark.parametrize(
    "fault,message,path",
    [
        (
            "citation",
            "Answer claims require their own observed citations",
            ["explanation_checks", 0, "evidence_ids", 0],
        ),
        ("quote", "Goal support must quote the actual answer", ["goal_checks", 0, "answer_quotes", 0]),
        ("type", "Input should be a valid boolean", ["goal_checks", 0, "matches"]),
        ("null", "Input should be a valid list", ["goal_checks", 0, "answer_quotes"]),
        ("missing", "Field required", ["explanation_checks", 0, "supported"]),
        ("extra", "Extra inputs are not permitted", ["unsupported"]),
        ("ids", "Check every answer sentence exactly once", []),
    ],
)
def test_exact_validator_failure_is_private_without_changing_request(monkeypatch, fault, message, path):
    verdict = valid()
    if fault == "citation":
        verdict["explanation_checks"][0]["evidence_ids"] = ["e9"]
    if fault == "quote":
        verdict["goal_checks"][0]["answer_quotes"] = ["A paraphrase that is not in the answer."]
    if fault == "type":
        verdict["goal_checks"][0]["matches"] = "true"
    if fault == "null":
        verdict["goal_checks"][0]["answer_quotes"] = None
    if fault == "missing":
        del verdict["explanation_checks"][0]["supported"]
    if fault == "extra":
        verdict["unsupported"] = False
    if fault == "ids":
        verdict["explanation_checks"].append(copy.deepcopy(verdict["explanation_checks"][0]))
    provider, recorded = mock_provider(monkeypatch, verdict)
    with scoped(monkeypatch), pytest.raises(ModelResponseError) as failure:
        provider.review(messages(), 10)
    detail = failure.value.private_diagnostics["review_contract"]
    assert failure.value.code == "MODEL_REVIEW_CONTRACT"
    assert detail["calls"][0]["arguments"] == (
        verdict if fault != "extra" else {**valid(), "unsupported": "[REDACTED_UNDECLARED_FIELD]"}
    )
    assert any(message in e["message"] for e in detail["validator_errors"])
    if fault in {"citation", "quote"}:
        assert detail["validator_errors"][0]["path"] == []
        assert detail["binding_observations"][0]["path"] == path
    else:
        assert detail["validator_errors"][0]["path"] == path
    assert recorded[0]["tools"] == [review_schema("explanation", review_mode="answer_support_v1")]
    assert recorded[0]["messages"] == messages()
    assert "review_contract" not in json.dumps(failure.value.diagnostics)


def test_telemetry_is_disabled_outside_the_whitelisted_session(monkeypatch):
    verdict = valid()
    verdict["explanation_checks"][0]["evidence_ids"] = ["outside"]
    provider, _ = mock_provider(monkeypatch, verdict)
    monkeypatch.setenv("AGENT_PRIVATE_REVIEW_TELEMETRY_SESSION", "another-session")
    with scoped(monkeypatch, enabled=False), pytest.raises(ModelResponseError) as error:
        provider.review(messages(), 10)
    assert "review_contract" not in error.value.private_diagnostics


def test_success_telemetry_does_not_change_the_verdict(monkeypatch):
    provider, _ = mock_provider(monkeypatch, valid())
    with scoped(monkeypatch):
        response = provider.review(messages(), 10)
    assert response["review"]["issues"] == []
    assert response["private_review_contract"]["validator_errors"] == []


def test_failed_observation_cannot_change_success_or_failure(monkeypatch):
    import lecturelens_agent.study.review_diagnostics as diagnostic

    def fail(*args, **kwargs):
        raise RuntimeError("private-error-sentinel")

    monkeypatch.setattr(diagnostic, "contract_detail", fail)
    provider, _ = mock_provider(monkeypatch, valid())
    with scoped(monkeypatch):
        assert provider.review(messages(), 10)["review"]["issues"] == []
    bad = valid()
    bad["explanation_checks"][0]["evidence_ids"] = ["outside"]
    provider, _ = mock_provider(monkeypatch, bad)
    with scoped(monkeypatch), pytest.raises(ModelResponseError) as error:
        provider.review(messages(), 10)
    assert error.value.code == "MODEL_REVIEW_CONTRACT"
    assert "private-error-sentinel" not in json.dumps(error.value.private_diagnostics)


def test_large_malformed_arguments_are_bounded_and_secrets_are_redacted(monkeypatch):
    body = json.loads(messages()[-1]["content"])
    arguments = valid()
    arguments["goal_checks"][0]["observation"] = (KEY + " Bearer auth-sentinel " + "x" * 10000) * 50
    arguments.update(
        api_key=KEY, cookie="private-cookie", unrelated_user={"email": "private-user@example.com"}
    )
    arguments["explanation_checks"] *= 100
    monkeypatch.setenv("QA_AUTH_TOKEN", "private-auth-token")
    arguments["goal_checks"][0]["answer_quotes"] = ["private-auth-token"]
    detail = contract_detail(
        body,
        [{"name": "assess_study_candidate", "arguments": arguments}],
        review_schema("explanation", review_mode="answer_support_v1"),
        secrets=(KEY,),
    )
    serialized = json.dumps(detail)
    for secret in (KEY, "auth-sentinel", "private-cookie", "private-user@example.com", "private-auth-token"):
        assert secret not in serialized
    assert len(serialized.encode()) <= 24 * 1024
    assert detail["truncated_paths"]


def test_operator_only_persistence_and_public_event_exclusion(setup, monkeypatch):  # noqa: F811
    store, _, runtime, scope = setup
    original = runtime.provider.decide

    def decide(messages, timeout):
        context = json.loads(messages[-1]["content"])
        if not context["evidence"]:
            return original(messages, timeout)
        return {
            "name": "create_explanation",
            "arguments": {
                "title": "Stopping",
                "explanation": "An algorithm needs a stopping condition.",
                "evidence_ids": ["e1"],
            },
        }

    runtime.provider.decide = decide
    bad = valid()
    bad["explanation_checks"][0]["evidence_ids"] = ["e999"]
    provider, _ = mock_provider(monkeypatch, bad)
    runtime.provider.review = provider.review
    monkeypatch.setenv("AGENT_PRIVATE_REVIEW_TELEMETRY_SESSION", scope["session_id"])
    run = start(setup)
    runtime.execute(run)
    assert read(setup)["run"]["error_code"] == "MODEL_REVIEW_CONTRACT"
    public = json.dumps(read(setup, "EVENTS"))
    assert "review_contract" not in public and "e999" not in public
    with store.connect() as conn:
        traces = conn.execute(
            "SELECT trace_detail FROM study_event WHERE run_id=%s AND event_type='model_failed'",
            (run["run_id"],),
        ).fetchall()
    assert len(traces) == 2
    for event in traces:
        detail = event["trace_detail"]["protocol"]["review_contract"]
        assert detail["calls"][0]["arguments"]["explanation_checks"][0]["evidence_ids"] == ["e999"]
        assert (
            "Answer claims require their own observed citations" in detail["validator_errors"][0]["message"]
        )
