"""Independent follow-up reproductions and opt-in v16 mechanisms, not model quality."""

import json
import os
from pathlib import Path

import pytest
import test_tutor_v15 as legacy

from lecturelens_real_eval.tutor.verified_runtime import HINTS, VerifiedTutorRuntime, calculate

lab, offline = legacy.lab, legacy.offline
Provider, block, run = legacy.Provider, legacy.block, legacy.run


def retain(name, value):
    output = Path(os.environ["TUTOR_FOLLOWUP_OUTPUT"])
    (output / (name + ".json")).write_text(json.dumps(value, indent=2, default=str) + "\n")


def test_reproduce_v15_arbitrary_claim_in_answer_and_feedback(lab):
    def finish(body):
        return {
            "outcome": "answered",
            "blocks": [block(body, "Every loop cures influenza.")],
            "evaluation_blocks": [block(body, "Your reply proves permanent mastery.")],
        }

    result = run(lab, Provider(finish))
    retain("v15-a03-reproduction", result)
    assert result["status"] == "completed"
    assert "cures influenza" in result["answer"] and "permanent mastery" in result["evaluation"]


def test_reproduce_v15_paraphrased_complete_solution(lab):
    answer = "Add seventy-five, twenty and two to obtain ninety-seven. Can you repeat these steps?"
    result = run(
        lab,
        Provider(lambda body: {"outcome": "socratic_prompt", "blocks": [block(body, answer)]}),
        socratic=True,
    )
    retain("v15-a12-reproduction", result)
    assert result["status"] == "completed" and "ninety-seven" in result["answer"]


@pytest.fixture
def verified_lab(lab):
    store, authority, _, scope = lab
    runtime = VerifiedTutorRuntime(store, authority)
    runtime.initialize()
    try:
        yield store, authority, runtime, scope
    finally:
        runtime.close()


def excerpt(body):
    source = body["evidence"][0]
    return {"kind": "source", "evidence_id": source["evidence_id"], "text": source["text"][:100]}


def hint(body, intent="trace_state"):
    value = excerpt(body)
    return {"evidence_id": value["evidence_id"], "quote": value["text"], "intent": intent}


def test_verified_source_publication_retains_full_binding_and_restart(verified_lab):
    result = run(verified_lab, Provider(lambda body: {"outcome": "answered", "blocks": [excerpt(body)]}))
    assert result["status"] == "completed"
    assert result["citations"][0]["text"].startswith(result["answer"].split("\n", 1)[1].rsplit(" [", 1)[0])
    store, authority, _, scope = verified_lab
    from lecturelens_real_eval.tutor.contracts import Command

    restored = VerifiedTutorRuntime(store, authority).command(Command(**scope, operation="GET"))
    assert restored["turns"][0]["answer"] == result["answer"]
    retain("v16-source-publication", result)


@pytest.mark.parametrize(
    "text",
    [
        "Every loop cures influenza.",
        "所有循环都能保证永久掌握。",
        "Loops prove that every learner is correct.",
    ],
)
def test_verified_arbitrary_course_claim_cannot_use_real_anchor(verified_lab, text):
    provider = Provider(lambda body: {"outcome": "answered", "blocks": [{**excerpt(body), "text": text}]})
    result = run(verified_lab, provider)
    assert result["status"] == "failed" and result["error_code"] == "TUTOR_SUPPORT_INVALID"
    assert result["answer"] is None and not result["citations"] and len(provider.requests) == 3
    retain("v16-a03-rejection", result)


def test_verified_repairs_claim_without_dropping_source_content(verified_lab):
    def finish(body):
        item = excerpt(body)
        if "rejected_blocks" not in body:
            item["text"] = "A new unsupported assertion."
        return {"outcome": "answered", "blocks": [item]}

    provider = Provider(finish)
    result = run(verified_lab, provider)
    assert result["status"] == "completed" and len(provider.requests) == 3
    assert "unsupported assertion" not in result["answer"]


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("2 + 1 + 1", "4"),
        ("2 + 2*2**2 + 3*2**2", "22"),
        ("0.1+0.2", "3/10"),
        ("-7//2", "-4"),
        ("7%2", "1"),
        ("[2,2+1,2+1+1]", "[2, 3, 4]"),
        ("[range(1,4),range(1,4,2)]", "[[1, 2, 3], [1, 3]]"),
    ],
)
def test_verified_calculation_exact_bounded_arithmetic(expression, expected):
    assert calculate(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "x+1",
        "(2).__class__",
        "1/0",
        "2**99",
        "1e309",
        "True+1",
        "9**12*9**12",
        "[1][0]",
        "-[1]",
        "[1]+[2]",
        "range(1000000000)",
        "range(0,3,0)",
        "[x for x in range(3)]",
        "1" * 121,
    ],
)
def test_verified_calculation_rejects_code_and_capacity(expression):
    from lecturelens_agent.study.store import StudyError

    with pytest.raises(StudyError, match="TUTOR_CALCULATION_INVALID"):
        calculate(expression)


