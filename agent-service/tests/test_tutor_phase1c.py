"""Immutable real failure analysis plus authored offline mechanisms, never new model quality."""

import copy
import hashlib
import json
import os
import zipfile
from functools import lru_cache
from pathlib import Path

import pytest
import test_tutor_v19 as prior

from lecturelens_agent.study.store import StudyError
from lecturelens_real_eval.tutor.contracts import Command
from lecturelens_real_eval.tutor.relevant_authority import RelevantSnapshotAuthority
from lecturelens_real_eval.tutor.selection_runtime import (
    IDENTITY,
    SPAN_LIMITS,
    SelectedTutorRuntime,
    span_ends,
    units,
)

offline, lab = prior.offline, prior.lab
ROOT = Path(__file__).resolve().parents[2]
FAILURE_SHA = "832e20a6e066603b57a858a50ddbd2eda355757ba821e4119c6056339299b30d"


@lru_cache
def failure():
    raw = (ROOT / ".data/phase1c/v19-failed-real-review.zip").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FAILURE_SHA
    with zipfile.ZipFile(ROOT / ".data/phase1c/v19-failed-real-review.zip") as archive:
        assets = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(assets["manifest.json"])
    assert manifest["generation"] == "REAL_OUTPUTS_PRESENT"
    for name, expected in manifest["files"].items():
        assert hashlib.sha256(assets[name]).hexdigest() == expected
    return assets


def asset(name):
    return json.loads(failure()[name])


def tasks():
    return asset("original-packet.json")["sessions"][0]["turns"]


def retain(name, value):
    path = Path(os.environ["PHASE1C_OUTPUT"]) / (name + ".json")
    with path.open("x") as target:
        json.dump(value, target, ensure_ascii=False, indent=2, default=str)


@pytest.fixture
def selected(lab):
    store, authority, _, scope = lab
    authority = RelevantSnapshotAuthority(authority.snapshot)
    authority.register(scope, "carpentries-python")
    runtime = SelectedTutorRuntime(store, authority)
    runtime.initialize()
    try:
        yield store, authority, runtime, scope
    finally:
        runtime.close()


def provider(finish, **kwargs):
    return prior.Provider(finish, **kwargs)


def run(selected, model, **kwargs):
    return prior.run(selected, model, **kwargs)


def test_original_three_turn_failure_remains_immutable_and_not_quality_pass():
    outcomes, summary = asset("execution/outcomes.json"), asset("execution/summary.json")
    assert summary["mode"] == "live" and summary["sent_requests"] == 9
    assert (summary["completed"], summary["failed"], summary["skipped"]) == (2, 1, 0)
    assert summary["ledger"]["nano_usd"] == 11272800 and not summary["ledger"]["pending"]
    assert "Ada" not in outcomes[0]["answer"] and "Grace" not in outcomes[0]["answer"]
    assert "length = 0" in outcomes[0]["answer"]
    assert "Which rule in the cited source applies" in outcomes[1]["answer"]
    assert "final print" not in outcomes[1]["answer"]
    assert outcomes[2]["error_code"] == "TUTOR_REPAIR_BUDGET_UNAVAILABLE"
    last = asset("execution/wire/009-response.body")["choices"][0]["message"]["tool_calls"][0]
    assert "Curie" in last["function"]["arguments"]
    request = asset("execution/wire/009-request.body")
    history = json.loads(request["messages"][-1]["content"])["history"]
    assert tasks()[0]["text"] == history[0]["learner_text"]
    assert "starting length at 2" in history[0]["learner_text"]
    retain("original-failure-facts", dict(summary=summary, historical_quality="UNRESOLVED_NOT_RELABELED"))


@pytest.mark.parametrize("limit", sorted(set(SPAN_LIMITS.values())))
def test_capacity_observations_are_exact_and_source_lossless(limit):
    text = ("条件😀\n" * 147) + "```python\nitems = ['one', 'two']\n```\n"
    parts = units(text)
    ends = span_ends(parts, limit)
    assert "".join(part for _, part in parts) == text
    for first, last in enumerate(ends):
        selected = "".join(part for _, part in parts[first:last])
        assert selected and len(selected) <= limit
        if last < len(parts):
            assert len(selected + parts[last][1]) > limit


