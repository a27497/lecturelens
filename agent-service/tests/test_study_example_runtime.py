import importlib.util
import json
import tarfile
from pathlib import Path

import pytest
import test_study
from test_study_answer_points import draft

from lecturelens_agent.study.contracts import StudyCommand

setup = test_study.setup


@pytest.mark.parametrize("checkpoint", ["none", "current", "prior_runtime"])
def test_computed_observation_drives_draft_and_survives_checkpoint_recovery(
    setup, monkeypatch, tmp_path, checkpoint
):
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
    if checkpoint != "none":

        def save(*args, **kwargs):
            result = original_save(*args, **kwargs)
            if "example_check" in result:
                store.save_tool = original_save
                raise SystemExit("after private tool commit")
            return result

        store.save_tool = save
        with monkeypatch.context() as patch:
            if checkpoint == "prior_runtime":
                fixture = Path(__file__).parent / "fixtures/study-decision-prior-source.tar.gz"
                with tarfile.open(fixture) as archive:
                    archive.extractall(tmp_path, filter="data")
                spec = importlib.util.spec_from_file_location(
                    "lecturelens_agent.study._prior_runtime", tmp_path / "study/runtime.py"
                )
                prior = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(prior)
                patch.setattr(prior, "check_example", check)
                patch.setattr(runtime, "graph", prior.StudyRuntime.graph.__get__(runtime))
            with pytest.raises(SystemExit, match="after private tool commit"):
                runtime.execute(run)
        assert test_study.read(setup)["run"]["status"] == "running"
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
        journal = conn.execute(
            "SELECT tool_name,result FROM study_tool_result WHERE run_id=%s ORDER BY call_id",
            (run["run_id"],),
        ).fetchall()
    assert [row["tool_name"] for row in journal] == [
        "search_course_evidence",
        "check_python_example",
        "create_practice_set",
    ]
    assert journal[-1]["result"]["quality"]["accepted"] is True


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
