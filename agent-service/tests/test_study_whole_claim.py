import hashlib
import json

import httpx
import pytest
from test_study import read, setup  # noqa: F401

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.goals import explanation_claims, goal_constraints
from lecturelens_agent.study.provider import ChatProvider
from lecturelens_agent.study.quality import review_messages as current_review_messages
from lecturelens_agent.study.review_diagnostics import semantic_review_detail


@pytest.fixture(autouse=True)
def legacy_answer_review(monkeypatch):
    monkeypatch.setattr("lecturelens_agent.study.runtime.review_messages", review_messages)


def review_messages(*args, **kwargs):
    """Historical v1 contract/replay regression; atomic default is tested separately."""
    return current_review_messages(*args, **kwargs, answer_review_mode="answer_support_v1")


_HTTP_CLIENT = httpx.Client
# These are independently labelled support judgments supplied by the model
# fixture. Mechanics tests do not establish a real model's entailment accuracy.
CASES = [
    (
        "conjunction",
        "The gate is open and a warning bell rings.",
        "The gate is open.",
        "The gate is open.",
        "The gate is open; no source supports the warning bell.",
        False,
    ),
    (
        "temporal",
        "The gate is open until the timer expires.",
        "The gate is open.",
        "The gate is open.",
        "The gate is open; no source supports 'until the timer expires'.",
        False,
    ),
    (
        "causal",
        "The gate is open because the sensor detected a vehicle.",
        "The gate is open.",
        "The gate is open.",
        "The gate is open; no source supports the sensor cause.",
        False,
    ),
    (
        "consequence",
        "The gate is open, therefore every vehicle can leave.",
        "The gate is open.",
        "The gate is open.",
        "The gate is open; no source supports the universal exit consequence.",
        False,
    ),
    (
        "fully_supported",
        "The gate is open and a warning bell rings.",
        "The gate is open. A warning bell rings at the same time.",
        "The gate is open and a warning bell rings.",
        "The source states both the open gate and the ringing warning bell.",
        True,
    ),
    (
        "object_state",
        "s 已改绑到新对象，旧 hello 对象仍在内存中（直到被垃圾回收）且不再由 s 指向，新旧对象不同。",
        "s binds to a new object. The old hello object is still in memory somewhere; the objects are different.",
        "s 已改绑到新对象，旧 hello 对象仍在内存中且不再由 s 指向，新旧对象不同。",
        "课程支持当时的对象关系；括号内的生命周期时间条件没有课程依据。",
        False,
    ),
]


def fixture_verdict(body, supported, observation):
    return {
        "goal_checks": [
            {
                "id": clause["id"],
                "matches": True,
                "observation": "The answer describes the state.",
                "answer_quotes": [body["candidate"]["explanation"]],
            }
            for clause in goal_constraints(body["goal"])
        ],
        "explanation_checks": [
            {"id": claim["id"], "supported": supported, "course_fact": observation, "evidence_ids": ["e1"]}
            for claim in explanation_claims(body["candidate"]["explanation"])
        ],
    }


def model_response(verdict):
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


@pytest.mark.parametrize(
    "name,answer,source,narrowed,observation,supported", CASES, ids=[c[0] for c in CASES]
)
def test_complete_claim_and_universal_support_rule_reach_reviewer(
    monkeypatch,
    name,
    answer,
    source,
    narrowed,
    observation,
    supported,
):
    requests = []

    def handle(request):
        wire = json.loads(request.content)
        body = json.loads(wire["messages"][-1]["content"])
        requests.append(wire)
        assert body["candidate"]["explanation"] == answer
        assert body["explanation_claims"] == [{"id": "x1", "text": answer}]
        assert body["evidence"][0]["text"] == source
        return model_response(fixture_verdict(body, supported, observation))

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: _HTTP_CLIENT(transport=httpx.MockTransport(handle), **kw)
    )
    candidate = {
        "kind": "explanation",
        "title": "State",
        "explanation": answer,
        "evidence_ids": ["canonical"],
    }
    messages = review_messages(
        "Explain the observed state.", candidate, [{"evidence_id": "canonical", "text": source}]
    )
    result = ChatProvider("https://fixture.invalid/v1", "qwen3-max", "fixture-key").review(messages, 10)
    assert result["review"]["issues"] == ([] if supported else ["unsupported_explanation"])
    assert result["review"]["explanation_assessments"][0]["supported"] is supported
    system = requests[0]["messages"][0]["content"]
    assert "PARTIAL SUPPORT = UNSUPPORTED" in system
    assert "time/duration conditions" in system and "causal reasons" in system
    assert "Parenthetical facts receive the same check" in system
    assert "garbage collection" not in system and "垃圾回收" not in system


