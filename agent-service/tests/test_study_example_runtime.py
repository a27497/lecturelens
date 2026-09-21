import json

import pytest
import test_study
from test_study_answer_points import draft

from lecturelens_agent.study.contracts import StudyCommand

setup = test_study.setup


@pytest.mark.parametrize("crash", [False, True])
def test_computed_observation_drives_draft_and_survives_checkpoint_recovery(setup, monkeypatch, crash):
    import lecturelens_agent.study.runtime as module

    store, _, runtime, scope = setup
    computed, observations = [], []
    original_check = module.check_example
    original_review = runtime.provider.review

    def check(program):
        computed.append(program)
        return original_check(program)

    monkeypatch.setattr(module, "check_example", check)

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {"name": "search_course_evidence", "arguments": {"query": "string slices"}}
        if not any(h["tool"] == "check_python_example" for h in body["history"]):
            return {
                "name": "check_python_example",
                "arguments": {"program": "s = 'world'\nprint('l' + s[2:])", "evidence_ids": ["e1"]},
            }
        observations.append(body["example_check"])
        data = draft()
        data["evidence_ids"] = ["e1"]
        for q in data["questions"]:
            q["evidence_ids"] = ["e1"]
            q["answer_points"] = [body["example_check"]["stdout"].strip()]
        return {"name": "create_practice_set", "arguments": data}

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        assert body["example_checks"][0]["stdout"] == "lrld\n"
        assert body["example_checks"][0]["evidence_ids"] == ["e1"]
        return original_review(messages, timeout)

    runtime.provider.decide, runtime.provider.review = decide, review
    run = test_study.start(setup)
    original_save = store.save_tool
    if crash:

        def save(*args, **kwargs):
            result = original_save(*args, **kwargs)
            if "example_check" in result:
                store.save_tool = original_save
                raise SystemExit("after private tool commit")
            return result

        store.save_tool = save
        with pytest.raises(SystemExit):
            runtime.execute(run)
    runtime.execute(run)
    response = test_study.read(setup)
    assert response["run"]["status"] == "succeeded"
    assert response["run"]["tool_calls"] == 3 and response["run"]["model_calls"] == 4
    assert len(computed) == 1 and observations[0]["stdout"] == "lrld\n"
    private = store.command(StudyCommand(**scope, operation="ANSWERS"), "mock")
    assert private["questions"][0]["answer"] == "lrld"
    events = test_study.read(setup, "EVENTS")["events"]
    assert "lrld" not in json.dumps(events, default=str)
    assert "world" not in json.dumps(events, default=str)
    with store.connect() as conn:
        row = conn.execute(
            "SELECT result FROM study_tool_result WHERE run_id=%s AND tool_name='create_practice_set'",
            (run["run_id"],),
        ).fetchone()
    assert row["result"]["quality"]["accepted"] is True


def test_example_checker_cannot_reference_another_courses_evidence(setup, monkeypatch):
    import lecturelens_agent.study.runtime as module

    _, _, runtime, _ = setup
    original = runtime.provider.decide
    called = []
    monkeypatch.setattr(module, "check_example", lambda _: called.append(True))

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if body["evidence"]:
            return {
                "name": "check_python_example",
                "arguments": {"program": "print(1)", "evidence_ids": ["foreign-evidence"]},
            }
        return original(messages, timeout)

    runtime.provider.decide = decide
    runtime.execute(test_study.start(setup))
    assert test_study.read(setup)["run"]["error_code"] == "UNSUPPORTED_CITATION"
    assert not called
