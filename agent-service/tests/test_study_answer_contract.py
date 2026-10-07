import copy
import json

import httpx
import pytest
from pydantic import ValidationError
from test_study import read, setup  # noqa: F401

from lecturelens_agent.study.answer_review import ExplanationVerdict, correction_feedback
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.goals import explanation_claims, goal_constraints
from lecturelens_agent.study.provider import ChatProvider, ModelResponseError
from lecturelens_agent.study.quality import review_messages as current_review_messages
from lecturelens_agent.study.quality import review_schema


@pytest.fixture(autouse=True)
def legacy_answer_review(monkeypatch):
    monkeypatch.setattr("lecturelens_agent.study.runtime.review_messages", review_messages)


def review_messages(*args, **kwargs):
    """Historical v1 contract/replay regression; atomic default is tested separately."""
    return current_review_messages(*args, **kwargs, answer_review_mode="answer_support_v1")


SOURCE = "The old hello object still is in memory somewhere; s no longer refers to it."
SUPPORTED = "旧 hello 对象仍在内存中，s 不再指向它。"
EXTRA = "它一直存在直到被垃圾回收。"
GOAL = "Explain the old hello object's state."
_HTTP_CLIENT = httpx.Client


def input_body(answer=SUPPORTED, goal=GOAL):
    return {
        "review_mode": "answer_support_v1",
        "goal": goal,
        "candidate": {
            "kind": "explanation",
            "title": "Object state",
            "explanation": answer,
            "evidence_ids": ["e1", "e2"],
        },
        "evidence": [{"evidence_id": ref, "text": SOURCE} for ref in ["e1", "e2", "e7"]],
        "observed_evidence_ids": ["e1", "e2", "e7"],
        "allowed_evidence_ids_for_answer_support": ["e1", "e2"],
        "goal_constraints": goal_constraints(goal),
        "explanation_claims": explanation_claims(answer),
    }


def judgment(body, reject_extra=False):
    return {
        "goal_checks": [
            {
                "id": item["id"],
                "matches": True,
                "observation": "The answer describes the object's state.",
                "answer_quotes": [body["candidate"]["explanation"]],
            }
            for item in goal_constraints(body["goal"])
        ],
        "explanation_checks": [
            {
                "id": item["id"],
                "supported": not (reject_extra and "垃圾回收" in item["text"]),
                "course_fact": "旧对象仍在内存，不再由 s 指向；课程未说明垃圾回收。"
                if reject_extra and "垃圾回收" in item["text"]
                else "旧对象仍在内存，不再由 s 指向。",
                "evidence_ids": ["e1"],
            }
            for item in explanation_claims(body["candidate"]["explanation"])
        ],
    }


def test_initial_context_explicitly_separates_observed_from_allowed_sources():
    evidence = [
        {"evidence_id": f"canonical{i}", "text": SOURCE, "start_ms": i, "end_ms": i + 1} for i in range(1, 10)
    ]
    candidate = {**input_body()["candidate"], "evidence_ids": ["canonical1", "canonical2"]}
    messages = review_messages(GOAL, candidate, evidence)
    body = json.loads(messages[-1]["content"])
    assert body["observed_evidence_ids"] == [f"e{i}" for i in range(1, 9)]
    assert body["allowed_evidence_ids_for_answer_support"] == ["e1", "e2"]
    assert "including when supported=false" in messages[0]["content"]
    tool = review_schema("explanation", review_mode="answer_support_v1")
    assert tool["function"]["parameters"] == ExplanationVerdict.model_json_schema()
    assert "allowed_evidence_ids_for_answer_support" in tool["function"]["description"]


@pytest.mark.parametrize("supported", [True, False])
def test_observed_but_uncited_source_is_rejected_even_when_supported_false(supported):
    body = input_body()
    verdict = judgment(body)
    verdict["explanation_checks"][0].update(evidence_ids=["e1", "e7"], supported=supported)
    original = copy.deepcopy(verdict)
    with pytest.raises(ValidationError, match="own observed citations"):
        ExplanationVerdict.model_validate(verdict, context=body)
    assert verdict == original
    # Context is explanatory metadata, not a replacement for the authority rule.
    body["allowed_evidence_ids_for_answer_support"].append("e7")
    with pytest.raises(ValidationError, match="own observed citations"):
        ExplanationVerdict.model_validate(verdict, context=body)