def test_complete_authored_lesson_is_saved_without_truncation_and_recovers(selected):
    model = provider(prior.complete)
    result = run(selected, model, text=tasks()[0]["text"])
    assert result["status"] == "completed" and len(model.requests) == 2
    for block in prior.teaching.LONG_BLOCKS:
        assert block in result["answer"]
    assert "names[0]" in result["answer"] and "names[1]" in result["answer"]
    store, authority, runtime, scope = selected
    resumed = SelectedTutorRuntime(store, authority)
    try:
        assert resumed.command(Command(**scope, operation="GET"))["turns"][-1] == result
        replay = runtime.command(
            Command(**scope, operation="TURN", client_turn_id="t1", text=tasks()[0]["text"])
        )
        assert replay["replayed"] and replay["turns"][-1] == result and len(model.requests) == 2
    finally:
        resumed.close()
    retain(
        "authored-complete-teaching",
        dict(result=result, requests=model.requests, generation="AUTHORED_NOT_REAL"),
    )


@pytest.mark.parametrize("correct", [False, True])
def test_real_source_only_finish_cannot_be_published_as_teaching(selected, correct):
    original = [asset(f"execution/wire/{n:03d}-response.body") for n in (1, 2, 3)]
    requests = []

    class Replay:
        def decide(self, messages, schemas, timeout):
            requests.append(copy.deepcopy((messages, schemas)))
            index = len(requests)
            if index <= 3 or not correct:
                response = original[min(index, 3) - 1]
                tool = response["choices"][0]["message"]["tool_calls"][0]["function"]
                return dict(
                    name=tool["name"],
                    arguments=json.loads(tool["arguments"]),
                    usage={key: response["usage"][key] for key in ("prompt_tokens", "completion_tokens")},
                )
            return dict(
                name="finish_tutor_turn",
                arguments=prior.complete(json.loads(messages[-1]["content"])),
                usage=dict(prompt_tokens=100, completion_tokens=60),
            )

    result = run(selected, Replay(), text=tasks()[0]["text"])
    assert len(requests) == 4
    assert [s["function"]["name"] for s in requests[-1][1]] == ["finish_tutor_turn"]
    body = json.loads(requests[-1][0][-1]["content"])
    assert any("TEACHING_CONTENT_REQUIRED" in o.get("message", "") for o in body["observations"])
    assert body["rejected_blocks"]["retained_in_checkpoint"] is True
    if correct:
        assert result["status"] == "completed"
        assert all(text in result["answer"] for text in prior.teaching.LONG_BLOCKS)
    else:
        assert result["status"] == "failed" and result["answer"] is None
        assert result["error_code"] == "TUTOR_SHARED_FINISH_CORRECTION_INVALID"
    retain(
        "source-only-replay-" + str(correct),
        dict(
            result=result,
            requests=requests,
            fourth="AUTHORED_CORRECTION" if correct else "UNCHANGED_FAILED_REAL_PROPOSAL",
            real_requests=0,
        ),
    )


def targeted(body):
    return dict(
        outcome="socratic_prompt",
        hint=dict(intent="locate_body", focus="final print", span=prior.span(body, "length = length + 1")),
    )


def feedback(body):
    value = prior.complete(body)
    value["evaluation_blocks"] = [
        dict(
            span=prior.span(body, "length = length + 1"),
            learner_quote="changes only once",
            text="Under your earlier changed example there are two visits, Ada and Grace. Starting at 2, one increment per visit gives 3 then 4. The final unindented print is outside the body and runs once. This corrects both claims without claiming code execution or a grade.",
        )
    ]
    return value


def test_targeted_hint_and_followup_preserve_learner_premises_and_complete_explanation(selected):
    first = run(selected, provider(prior.complete), text=tasks()[0]["text"])
    hint_model = provider(targeted)
    second = run(selected, hint_model, key="t2", text=tasks()[1]["text"], socratic=True)
    assert second["status"] == "completed"
    text = second["answer"]
    for citation in second["citations"]:
        text = text.replace("[" + citation["evidence_id"] + "]", "")
    assert "final print" in text and "indented loop body" in text
    assert all(term not in text for term in ("Ada", "Grace", "length =", "3", "4"))
    model = provider(feedback)
    third = run(selected, model, key="t3", text=tasks()[2]["text"])
    assert third["status"] == "completed" and "two visits" in third["evaluation"]
    body = json.loads(model.requests[-1][0][-1]["content"])
    assert body["history"][0]["learner_text"] == tasks()[0]["text"]
    assert body["history"][1]["learner_text"] == tasks()[1]["text"]
    for block in prior.teaching.LONG_BLOCKS:
        assert block in body["history"][0]["answer"]
    assert body["history"][1]["answer"] == second["answer"]
    assert all(
        len(row["answer"]) <= 4096 and len(row["evaluation"] or "") <= 1024 for row in (first, second, third)
    )
    retain(
        "authored-three-turn-dialogue",
        dict(
            turns=[first, second, third],
            requests=model.requests,
            real_requests=0,
            quality="REAL_MODEL_QUALITY_NOT_RUN",
        ),
    )


