import copy
import json

import pytest
import test_study
from pydantic import ValidationError
from test_study_answer_points import draft

from lecturelens_agent.study.contracts import StudyCommand, materialize_practice
from lecturelens_agent.study.solution import BlindSolutionVerdict, solution_fingerprint, solution_messages

setup = test_study.setup  # Reuse the real PostgreSQL fixture.


def test_solution_input_hides_original_answers_rubric_explanation_and_changes_with_question():
    candidate = materialize_practice(draft())
    candidate["explanation"] = "PRIVATE EXPLANATION"
    candidate["questions"][0].update(
        answer="PRIVATE ANSWER", rubric="PRIVATE RULE", answer_points=["PRIVATE POINT"]
    )
    evidence = [{"evidence_id": "caption-a", "text": "Course fact"}]
    messages = solution_messages("goal", candidate, evidence)
    assert "PRIVATE" not in json.dumps(messages)
    body = json.loads(messages[-1]["content"])
    old = solution_fingerprint(body)
    candidate["questions"][0]["answer_points"] = ["a changed proposed answer"]
    assert (
        solution_fingerprint(json.loads(solution_messages("goal", candidate, evidence)[-1]["content"])) == old
    )
    for changed in ("question", "evidence_ids"):
        updated = copy.deepcopy(candidate)
        updated["questions"][0][changed] = "Different question" if changed == "question" else ["caption-b"]
        assert (
            solution_fingerprint(json.loads(solution_messages("goal", updated, evidence)[-1]["content"]))
            != old
        )
    evidence[0]["text"] = "A different course fact"
    assert (
        solution_fingerprint(json.loads(solution_messages("goal", candidate, evidence)[-1]["content"])) != old
    )


def test_independent_solution_requires_own_evidence():
    body = json.loads(
        solution_messages(
            "goal",
            materialize_practice(draft()),
            [
                {"evidence_id": "caption-a", "text": "None"},
                {"evidence_id": "caption-b", "text": "Both prints"},
            ],
        )[-1]["content"]
    )
    valid = {
        "questions": [
            {"answer": "None", "evidence": ["e1"]},
            {"answer": "inner then None", "evidence": ["e2"]},
        ]
    }
    result = BlindSolutionVerdict.model_validate(valid, context=body).solution(body)
    assert result.answers[1].grounds[0].quote == "Both prints"
    valid["questions"][1]["evidence"] = ["e1"]
    with pytest.raises(ValidationError):
        BlindSolutionVerdict.model_validate(valid, context=body)


def test_computation_observations_reach_solver_and_invalidate_cached_solution():
    candidate = materialize_practice(draft())
    evidence = [{"evidence_id": "caption-a", "text": "String slicing"}]
    checks = [
        {
            "program": "print('l' + 'world'[2:])",
            "evidence_ids": ["caption-a"],
            "status": "computed",
            "stdout": "lrld\n",
        }
    ]

    def body(observations):
        return json.loads(solution_messages("goal", candidate, evidence, observations)[-1]["content"])

    actual = body(checks)
    assert actual["example_checks"][0]["stdout"] == "lrld\n"
    assert actual["example_checks"][0]["evidence_ids"] == ["e1"]
    assert solution_fingerprint(actual) != solution_fingerprint(body(None))
    checks[0]["status"] = "unsupported"
    assert solution_fingerprint(actual) != solution_fingerprint(body(checks))


@pytest.mark.parametrize("changed_question,crash", [(False, False), (False, True), (True, False)])
def test_solution_reuse_is_persistent_scoped_and_never_expands_six_call_budget(
    setup,
    changed_question,
    crash,
):
    store, _, runtime, scope = setup
    runtime.independent_solutions = True
    solves, reviews = [], []

    class Provider:
        mode = "real"

        def decide(self, messages, timeout):
            body = json.loads(messages[-1]["content"])
            if not body["evidence"]:
                return {"name": "search_course_evidence", "arguments": {"query": "stopping condition"}}
            revision = bool(body.get("quality"))
            data = draft()
            data["evidence_ids"] = ["e1"]
            for i, q in enumerate(data["questions"]):
                q["evidence_ids"] = ["e1"]
                q["answer_points"] = ["corrected" if revision else "original"]
                if changed_question and revision and i == 1:
                    q["question"] += " Explain a different example."
            return {"name": "create_practice_set", "arguments": data}

        def review(self, messages, timeout):
            body = json.loads(messages[-1]["content"])
            if body.get("review_mode") == "independent_solution":
                solves.append(body)
                solved = BlindSolutionVerdict.model_validate(
                    {
                        "questions": [
                            {"answer": "Independent course result", "evidence": ["e1"]},
                            {"answer": "Independent application result", "evidence": ["e1"]},
                        ]
                    },
                    context=body,
                ).solution(body)
                return {"solution": solved.model_dump()}
            assert body["independent_solution"]["answers"][0]["evidence_ids"] == ["e1"]
            reviews.append(body)
            return {
                "review": {
                    "issues": ["incorrect_answer"] if len(reviews) == 1 else [],
                    "feedback": "Correct only the proposed answer.",
                }
            }

    runtime.provider = Provider()
    command = StudyCommand(
        **scope, operation="START", request_key="independent", goal="Explain stopping conditions"
    )
    result = store.command(command, "real")
    run = next(r for r in store.candidates() if r["run_id"] == result["run"]["run_id"])
    original = store.save_tool
    if crash:

        def crash_after_commit(*args, **kwargs):
            result = original(*args, **kwargs)
            if result.get("quality", {}).get("independent_solution"):
                store.save_tool = original
                raise SystemExit("crash after durable rejected draft")
            return result

        store.save_tool = crash_after_commit
        with pytest.raises(SystemExit):
            runtime.execute(run)
    runtime.execute(run)
    response = store.command(StudyCommand(**scope, operation="READ"), "real")
    assert response["run"]["model_calls"] == 6
    assert len(solves) == (2 if changed_question else 1)
    assert response["run"]["status"] == ("budget_exceeded" if changed_question else "succeeded")
    if changed_question:
        assert response["artifact"] is None
    assert "Independent course result" not in json.dumps(response, default=str)
