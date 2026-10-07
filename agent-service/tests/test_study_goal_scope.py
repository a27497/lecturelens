import copy
import json

import httpx
import pytest
from pydantic import ValidationError
from test_study import read, setup  # noqa: F401
from test_study_atomic import judgment, response
from test_study_revision import procedure_transaction

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.goal_scope import ScopedGoalVerdict, bind_scope
from lecturelens_agent.study.provider import ChatProvider
from lecturelens_agent.study.quality import review_messages, review_schema, review_wire_messages
from lecturelens_agent.study.revision import assemble_revision, freeze_revision


def scoped_input(remove_input=False):
    history, semantic, evidence = procedure_transaction()
    frozen = freeze_revision(history, semantic, evidence)
    candidate = assemble_revision(
        frozen, [{"id": c["id"], "replacement": ""} for c in frozen["rejected"]], evidence=evidence
    )
    if remove_input:
        candidate["explanation"] = "方法将某个元素与左右邻居比较。直到单元素基础情况，返回该元素。"
    messages = review_messages(semantic["resolved_goal"], dict(kind="explanation", **candidate), evidence)
    bind_scope(messages, frozen)
    return messages, json.loads(messages[-1]["content"]), frozen


def test_schema_and_verdict_bind_all_exact_obligations_and_current_answer():
    messages, body, frozen = scoped_input()
    schema = review_schema("explanation", review_mode=body["review_mode"], context=body)["function"][
        "parameters"
    ]
    ids = [o["id"] for o in frozen["goal_obligations"]["obligations"]]
    assert schema["$defs"]["ScopedGoalCheck"]["properties"]["id"]["enum"] == ids
    assert set(schema["$defs"]["ScopedGoalCheck"]["properties"]) == {"id", "status", "answer_quote"}
    assert (
        schema["properties"]["goal_checks"]["minItems"]
        == schema["properties"]["goal_checks"]["maxItems"]
        == len(ids)
    )
    assert [o["text"] for o in body["goal_scope_binding"]["obligations"]] == [
        o["requirement"] for o in frozen["goal_obligations"]["obligations"]
    ]
    review = ScopedGoalVerdict.model_validate(judgment(body), context=body).review()
    assert review.issues == [] and len(review.goal_scope_assessments) == len(ids)
    assert all(c["answer_quote"] in body["candidate"]["explanation"] for c in review.goal_scope_assessments)
    wire = json.loads(review_wire_messages(messages)[-1]["content"])
    assert wire["goal_scope_binding"]["obligations"] == body["goal_scope_binding"]["obligations"]


@pytest.mark.parametrize(
    "violation", ["new_id", "duplicate", "missing", "observation", "foreign_quote", "scope_mutation"]
)
def test_out_of_scope_requirements_cannot_produce_goal_mismatch(violation):
    _, body, _ = scoped_input()
    verdict = judgment(body)
    if violation == "new_id":
        verdict["goal_checks"][0]["id"] = "invented_position"
    elif violation == "duplicate":
        verdict["goal_checks"][-1] = copy.deepcopy(verdict["goal_checks"][0])
    elif violation == "missing":
        verdict["goal_checks"].pop()
    elif violation == "observation":
        verdict["goal_checks"][0]["observation"] = "Also specify the midpoint and a fixed branch."
    elif violation == "foreign_quote":
        verdict["goal_checks"][0]["answer_quote"] = "Choose the midpoint."
    else:
        body["goal_scope_binding"]["obligations"][0]["text"] += " Add a new rule."
    with pytest.raises(ValidationError):
        ScopedGoalVerdict.model_validate(verdict, context=body)


def test_keyword_hit_does_not_override_semantic_rejection_or_require_a_full_quote():
    _, body, _ = scoped_input()
    verdict = judgment(body)
    check = next(c for c in verdict["goal_checks"] if c["id"] == "procedure_input_change")
    check.update(status="unsatisfied", answer_quote="")
    review = ScopedGoalVerdict.model_validate(verdict, context=body).review()
    assert review.issues == ["goal_mismatch"]  # Semantic rejection, not a retry.
    check.update(status="satisfied", answer_quote=body["candidate"]["explanation"][:10])
    assert ScopedGoalVerdict.model_validate(verdict, context=body).review().issues == []