@pytest.mark.parametrize("focus", ["the solution is 4", "final\nprint", "   "])
def test_invented_or_unsafe_hint_focus_cannot_publish(selected, focus):
    def finish(body):
        return targeted(body) | dict(hint=targeted(body)["hint"] | dict(focus=focus))

    model = provider(finish)
    result = run(selected, model, text=tasks()[1]["text"], socratic=True)
    assert result["status"] == "failed" and result["answer"] is None
    assert len(model.requests) == 3


def test_old_generic_hint_without_current_focus_requires_one_correction(selected):
    def finish(body):
        value = targeted(body)
        if "rejected_blocks" not in body:
            del value["hint"]["focus"]
            value["hint"]["intent"] = "locate_rule"
        return value

    model = provider(finish)
    result = run(selected, model, text=tasks()[1]["text"], socratic=True)
    assert result["status"] == "completed" and len(model.requests) == 3
    assert "final print" in result["answer"] and "indented loop body" in result["answer"]


@pytest.mark.parametrize("fault", ["foreign_id", "source_change", "no_capacity", "late_cancel"])
def test_authority_cancellation_and_budget_fences_remain(selected, fault):
    store, authority, runtime, scope = selected

    def finish(body):
        value = prior.complete(body)
        if fault == "foreign_id":
            value["blocks"][0]["span"]["evidence_id"] = "f" * 64
        elif fault == "source_change":
            original = authority.read

            def changed(scope, action="CHECK", **kwargs):
                result = copy.deepcopy(original(scope, action, **kwargs))
                if action == "READ" and result["evidence"]:
                    result["evidence"][0]["text"] += "changed after observation"
                return result

            authority.read = changed
        elif fault == "no_capacity":
            with store.connect() as conn:
                conn.execute(
                    "UPDATE tutor_session SET max_tokens=reserved_tokens WHERE session_id=%s",
                    (scope["session_id"],),
                )
            value["blocks"][0]["span"]["last_unit"] = 7999
        else:
            runtime.command(Command(**scope, operation="CANCEL", client_turn_id="t1"))
        return value

    model = provider(finish)
    result = run(selected, model)
    assert result["status"] == ("cancelled" if fault == "late_cancel" else "failed")
    assert result["answer"] is None and len(model.requests) == 2
    if fault == "no_capacity":
        assert result["error_code"] == "TUTOR_REPAIR_BUDGET_UNAVAILABLE"
    with pytest.raises(StudyError):
        runtime.command(Command(**(scope | dict(owner_id=scope["owner_id"] + 1)), operation="GET"))


@pytest.mark.parametrize("changed", [False, True])
def test_prepaid_correction_survives_restart_without_extra_reservation(selected, changed):
    store, authority, runtime, scope = selected

    def finish(body):
        value = prior.complete(body)
        if "rejected_blocks" not in body:
            value["blocks"][0]["span"]["last_unit"] = 7999
        return value

    model = provider(finish, second_search=True)
    runtime.provider = model
    runtime.command(Command(**scope, operation="TURN", client_turn_id="t1", text=tasks()[0]["text"]))
    candidate = store.candidates()[0]
    repair = runtime.repair

    class Paused(Exception):
        pass

    def pause(*args, **kwargs):
        repair(*args, **kwargs)
        raise Paused()

    runtime.repair = pause
    with pytest.raises(Paused):
        runtime.loop(candidate["turn_id"])
    with store.connect() as conn:
        before = conn.execute(
            "SELECT model_calls,reserved_tokens,checkpoint FROM tutor_turn WHERE turn_id=%s",
            (candidate["turn_id"],),
        ).fetchone()
    assert before["model_calls"] == 4 and len(model.requests) == 3
    assert before["checkpoint"]["repair_request"]
    assert before["checkpoint"]["structured_proposal"]["blocks"][0]["span"]["last_unit"] == 7999
    if changed:
        original = authority.read

        def read(scope, action="CHECK", **kwargs):
            value = copy.deepcopy(original(scope, action, **kwargs))
            if action == "READ" and value["evidence"]:
                value["evidence"][0]["text"] += "changed after prepaid reservation"
            return value

        authority.read = read
    resumed = SelectedTutorRuntime(store, authority, model)
    try:
        resumed.execute(candidate)
        row = resumed.command(Command(**scope, operation="GET"))["turns"][-1]
    finally:
        resumed.close()
    with store.connect() as conn:
        after = conn.execute(
            "SELECT model_calls,reserved_tokens FROM tutor_turn WHERE turn_id=%s", (candidate["turn_id"],)
        ).fetchone()
    assert (after["model_calls"], after["reserved_tokens"]) == (
        before["model_calls"],
        before["reserved_tokens"],
    )
    assert row["status"] == ("failed" if changed else "completed")
    assert len(model.requests) == (3 if changed else 4)
    retain("prepaid-restart-" + str(changed), dict(before=before, after=after, result=row))