@pytest.mark.parametrize(
    "name,answer,source,narrowed,observation,supported", CASES, ids=[c[0] for c in CASES]
)
def test_runtime_minimally_narrows_partial_support_without_new_retrieval(
    setup,  # noqa: F811
    monkeypatch,
    name,
    answer,
    source,
    narrowed,
    observation,
    supported,  # noqa: F811
):
    store, authority, runtime, scope = setup
    original_read, original_decide = authority.read, runtime.provider.decide
    decisions, reviews = [], []

    def course_read(current_scope, action="CHECK", **arguments):
        result = original_read(current_scope, action, **arguments)
        for item in result["evidence"]:
            item["text"] = source
        return result

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return original_decide(messages, timeout)
        decisions.append(body)
        if len(decisions) == 2:
            assert body["quality"]["issues"] == ["unsupported_explanation"]
            assert "preserve its cited supported facts" in body["quality"]["feedback"]
            assert observation in body["quality"]["feedback"]
        return {
            "name": "create_explanation",
            "arguments": {
                "title": "State",
                "explanation": answer if len(decisions) == 1 else narrowed,
                "evidence_ids": ["e1"],
            },
        }

    def handle(request):
        body = json.loads(json.loads(request.content)["messages"][-1]["content"])
        reviews.append(body)
        verdict = fixture_verdict(
            body,
            supported if len(reviews) == 1 else True,
            observation if len(reviews) == 1 else "The cited course supports the narrowed state.",
        )
        return model_response(verdict)

    authority.read = course_read
    runtime.provider.decide = decide
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: _HTTP_CLIENT(transport=httpx.MockTransport(handle), **kw)
    )
    runtime.provider.review = ChatProvider("https://fixture.invalid/v1", "qwen3-max", "fixture-key").review
    monkeypatch.setenv("AGENT_PRIVATE_REVIEW_TELEMETRY_SESSION", scope["session_id"])
    started = store.command(
        StudyCommand(
            **scope, operation="START", request_key="whole-claim", goal="Explain the observed state."
        ),
        "mock",
    )
    run = next(r for r in store.candidates() if r["run_id"] == started["run"]["run_id"])
    runtime.execute(run)
    final = read(setup)
    assert final["run"]["status"] == "succeeded"
    assert final["artifact"]["explanation"] == narrowed
    assert len(reviews) == len(decisions) == (1 if supported else 2)
    assert reviews[0]["candidate"]["explanation"] == answer
    if not supported:
        assert reviews[1]["candidate"]["explanation"] == narrowed
        assert reviews[1]["candidate"]["evidence_ids"] == reviews[0]["candidate"]["evidence_ids"]
    assert authority.reads.count("SEARCH") == 1
    public = json.dumps(read(setup, "EVENTS"))
    assert "semantic_review" not in public and "whole_claim_observation" not in public
    with store.connect() as conn:
        events = conn.execute(
            "SELECT event_type,trace_detail FROM study_event WHERE run_id=%s ORDER BY sequence",
            (run["run_id"],),
        ).fetchall()
    revisions = [
        e["trace_detail"]["semantic_review"]
        for e in events
        if e["event_type"] == "node_started" and "semantic_review" in (e["trace_detail"] or {})
    ]
    assert len(revisions) == (0 if supported else 1)
    response_details = [
        e["trace_detail"]["response"]["private_review_contract"]["semantic_review"]
        for e in events
        if e["event_type"] == "model_finished" and "private_review_contract" in e["trace_detail"]["response"]
    ]
    first_claim = response_details[0]["claims"][0]
    assert first_claim["supported"] is supported
    assert first_claim["claim_sha256"] == hashlib.sha256(answer.encode()).hexdigest()
    assert response_details[0]["revision_triggered"] is False
    if not supported:
        assert revisions[0]["revision_triggered"] is True
        assert revisions[0]["claims"][0]["claim_sha256"] == first_claim["claim_sha256"]
        assert revisions[0]["claims"][0]["supported"] is False
        assert response_details[-1]["claims"][0]["supported"] is True


def test_semantic_observations_are_bounded_redacted_and_handle_malformed_values(monkeypatch):
    key = "private-semantic-key-sentinel"
    monkeypatch.setenv("QA_API_KEY", key)
    checks = [
        {
            "id": "x1",
            "supported": False,
            "evidence_ids": [key] * 200,
            "course_fact": (key + " Bearer hidden-token " + "z" * 2000) * 100,
        }
    ] * 100
    detail = semantic_review_detail("A and B.", checks, revision_triggered=True)
    serialized = json.dumps(detail)
    assert key not in serialized and "hidden-token" not in serialized
    assert len(detail["claims"]) == 6 and len(detail["claims"][0]["evidence_ids"]) == 8
    assert len(serialized.encode()) < 10 * 1024
    malformed = semantic_review_detail(
        "A.", [{"id": ["x1"]}, {"id": "x1", "evidence_ids": None, "supported": "true", "course_fact": None}]
    )
    assert len(malformed["claims"]) == 1
    assert malformed["claims"][0]["supported"] is None