@pytest.mark.parametrize("kind", ["comparison_operands", "input_change", "stopping_case"])
def test_present_keywords_can_describe_the_wrong_or_incomplete_outcome(kind):
    from lecturelens_agent.study.goal_obligations import carries_obligation

    _, body, _ = scoped_input()
    verdict = judgment(body)
    obligation = next(o for o in body["goal_scope_binding"]["obligations"] if o["kind"] == kind)
    assert carries_obligation(obligation, body["candidate"]["explanation"])
    next(c for c in verdict["goal_checks"] if c["id"] == obligation["id"]).update(
        status="unsatisfied", answer_quote=""
    )
    assert "goal_mismatch" in ScopedGoalVerdict.model_validate(verdict, context=body).review().issues


def test_safe_diagnostics_bind_the_obligation_status_and_validator_condition(monkeypatch):
    from lecturelens_agent.study.provider import ModelResponseError

    messages, body, _ = scoped_input()
    verdict = judgment(body)
    check = next(c for c in verdict["goal_checks"] if c["id"] == "procedure_input_change")
    check["answer_quote"] = "sk-private-secret-sentinel"
    provider = ChatProvider("https://fixture.invalid/v1", "qwen3-max", "private-key-sentinel")
    monkeypatch.setattr(
        provider,
        "_request",
        lambda *a: {
            "calls": [
                {
                    "name": "assess_study_candidate",
                    "arguments": {**verdict, "secret": "Bearer sensitive-sentinel"},
                }
            ],
            "usage": {},
        },
    )
    # Undeclared fields are diagnosed separately and never copied.
    with pytest.raises(ModelResponseError) as raised:
        provider.review(messages, 1)
    detail = raised.value.private_diagnostics["goal_scope"]
    assert "private" not in json.dumps(detail) and "sensitive" not in json.dumps(detail)
    monkeypatch.setattr(
        provider,
        "_request",
        lambda *a: {"calls": [{"name": "assess_study_candidate", "arguments": verdict}], "usage": {}},
    )
    with pytest.raises(ModelResponseError) as raised:
        provider.review(messages, 1)
    detail = raised.value.private_diagnostics["goal_scope"]
    assert detail["validator_conditions"] == [{"rule": "current_answer_quote", "obligation_id": check["id"]}]
    item = next(c for c in detail["assessments"] if c["obligation_id"] == check["id"])
    assert item["model_status"] == "satisfied" and item["quote_in_answer"] is False
    assert item["requirement_sha256"] and item["quote_sha256"]
    assert "private" not in json.dumps(detail)


def test_scoped_wire_is_lossless_without_repeated_goal_or_claim_prose():
    messages, body, _ = scoped_input()
    body["revision_goal_obligations"] = {"duplicate": True}
    messages[-1]["content"] = json.dumps(body, ensure_ascii=False)
    wire = review_wire_messages(messages)
    visible = json.loads(wire[-1]["content"])
    assert not {"revision_goal_obligations", "goal_constraints", "goal_answer_claims"} & visible.keys()
    for claim in visible["atomic_claims"]:
        original = next(c for c in body["atomic_claims"] if c["id"] == claim["id"])
        assert visible["candidate"]["explanation"][claim["start"] : claim["end"]] == original["source_text"]
        assert "source_text" not in claim and "context_start" in claim and "context_end" in claim
    assert "Unicode offsets" in wire[0]["content"]
    assert json.loads(messages[-1]["content"]) == body


def test_genuinely_omitted_frozen_user_requirement_still_fails():
    _, body, _ = scoped_input(remove_input=True)
    verdict = judgment(body)
    for c in verdict["goal_checks"]:
        if c["id"] in {"g1", "procedure_input_change"}:
            c.update(status="unsatisfied", answer_quote="")
    review = ScopedGoalVerdict.model_validate(verdict, context=body).review()
    assert review.issues == ["goal_mismatch"]
    assert all(c.supported for c in review.atomic_assessments)
    assert "input/subproblem size" in review.feedback


