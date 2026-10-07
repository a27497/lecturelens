import json

import pytest
from pydantic import ValidationError
from test_study import read, setup, start  # noqa: F401

from lecturelens_agent.study.answer_review import ExplanationVerdict
from lecturelens_agent.study.goals import explanation_claims, goal_constraints
from lecturelens_agent.study.quality import review_messages as current_review_messages
from lecturelens_agent.study.quality import review_schema


def review_messages(*args, **kwargs):
    """Historical v1 contract/replay regression; atomic default is tested separately."""
    return current_review_messages(*args, **kwargs, answer_review_mode="answer_support_v1")


SOURCE = "s refers to a new 'help' object. The old 'hello' object still is in memory somewhere; s no longer refers to it."
ANSWER = "s 改为指向新建的 help 对象，新旧对象不同。原来的 hello 已不由 s 引用，但按老师这段解释，它当时仍存在内存的某处。"


def body(goal, answer):
    return json.loads(
        review_messages(
            goal,
            {
                "kind": "explanation",
                "title": "状态变化",
                "explanation": answer,
                "evidence_ids": ["canonical"],
            },
            [{"evidence_id": "canonical", "text": SOURCE, "start_ms": 91330, "end_ms": 107210}],
        )[-1]["content"]
    )


def judgment(input_body, matches=True):
    return {
        "goal_checks": [
            {
                "id": c["id"],
                "matches": matches,
                "observation": "当前答案说明了变量指向、新旧对象区别和旧对象当时的存在状态。"
                if matches
                else "当前答案遗漏旧对象的去向。",
                "answer_quotes": [input_body["candidate"]["explanation"]] if matches else [],
            }
            for c in goal_constraints(input_body["goal"])
        ],
        "explanation_checks": [
            {
                "id": c["id"],
                "supported": True,
                "course_fact": "变量重新指向新对象，旧对象仍在内存而未由该变量引用。",
                "evidence_ids": ["e1"],
            }
            for c in explanation_claims(input_body["candidate"]["explanation"])
        ],
    }


@pytest.mark.parametrize(
    "goal",
    [
        "那原来那个 'hello' 对象后来怎么样了？",
        "重新赋值后，原值对应的对象和变量还有什么关系？",
        "新值出现时，两个对象的身份和旧对象的状态如何？",
    ],
)
def test_current_answer_can_express_object_state_independently_of_exercises(goal):
    input_body = body(goal, ANSWER)
    verdict = ExplanationVerdict.model_validate(judgment(input_body), context=input_body)
    assert verdict.review().issues == []
    assert review_schema("explanation", review_mode="answer_support_v1")["function"]["parameters"]["required"]


def test_evidence_fact_does_not_fill_an_omission_in_the_answer():
    input_body = body(
        "Explain what happens to the old object after rebinding.",
        "Rebinding changes which object the variable refers to.",
    )
    assert SOURCE in input_body["evidence"][0]["text"]
    verdict = ExplanationVerdict.model_validate(judgment(input_body, False), context=input_body)
    assert verdict.review().issues == ["goal_mismatch"]
    false_acceptance = judgment(input_body)
    false_acceptance["goal_checks"][0]["answer_quotes"] = [
        "The old 'hello' object still is in memory somewhere"
    ]
    with pytest.raises(ValidationError, match="actual answer"):
        ExplanationVerdict.model_validate(false_acceptance, context=input_body)


@pytest.mark.parametrize("crash", [False, True])
def test_standalone_answer_is_authorized_persisted_and_replayed(setup, crash):  # noqa: F811
    store, authority, runtime, _ = setup
    original = runtime.provider.decide

    def decide(messages, timeout):
        data = json.loads(messages[-1]["content"])
        if not data["evidence"]:
            return original(messages, timeout)
        return {
            "name": "create_explanation",
            "arguments": {
                "title": "停止条件",
                "explanation": "算法必须有停止条件，避免无止境地执行。",
                "evidence_ids": ["e1"],
            },
        }

    runtime.provider.decide = decide
    original_save = store.save_tool
    if crash:

        def save(*args, **kwargs):
            result = original_save(*args, **kwargs)
            if result.get("artifact_id"):
                store.save_tool = original_save
                raise SystemExit("after persisted answer")
            return result

        store.save_tool = save
        with pytest.raises(SystemExit):
            runtime.execute(start(setup))
    runtime.execute(start(setup))
    artifact = read(setup)["artifact"]
    assert artifact["kind"] == "explanation"
    assert artifact["questions"] == []
    assert artifact["citations"][0]["evidence_id"] == "e1"
    assert read(setup)["run"]["status"] == "succeeded"
    assert "CHECK" in authority.reads
