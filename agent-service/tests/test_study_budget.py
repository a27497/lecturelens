"""Synthetic overlap regression; deterministic providers establish mechanics only."""

import json

import pytest
import test_study
from test_study_goals import goal_verdict

from lecturelens_agent.study import call_journal
from lecturelens_agent.study.quality import review_contract
from lecturelens_agent.study.store import BudgetExceeded, RunStopped
from lecturelens_agent.study.support_review import MethodCoverageVerdict

setup = test_study.setup


def overlap_scenario(setup, monkeypatch, *, batch=True, recover=False):
    store, authority, runtime, _ = setup
    sources = [
        {
            "evidence_id": f"owned-caption-{i}-" + "x" * 60,
            "text": ("算法需要停止条件。计数达到上限时停止，否则继续。例：计数2、上限3，继续。" * 12),
            "start_ms": i * 10000,
            "end_ms": i * 10000 + 1000,
            "source_type": "OCR",
        }
        for i in range(8)
    ]
    original = authority.read
    searches = []
    requests = []
    begin = call_journal.begin

    def record_request(*args, **kwargs):
        requests.append(args[4])
        return begin(*args, **kwargs)

    monkeypatch.setattr(call_journal, "begin", record_request)

    def read(run, action="CHECK", **kwargs):
        response = original(run, action, **kwargs)
        if action == "SEARCH":
            ids = [0, 1, 2, 3, 4, 5] if not searches else [0, 1, 2, 3, 4, 6]
            searches.append(ids)
        elif action == "WINDOW":
            ids = [4, 6, 7]
        else:
            ids = [
                i
                for i, source in enumerate(sources)
                if source["evidence_id"] in kwargs.get("evidence_ids", [])
            ]
        return {**response, "evidence": [dict(sources[i]) for i in ids]}

    def search(query):
        return {"name": "search_course_evidence", "arguments": {"query": query, "practice_kind": "general"}}

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        history = body["history"]
        if not history:
            calls = [search("stopping condition"), search("check count against limit")]
            return {"calls": calls if batch else calls[:1]}
        if len(history) == 1:
            return search("check count against limit")
        if len(history) == 2:
            return {
                "name": "read_evidence_window",
                "arguments": {"evidence_id": body["evidence"][0]["evidence_id"]},
            }
        ref = body["course_coverage"]["methods"]["m1"]["evidence_id"]
        return {
            "name": "create_practice_set",
            "arguments": {
                "title": "停止条件练习",
                "explanation": "算法需要停止条件。计数达到上限时停止，否则继续。",
                "evidence_ids": [ref],
                "concept": {
                    "question": "停止条件有什么作用？",
                    "answer_points": ["判断算法继续还是停止。"],
                    "evidence_ids": [ref],
                },
                "application": {
                    "question": "计数为3、上限为3，此时应继续还是停止？",
                    "answer_points": ["计数达到上限，应停止。"],
                    "evidence_ids": [ref],
                },
                "method_id": "m1",
            },
        }

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if body["review_mode"] == "course_methods_v1":
            data = {
                "course_fact": "Check a stopping condition",
                "evidence_ids": ["e1"],
                "support": "direct",
                "missing_goal_quote": "",
                "methods": [
                    {
                        "operation": "Check count against limit",
                        "input": "Count and limit",
                        "output": "Continue or stop",
                        "evidence_id": "e1",
                    }
                ],
            }
            result = MethodCoverageVerdict.model_validate(data, context=body).review()
        else:
            data = goal_verdict(body)
            data["application_method_check"] = data["checks"][2].pop("method_alignment")
            result = (
                review_contract(review_mode=body["review_mode"]).model_validate(data, context=body).review()
            )
        return {"review": result.model_dump()}

    authority.read = read
    runtime.provider.decide, runtime.provider.review = decide, review
    save_tool = store.save_tool
    interrupted = False

    def save(*args, **kwargs):
        nonlocal interrupted
        if (
            recover
            and not interrupted
            and args[3] == "search_course_evidence"
            and args[5].get("reused_method_observation")
        ):
            interrupted = True
            raise RunStopped()
        return save_tool(*args, **kwargs)

    monkeypatch.setattr(store, "save_tool", save)
    run = test_study.start(setup)
    runtime.execute(run)
    if recover:
        assert interrupted and test_study.read(setup)["run"]["status"] == "running"
        runtime.execute(run)
    response = test_study.read(setup)
    with store.connect() as conn:
        models = conn.execute(
            "SELECT metadata,reserved_tokens FROM study_model_call WHERE run_id=%s ORDER BY metadata->>'attempt'",
            (run["run_id"],),
        ).fetchall()
        results = conn.execute(
            "SELECT result FROM study_tool_result WHERE run_id=%s", (run["run_id"],)
        ).fetchall()
    observations = sum(row["metadata"].get("review_stage") == "course_methods_v1" for row in models)
    summary = {
        k: response["run"][k]
        for k in ("status", "error_code", "model_calls", "tool_calls", "reserved_tokens")
    }
    summary.update(
        reservations=[row["reserved_tokens"] for row in models],
        method_observations=observations,
        duplicate_observations=max(0, observations - 1),
        reused_observations=sum(bool(r["result"].get("reused_method_observation")) for r in results),
        requested_reservations=requests,
    )
    print("BUDGET_SCENARIO", json.dumps({"batch": batch, **summary}, sort_keys=True))
    return response, summary, searches