def test_goal_coverage_never_overrides_atomic_rejection_or_source_scope():
    _, body, _ = scoped_input()
    verdict = judgment(body)
    verdict["claim_checks"][0].update(supported=False, evidence_ids=[])
    if verdict["claim_checks"][0].get("relation"):
        verdict["claim_checks"][0]["relation"]["grounds"] = []
    review = ScopedGoalVerdict.model_validate(verdict, context=body).review()
    assert review.issues == ["unsupported_explanation"]
    assert not review.atomic_assessments[0].supported
    assert all(c["status"] == "satisfied" for c in review.goal_scope_assessments)
    bad = copy.deepcopy(verdict)
    bad["claim_checks"][0].update(supported=True, evidence_ids=["foreign"])
    with pytest.raises(ValidationError):
        ScopedGoalVerdict.model_validate(bad, context=body)


@pytest.mark.parametrize("repeat_violation", [False, True])
def test_runtime_records_scope_violation_and_corrects_at_most_once(setup, monkeypatch, repeat_violation):  # noqa: F811
    store, authority, runtime, scope = setup
    history, _, evidence = procedure_transaction()
    initial = history[0]["arguments"]["explanation"]
    original_read = authority.read
    requests = []

    def course_read(scope, action="CHECK", **kw):
        result = original_read(scope, action, **kw)
        for e in result.get("evidence", []):
            e["text"] = evidence[0]["text"]
        return result

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["history"]:
            return dict(
                name="search_course_evidence", arguments=dict(query=body["goal"], output_kind="explanation")
            )
        if body.get("revision_transaction"):
            return dict(
                name="create_explanation",
                arguments=dict(
                    revision_edits=[
                        dict(id=c["id"], replacement="") for c in body["revision_transaction"]["rejected"]
                    ]
                ),
            )
        return dict(
            name="create_explanation",
            arguments=dict(title="Method", explanation=initial, evidence_ids=["e1"]),
        )

    def handle(request):
        body = json.loads(json.loads(request.content)["messages"][-1]["content"])
        requests.append(body)
        verdict = judgment(body)
        if body.get("goal_scope_binding"):
            if len(requests) == 2 or repeat_violation:
                verdict["goal_checks"][0]["id"] = "invented_position"
            if len(requests) == 3:
                assert body["goal_scope_binding"] == requests[1]["goal_scope_binding"]
                assert body["candidate"] == requests[1]["candidate"]
                assert body["evidence"] == requests[1]["evidence"]
                assert "Only fixed obligation IDs" in body["protocol_feedback"]["instruction"]
        return response(verdict)

    authority.read = course_read
    runtime.provider.decide = decide
    client_type = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: client_type(transport=httpx.MockTransport(handle), **kw)
    )
    runtime.provider.review = ChatProvider("https://fixture.invalid/v1", "qwen3-max", "fixture").review
    started = store.command(
        StudyCommand(
            **scope, operation="START", request_key="goal-scope", goal="Explain the method in concrete steps."
        ),
        "mock",
    )
    run = next(r for r in store.candidates() if r["run_id"] == started["run"]["run_id"])
    runtime.execute(run)
    result = read(setup)
    assert len(requests) == 3 and result["run"]["model_calls"] == 6
    assert authority.reads.count("SEARCH") == 1
    if repeat_violation:
        assert result["run"]["status"] == "failed" and result["artifact"] is None
        assert result["run"]["error_code"] == "MODEL_REVIEW_CONTRACT"
    else:
        assert result["run"]["status"] == "succeeded"
    with store.connect() as conn:
        events = conn.execute(
            "SELECT payload,trace_detail FROM study_event WHERE run_id=%s AND event_type='goal_scope_violation'",
            (run["run_id"],),
        ).fetchall()
    assert len(events) == 1 and events[0]["payload"]["status"] == "BOUNDED_CORRECTION_REQUIRED"
    assert events[0]["trace_detail"]["scope"]["obligations"]