def test_verified_model_selects_calculation_controller_generates_conclusion(verified_lab):
    def finish(body):
        value = hint(body)
        return {
            "outcome": "answered",
            "blocks": [
                excerpt(body),
                {
                    "kind": "calculation",
                    "evidence_id": value["evidence_id"],
                    "quote": value["quote"],
                    "expression": "2+1+1",
                },
            ],
        }

    result = run(verified_lab, Provider(finish))
    assert result["status"] == "completed" and "Derived: 2+1+1 = 4" in result["answer"]
    retain("v16-calculation-publication", result)


@pytest.mark.parametrize("intent", list(HINTS))
def test_verified_socratic_act_has_no_free_solution_channel(verified_lab, intent):
    result = run(
        verified_lab,
        Provider(lambda body: {"outcome": "socratic_prompt", "hint": hint(body, intent)}),
        socratic=True,
    )
    assert result["status"] == "completed" and HINTS[intent] in result["answer"]
    visible_question = result["answer"].rsplit(" [", 1)[0]
    assert "ninety-seven" not in visible_question and "97" not in visible_question


@pytest.mark.parametrize("payload", ["source", "hint_extra", "hint_intent", "feedback"])
def test_verified_paraphrased_solution_cannot_bypass_typed_hint(verified_lab, payload):
    answer = "Add seventy-five, twenty and two to obtain ninety-seven. Can you repeat these steps?"

    def finish(body):
        data = {"outcome": "socratic_prompt", "hint": hint(body)}
        if payload == "source":
            data["blocks"] = [{**excerpt(body), "text": answer}]
        elif payload == "hint_extra":
            data["hint"]["text"] = answer
        elif payload == "hint_intent":
            data["hint"]["intent"] = answer
        else:
            data["evaluation_blocks"] = [
                {
                    "evidence_id": excerpt(body)["evidence_id"],
                    "learner_quote": "Explain",
                    "quote": excerpt(body)["text"][:80],
                }
            ]
        return data

    result = run(verified_lab, Provider(finish), socratic=True)
    assert result["status"] == "failed" and result["answer"] is None and result["evaluation"] is None
    retain("v16-a12-rejection-" + payload, result)


def test_verified_feedback_compares_actual_reply_without_invented_grade(verified_lab):
    run(
        verified_lab,
        Provider(lambda body: {"outcome": "socratic_prompt", "hint": hint(body)}),
        key="hint",
        socratic=True,
    )

    def finish(body):
        item = excerpt(body)
        return {
            "outcome": "answered",
            "blocks": [item],
            "evaluation_blocks": [
                {"evidence_id": item["evidence_id"], "learner_quote": "restores", "quote": item["text"][:90]}
            ],
        }

    result = run(verified_lab, Provider(finish), key="reply", text="I think it restores the old value.")
    assert result["status"] == "completed" and "Your reply: restores" in result["evaluation"]
    assert "mastery" not in result["evaluation"]
    retain("v16-feedback-comparison", result)


def test_verified_feedback_cannot_claim_unseen_learner_words(verified_lab):
    def finish(body):
        item = excerpt(body)
        return {
            "outcome": "answered",
            "blocks": [item],
            "evaluation_blocks": [
                {
                    "evidence_id": item["evidence_id"],
                    "learner_quote": "I proved mastery",
                    "quote": item["text"][:90],
                }
            ],
        }

    result = run(verified_lab, Provider(finish))
    assert result["status"] == "failed" and result["error_code"] == "TUTOR_SUPPORT_INVALID"


def test_verified_exact_quote_format_repair_preserves_oversized_input(verified_lab):
    def finish(body):
        item = excerpt(body)
        item["text"] = body["evidence"][0]["text"][: 301 if "rejected_blocks" not in body else 300]
        return {"outcome": "answered", "blocks": [item]}

    provider = Provider(finish)
    result = run(verified_lab, provider)
    assert result["status"] == "completed" and len(provider.requests) == 3
    body = json.loads(provider.requests[-1][0][-1]["content"])
    assert len(body["rejected_blocks"]["blocks"][0]["text"]) == 301


def test_verified_foreign_citation_cannot_get_support_repair(verified_lab):
    result = run(
        verified_lab,
        Provider(
            lambda body: {"outcome": "answered", "blocks": [{**excerpt(body), "evidence_id": "foreign"}]}
        ),
    )
    assert result["error_code"] == "TUTOR_CITATION_MISMATCH" and not result["citations"]


def test_verified_factory_rejects_real_mode(monkeypatch):
    from starlette.testclient import TestClient

    from lecturelens_real_eval.tutor.verified_app import create_app

    monkeypatch.setenv("AGENT_LLM_MODE", "real")
    with pytest.raises(Exception, match="MOCK"):
        with TestClient(create_app()):
            pytest.fail("Real startup must never be admitted")