def test_valid_candidate_citations_pass_and_duplicates_still_fail():
    body = input_body()
    verdict = judgment(body)
    verdict["explanation_checks"][0]["evidence_ids"] = ["e1", "e2"]
    assert ExplanationVerdict.model_validate(verdict, context=body).review().issues == []
    verdict["explanation_checks"][0]["evidence_ids"] = ["e1", "e1"]
    with pytest.raises(ValidationError, match="own observed citations"):
        ExplanationVerdict.model_validate(verdict, context=body)


@pytest.mark.parametrize("fault", ["duplicate", "missing", "wrong"])
def test_goal_ids_remain_exactly_bound(fault):
    body = input_body(goal="Explain the old object; distinguish the new object.")
    verdict = judgment(body)
    if fault == "duplicate":
        verdict["goal_checks"][1]["id"] = "g1"
    elif fault == "missing":
        verdict["goal_checks"].pop()
    else:
        verdict["goal_checks"][1]["id"] = "g3"
    with pytest.raises(ValidationError, match="every goal clause exactly once"):
        ExplanationVerdict.model_validate(verdict, context=body)


@pytest.mark.parametrize("answer", [SUPPORTED + EXTRA, "旧 hello 对象仍在内存中，直到被垃圾回收。"])
def test_unsupported_extra_clause_is_a_semantic_rejection_not_a_contract_error(answer):
    body = input_body(answer)
    result = ExplanationVerdict.model_validate(judgment(body, reject_extra=True), context=body).review()
    assert result.issues == ["unsupported_explanation"]
    assert "垃圾回收" in result.feedback
    assert result.explanation_assessments[-1].supported is False
    if answer == SUPPORTED + EXTRA:
        assert result.explanation_assessments[0].supported is True


def test_binding_correction_is_precise_private_and_does_not_normalize(monkeypatch):
    from lecturelens_agent.study.answer_review import ANSWER_SYSTEM

    body = input_body()
    bad = judgment(body)
    bad["explanation_checks"][0]["evidence_ids"] = ["e1", "e7"]
    original = copy.deepcopy(bad)
    responses = [bad, judgment(body)]
    responses[1]["explanation_checks"][0]["supported"] = False
    recorded = []

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
                                        "arguments": json.dumps(responses[len(recorded) - 1]),
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: _HTTP_CLIENT(transport=httpx.MockTransport(handle), **kw)
    )
    monkeypatch.delenv("AGENT_PRIVATE_REVIEW_TELEMETRY_SESSION", raising=False)
    provider = ChatProvider("https://provider.invalid/v1", "qwen3-max", "fixture-key")
    messages = [{"role": "system", "content": ANSWER_SYSTEM}, {"role": "user", "content": json.dumps(body)}]
    with pytest.raises(ModelResponseError) as failure:
        provider.review(messages, 10)
    feedback = correction_feedback(failure.value)
    assert feedback["contract_errors"] == [
        {
            "path": "explanation_checks[0].evidence_ids[1]",
            "claim_id": "x1",
            "invalid_value": "e7",
            "allowed_values": ["e1", "e2"],
            "rule": "evidence_ids must belong to the candidate answer's own observed citations",
        }
    ]
    assert "e7" not in json.dumps(failure.value.diagnostics)
    body["protocol_feedback"] = feedback
    messages[-1]["content"] = json.dumps(body)
    result = provider.review(messages, 10)
    assert result["review"]["issues"] == ["unsupported_explanation"]
    assert result["review"]["explanation_assessments"][0]["evidence_ids"] == ["e1"]
    assert bad == original
    assert len(recorded) == 2