def test_same_semantic_risk_is_not_disguised_as_independent_validation(selected):
    model = provider(
        lambda body: dict(
            outcome="answered", blocks=[prior.explanation(body, "All loops prove that a medicine is safe.")]
        )
    )
    row = run(selected, model)
    assert row["status"] == "completed"  # Binding still cannot establish entailment.
    retain(
        "a03-residual-semantic-risk",
        dict(result=row, semantic_status="AUTHORED_KNOWN_FALSE_NEGATIVE_NOT_QUALITY_PASS"),
    )


def test_complete_learner_history_is_not_limited_to_six_turns(selected):
    first_question = "Use a modified inventory starting at seven, and explain one update per visit."
    model = provider(lambda body: dict(outcome="answered", blocks=[prior.explanation(body)]))
    for index in range(8):
        result = run(
            selected,
            model,
            key=f"history-{index}",
            text=first_question
            if index == 0
            else "Keep those earlier assumptions and explain the next step.",
        )
        assert result["status"] == "completed"
    latest = json.loads(model.requests[-1][0][-1]["content"])
    assert len(latest["history"]) == 7
    assert latest["history"][0]["learner_text"] == first_question
    assert all("A loop applies its body once per item" in row["answer"] for row in latest["history"])


def test_another_course_topic_and_checked_calculation_are_preserved(selected):
    _, authority, runtime, scope = selected
    source = "A rate is distance divided by elapsed time. Keep the same units when comparing rates."
    evidence = copy.deepcopy(authority.rows(scope)[0])
    evidence.update(evidence_id=hashlib.sha256(source.encode()).hexdigest(), text=source)
    authority.snapshot["lectures"]["carpentries-python"]["evidence"] = [evidence]
    requests = []

    class RateProvider:
        def decide(self, messages, schemas, timeout):
            body = json.loads(messages[-1]["content"])
            requests.append(copy.deepcopy(body))
            if not body["observations"]:
                return dict(
                    name="search_tutor_evidence",
                    arguments=dict(query="rate distance time"),
                    usage=dict(prompt_tokens=100, completion_tokens=20),
                )
            span = dict(evidence_id=body["evidence"][0]["evidence_id"], first_unit=1, last_unit=1)
            return dict(
                name="finish_tutor_turn",
                arguments=dict(
                    outcome="answered",
                    blocks=[
                        dict(
                            kind="explanation",
                            span=span,
                            text="Under your supplied distance and elapsed time, divide distance by time. This is a derivation, not an observed experiment.",
                        ),
                        dict(kind="calculation", span=span, expression="6/3"),
                    ],
                ),
                usage=dict(prompt_tokens=100, completion_tokens=60),
            )

    first = run(
        selected,
        RateProvider(),
        text="Given distance 6 metres and time 3 seconds, explain and calculate the rate.",
    )
    assert first["status"] == "completed" and "6/3 = 2" in first["answer"]
    second = run(
        selected, RateProvider(), key="rate-followup", text="Keep that example and explain the units."
    )
    assert second["status"] == "completed"
    assert requests[-1]["history"][0]["answer"] == first["answer"]
    assert "6 metres" in requests[-1]["history"][0]["learner_text"]
    assert len(requests) == 4
    retain(
        "authored-other-topic",
        dict(first=first, second=second, generation="SYNTHETIC_COURSE_AND_AUTHORED_RESPONSES"),
    )


def test_old_live_entry_cannot_authorize_modified_candidate():
    from lecturelens_real_eval.tutor.selection_smoke import verify_inputs
    from lecturelens_real_eval.tutor_channel import EvalError

    assert IDENTITY == "phase1c-tutor-repair-development"
    with pytest.raises(EvalError):
        verify_inputs()