@pytest.mark.parametrize("recover", [False, True])
def test_overlapping_searches_and_window_complete_within_unchanged_budget(setup, monkeypatch, recover):
    response, summary, searches = overlap_scenario(setup, monkeypatch, recover=recover)
    assert len(searches) == (3 if recover else 2) and len(set(searches[0]) & set(searches[1])) == 5
    assert response["run"]["status"] == "succeeded", summary
    assert response["artifact"]["explanation"] and len(response["artifact"]["questions"]) == 2
    assert len(test_study.read(setup, "ANSWERS")["questions"]) == 2
    assert summary["model_calls"] == 5
    assert summary["tool_calls"] == 4
    assert summary["method_observations"] == 1 and summary["duplicate_observations"] == 0
    assert summary["reserved_tokens"] <= 64000
    assert summary["reserved_tokens"] == sum(summary["reservations"])
    events = test_study.read(setup, "EVENTS")["events"]
    assert sum(e["event_type"] == "artifact_created" for e in events) == 1
    assert sum(e["event_type"] == "quality_checked" for e in events) == 1
    store = setup[0]
    with store.connect() as conn:
        private = conn.execute(
            "SELECT content FROM study_artifact WHERE run_id=%s", (response["run"]["run_id"],)
        ).fetchone()["content"]
    assert private["questions"][1]["answer_points"] == ["计数达到上限，应停止。"]
    assert private["questions"][1]["evidence_ids"] == ["owned-caption-0-" + "x" * 60]


def test_long_serial_searches_stop_with_specific_budget_reason_and_no_artifact(setup, monkeypatch):
    response, summary, _ = overlap_scenario(setup, monkeypatch, batch=False)
    assert response["run"]["status"] == "budget_exceeded" and response["artifact"] is None
    assert response["run"]["error_code"] == "RUN_BUDGET_EXCEEDED"
    events = test_study.read(setup, "EVENTS")["events"]
    rejected = next(e["payload"] for e in events if e["event_type"] == "budget_rejected")
    assert rejected["reason"] == "reserved_tokens" and rejected["purpose"] == "decision"
    assert rejected["remaining_tokens"] == 64000 - summary["reserved_tokens"]
    assert rejected["requested_tokens"] == summary["requested_reservations"][-1]
    assert rejected["requested_tokens"] > rejected["remaining_tokens"]
    assert rejected["reservation"]["message_bytes"] > 0
    assert rejected["operation_key"] and rejected["node"] == "decide"
    assert not any(e["event_type"] == "artifact_created" for e in events)


@pytest.mark.parametrize(
    "used,requested,allowed", [(63900, 100, True), (63900, 101, False), (64000, 1, False)]
)
def test_model_reservation_exact_boundary_and_replay_are_atomic(setup, used, requested, allowed):
    store, _, _, _ = setup
    run = test_study.start(setup)
    store.claim(run["run_id"], "budget-test", 90)
    with store.connect() as conn:
        conn.execute("UPDATE study_run SET reserved_tokens=%s WHERE run_id=%s", (used, run["run_id"]))
    args = (
        store,
        run["run_id"],
        "budget-test",
        "slot",
        requested,
        {"purpose": "decision"},
        {"messages": [], "schemas": []},
    )
    if allowed:
        prior, metadata = call_journal.begin(*args)
        assert prior is None
        call_journal.complete(
            store, run["run_id"], "budget-test", "slot", metadata, {}, response={"ok": True}
        )
        prior, _ = call_journal.begin(*args)
        assert call_journal.replay(prior) == {"ok": True}
        assert store.guard(run["run_id"], "budget-test")["reserved_tokens"] == used + requested
        assert store.guard(run["run_id"], "budget-test")["model_calls"] == 1
    else:
        with pytest.raises(BudgetExceeded) as raised:
            call_journal.begin(*args)
        error = raised.value
        assert error.diagnostics["reason"] == "reserved_tokens"
        assert error.diagnostics["requested_tokens"] == requested
        assert store.guard(run["run_id"], "budget-test")["reserved_tokens"] == used
        store.finish(
            run["run_id"],
            "budget-test",
            "budget_exceeded",
            "RUN_BUDGET_EXCEEDED",
            budget_diagnostics=error.diagnostics,
        )
        events = test_study.read(setup, "EVENTS")["events"]
        assert not any(e["event_type"] == "model_started" for e in events)
        assert events[-1]["payload"]["error_code"] == "RUN_BUDGET_EXCEEDED"


@pytest.mark.parametrize("resource", ["model_calls", "tool_calls", "deadline"])
def test_budget_diagnostic_keeps_public_error_code_and_stops_before_artifact(setup, resource):
    store, _, runtime, _ = setup
    run = test_study.start(setup)
    assignment = {
        "model_calls": "model_calls=6",
        "tool_calls": "tool_calls=8",
        "deadline": "deadline=now()-interval '1 second'",
    }[resource]
    with store.connect() as conn:
        conn.execute(f"UPDATE study_run SET {assignment} WHERE run_id=%s", (run["run_id"],))
    runtime.execute(run)
    response = test_study.read(setup)
    assert response["run"]["status"] == "budget_exceeded" and response["artifact"] is None
    assert response["run"]["error_code"] == "RUN_BUDGET_EXCEEDED"
    events = test_study.read(setup, "EVENTS")["events"]
    assert next(e["payload"] for e in events if e["event_type"] == "budget_rejected")["reason"] == resource