def test_runtime_correction_then_semantic_revision_preserves_private_evidence(setup, monkeypatch):  # noqa: F811
    store, authority, runtime, scope = setup
    original_read, original_decide = authority.read, runtime.provider.decide
    decisions, requests, returned = [], [], []

    def course_read(current_scope, action="CHECK", **arguments):
        result = original_read(current_scope, action, **arguments)
        if action != "CHECK":
            for item in result["evidence"]:
                item["text"] = SOURCE
            if action == "SEARCH":
                result["evidence"] += [
                    {
                        "evidence_id": f"e{i}",
                        "text": SOURCE,
                        "start_ms": i * 1000,
                        "end_ms": (i + 1) * 1000,
                        "source_type": "SUBTITLE",
                    }
                    for i in range(3, 8)
                ]
        return result

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return original_decide(messages, timeout)
        decisions.append(body)
        if len(decisions) == 2:
            assert "unsupported_explanation" in body["quality"]["issues"]
            assert "垃圾回收" in json.dumps(body["quality"], ensure_ascii=False)
        return {
            "name": "create_explanation",
            "arguments": {
                "title": "Object state",
                "explanation": SUPPORTED + EXTRA if len(decisions) == 1 else SUPPORTED,
                "evidence_ids": ["e1", "e2"],
            },
        }

    def handle(request):
        body = json.loads(json.loads(request.content)["messages"][-1]["content"])
        requests.append(body)
        verdict = judgment(body, reject_extra=len(requests) == 2)
        if len(requests) == 1:
            verdict["explanation_checks"][1]["evidence_ids"] = ["e1", "e7"]
        returned.append(copy.deepcopy(verdict))
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

    authority.read = course_read
    runtime.provider.decide = decide
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: _HTTP_CLIENT(transport=httpx.MockTransport(handle), **kw)
    )
    runtime.provider.review = ChatProvider("https://provider.invalid/v1", "qwen3-max", "fixture-key").review
    monkeypatch.setenv("AGENT_PRIVATE_REVIEW_TELEMETRY_SESSION", scope["session_id"])
    started = store.command(
        StudyCommand(**scope, operation="START", request_key="answer-contract", goal=GOAL), "mock"
    )
    run = next(r for r in store.candidates() if r["run_id"] == started["run"]["run_id"])
    runtime.execute(run)
    result = read(setup)
    assert result["run"]["status"] == "succeeded"
    assert result["artifact"]["explanation"] == SUPPORTED
    assert len(requests) == 3 and len(decisions) == 2
    assert returned[0]["explanation_checks"][1]["evidence_ids"] == ["e1", "e7"]
    assert returned[1]["explanation_checks"][1]["supported"] is False
    assert returned[1]["explanation_checks"][1]["evidence_ids"] == ["e1"]
    assert requests[0]["candidate"] == requests[1]["candidate"]
    feedback = requests[1]["protocol_feedback"]
    assert feedback["contract_errors"][0]["path"] == "explanation_checks[1].evidence_ids[1]"
    assert feedback["contract_errors"][0]["allowed_values"] == ["e1", "e2"]
    assert "explanation:N" not in feedback["instruction"]
    public = json.dumps(read(setup, "EVENTS"), ensure_ascii=False)
    assert "contract_errors" not in public and "垃圾回收" not in public and "arguments" not in public
    with store.connect() as conn:
        failed = conn.execute(
            "SELECT trace_detail FROM study_event WHERE run_id=%s AND event_type='model_failed'",
            (run["run_id"],),
        ).fetchall()
        retries = conn.execute(
            "SELECT count(*) FROM study_event WHERE run_id=%s AND event_type='protocol_retry_scheduled'",
            (run["run_id"],),
        ).fetchone()["count"]
    assert len(failed) == 1 and retries == 1
    detail = failed[0]["trace_detail"]["protocol"]["review_contract"]
    assert detail["calls"][0]["arguments"]["explanation_checks"][1]["evidence_ids"] == ["e1", "e7"]
    assert detail["binding_observations"][0]["path"] == ["explanation_checks", 1, "evidence_ids", 1]
