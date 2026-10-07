"""Projection proof and replay mechanics; no real-model quality claims."""

import copy
import json

import pytest
from test_study_atomic import judgment
from test_study_ledger import SCOPE, message, supported

from lecturelens_agent.study.atomic_delta import digest
from lecturelens_agent.study.atomic_review import AtomicAnswerVerdict
from lecturelens_agent.study.context import aliases_in
from lecturelens_agent.study.ledger import facts_from_review, generation_view, valid_fact

ANSWER = (
    '随后执行 v = "blue" 时，Python 解除 v 与原 "red" 对象的绑定，'
    '并将 v 重新绑定到一个全新的字符串对象 "blue"。'
    '由于字符串是不可变的，原 "red" 对象不会被修改，而是保留在内存中'
    "（直到被垃圾回收）。"
)
SOURCE = (
    '执行 v = "blue" 时，变量 v 不再引用原 "red" 对象，重新绑定到一个全新的字符串对象 "blue"。'
    '字符串是不可变的，原 "red" 对象不会被修改，仍保留在内存中。'
)


def review(answer=ANSWER, source=SOURCE):
    body, _, candidate, evidence = message(answer, source=source)
    quality = aliases_in(
        AtomicAnswerVerdict.model_validate(judgment(body), context=body).review().model_dump(),
        {"e1": "canonical"},
    )
    return candidate, quality, evidence


def test_projection_retains_three_relations_with_supported_scope_and_exact_proofs():
    candidate, quality, evidence = review()
    facts = facts_from_review(SCOPE, candidate, quality, evidence)
    assert len(facts) == 3
    assert any('不再引用原来的 "red" 对象' in f["text"] for f in facts)
    assert any('重新绑定到一个全新的字符串对象 "blue"' in f["text"] for f in facts)
    assert any("保留在内存中" in f["text"] for f in facts)
    assert all("垃圾回收" not in f["text"] + f["normalized_claim"] for f in facts)
    for fact in json.loads(json.dumps(facts)):
        assert valid_fact(fact, SCOPE)
        assert len(fact["source_units"]) >= 2
        assert fact["source_run_id"] == SCOPE["run_id"]
        for unit in fact["source_units"]:
            assert unit["supported"] is True and unit["model_supported"] is True
            assert candidate["explanation"][unit["start"] : unit["end"]] == unit["source_text"]
            assert "垃圾回收" not in unit["source_text"]
        if "引用" in fact["text"] or "重新绑定" in fact["text"]:
            assert fact["text"].startswith('随后执行 v = "blue" 时，')
        else:
            assert fact["text"].startswith('由于字符串是不可变的，原 "red" 对象不会被修改，')
    assert len(generation_view(facts, evidence, {"e1": "canonical"})) == 3


@pytest.mark.parametrize("failure", ["rejected", "unknown", "model_unknown", "foreign", "changed_span"])
@pytest.mark.parametrize("premise", ["随后执行", '原 "red" 对象不会'])
def test_missing_or_invalid_premise_cannot_supply_projection_content(failure, premise):
    candidate, quality, evidence = review()
    unit = next(u for u in quality["atomic_assessments"] if u["source_text"].startswith(premise))
    if failure == "unknown":
        quality["atomic_assessments"].remove(unit)
    elif failure == "rejected":
        unit.update(supported=False, model_supported=False, evidence_ids=[])
    elif failure == "model_unknown":
        unit["model_supported"] = None
    elif failure == "foreign":
        unit["evidence_ids"] = ["foreign"]
    else:
        unit["start"] += 1
    facts = facts_from_review(SCOPE, candidate, quality, evidence)
    barred = ("引用", "重新绑定") if premise == "随后执行" else ("保留在内存中",)
    assert not any(word in f["text"] for f in facts for word in barred)


@pytest.mark.parametrize("prefix", ["如果闸门打开，", "因为闸门打开，"])
def test_verified_non_temporal_premise_is_explicit_not_generalized(prefix):
    answer = prefix + '原 "red" 对象保留在内存中。'
    facts = supported(answer, source=answer)
    assert len(facts) == 1 and facts[0]["text"] == answer[:-1]
    assert len(facts[0]["source_units"]) == 2
    assert valid_fact(facts[0], SCOPE)
    assert not supported(answer, source=answer, rejected=[prefix])


def test_trailing_scope_and_quoted_or_question_predicate_fail_closed():
    for answer in [
        '原 "red" 对象保留在内存中，如果闸门打开。',
        '老师说：“执行 v = "blue" 时，原 "red" 对象保留在内存中。”',
        '执行 v = "blue" 时，原 "red" 对象保留在内存中？',
    ]:
        assert not supported(answer, source=answer)


def test_implicit_subject_does_not_come_from_rejected_or_ambiguous_neighbor():
    answer = '原 "red" 对象不会被修改，而是保留在内存中。'
    facts = supported(answer, source=answer)
    assert any('原来的 "red" 对象保留在内存中' == f["text"] for f in facts)
    assert not supported(answer, source=answer, rejected=['原 "red" 对象不会被修改，'])
    ambiguous = '原 "red" 对象与新 "blue" 对象不会被修改，而是保留在内存中。'
    assert not any("保留在内存中" in f["text"] for f in supported(ambiguous, source=ambiguous))


def test_each_contributing_evidence_and_authority_span_survives_projection():
    candidate, quality, evidence = review()
    second = {**evidence[0], "evidence_id": "second", "start_ms": 30, "end_ms": 40}
    evidence.append(second)
    candidate["evidence_ids"].append("second")
    quality["atomic_basis"]["evidence_ids"].append("second")
    quality["atomic_basis"]["evidence"].append(dict(evidence_id="second", text_sha256=digest(second["text"])))
    time = quality["atomic_assessments"][0]
    time["evidence_ids"] = ["second"]
    time["relation"]["grounds"][0]["evidence_id"] = "second"
    fact = next(f for f in facts_from_review(SCOPE, candidate, quality, evidence) if "不再引用" in f["text"])
    assert fact["evidence_ids"] == ["canonical", "second"]
    assert fact["evidence_spans"]["second"] == {"start_ms": 30, "end_ms": 40}
    assert {r for u in fact["source_units"] for r in u["evidence_ids"]} == set(fact["evidence_ids"])
    assert valid_fact(fact, SCOPE)
    changed = copy.deepcopy(evidence)
    changed[-1]["text"] += " altered"
    assert not any("不再引用" in f["text"] for f in facts_from_review(SCOPE, candidate, quality, changed))
    assert generation_view([fact], changed, {"e1": "canonical", "e2": "second"}) == []
    shifted = copy.deepcopy(evidence)
    shifted[-1]["start_ms"] += 1
    assert generation_view([fact], shifted, {"e1": "canonical", "e2": "second"}) == []


@pytest.mark.parametrize("failure", ["drop_premise", "reject_premise", "change_text", "old_version", "scope"])
def test_checkpoint_proof_cannot_drop_a_premise_or_resurrect_prior_policy(failure):
    fact = next(f for f in supported(ANSWER, source=SOURCE) if "不再引用" in f["text"])
    if failure == "drop_premise":
        fact["source_units"] = [fact["source_claim"]]
    elif failure == "reject_premise":
        fact["source_units"][-1]["supported"] = False
    elif failure == "change_text":
        fact["text"] = fact["text"].split("，", 1)[1]
    elif failure == "old_version":
        fact["verifier_version"] = "atomic_ledger_v3"
    else:
        fact["revision"] += 1
    assert valid_fact(fact, SCOPE) is None


def test_global_no_reference_and_gc_never_enter_projection_even_with_model_positive():
    answer = '执行 v = "blue" 后，原 "red" 对象仍保留在内存中（直到被垃圾回收），没有任何变量引用它。'
    facts = supported(answer, source=SOURCE)
    assert facts
    assert all("垃圾回收" not in f["text"] and "没有任何" not in f["text"] for f in facts)
    assert all(not u["strengthening_guards"] for f in facts for u in f["source_units"])


@pytest.mark.parametrize("failure", ["answer_basis", "ambiguous_verdict", "duplicate_evidence_basis"])
def test_mismatched_or_ambiguous_review_cannot_certify_a_projection(failure):
    candidate, quality, evidence = review()
    if failure == "answer_basis":
        quality["atomic_basis"]["answer_sha256"] = digest("Other answer")
    elif failure == "ambiguous_verdict":
        quality["atomic_assessments"].append({**quality["atomic_assessments"][0], "supported": False})
    else:
        quality["atomic_basis"]["evidence"].append(quality["atomic_basis"]["evidence"][0])
    assert facts_from_review(SCOPE, candidate, quality, evidence) == []


@pytest.mark.parametrize(
    "answer",
    [
        "将输入规模表示为 m = 2ᵏ，则 Θ(m) 对应 Θ(2ᵏ)，Θ(log₂ m) 对应 Θ(k)。",
        "若令 m = 2^j，则 Θ(m) 对应 Θ(2^j)，Θ(log₂ m) 对应 Θ(j)。",
        "例如，当 m = 8（k = 3）时，线性规模为 8，对数规模为 3。",
    ],
)
def test_mathematical_projection_keeps_entire_parameter_bound_statement(answer):
    facts = supported(answer, source=answer)
    composite = next(f for f in facts if f["text"] == answer[:-1])
    assert len(composite["source_units"]) >= 3
    assert (
        "".join(u["source_text"] for u in sorted(composite["source_units"], key=lambda u: u["start"]))
        == answer
    )
    assert valid_fact(composite, SCOPE)
    for unit in composite["source_units"]:
        rejected = supported(answer, source=answer, rejected=[unit["source_text"]])
        assert not any(f["text"] == composite["text"] for f in rejected)


def test_math_qualification_and_quotation_are_preserved_without_paraphrase():
    answer = "课程指出 Θ(m) 与 Θ(log₂ m) 有“指数级差异”，将输入规模表示为 m = 2ᵏ 时，Θ(m) 与 Θ(log₂ m) 分别对应 Θ(2ᵏ) 与 Θ(k)。"
    facts = supported(answer, source=answer)
    assert any(f["text"] == answer[:-1] for f in facts)
    assert all("将输入规模表示为" in f["text"] for f in facts if len(f["source_units"]) > 1)


@pytest.mark.parametrize("prefix", ["", '执行 cursor = "cyan" 后，', "因为字符串不可变，"])
def test_same_unit_created_object_binds_rebinding_pronoun_and_retains_scope(prefix):
    unit = '而是创建一个全新的字符串对象 "cyan" 并将 cursor 重新绑定到它。'
    answer = prefix + unit
    facts = supported(answer, source=answer)
    assert len(facts) == 1
    fact = facts[0]
    assert '重新绑定到一个全新的字符串对象 "cyan"' in fact["text"]
    assert "它" not in fact["text"]
    assert prefix.rstrip("，") in fact["text"]
    target = fact["source_claim"]
    assert target["source_text"] == unit
    assert answer[target["start"] : target["end"]] == unit
    assert valid_fact(json.loads(json.dumps(fact)), SCOPE)
    assert len(fact["source_units"]) == (2 if prefix else 1)
    if prefix:
        assert not supported(answer, source=answer, rejected=[prefix])
    assert not supported(answer, source=answer, rejected=[unit])


@pytest.mark.parametrize("failure", ["unknown", "model_unknown", "rejected", "foreign", "span"])
def test_intra_unit_binding_requires_one_authorized_positive_exact_assessment(failure):
    answer = '创建一个全新的对象 "cyan" 并将 cursor 重新绑定到它。'
    candidate, quality, evidence = review(answer, source=answer)
    unit = quality["atomic_assessments"][0]
    if failure == "unknown":
        quality["atomic_assessments"] = []
    elif failure == "model_unknown":
        unit["model_supported"] = None
    elif failure == "rejected":
        unit.update(supported=False, model_supported=False, evidence_ids=[])
    elif failure == "foreign":
        unit["evidence_ids"] = ["foreign"]
    else:
        unit["end"] -= 1
    assert facts_from_review(SCOPE, candidate, quality, evidence) == []


@pytest.mark.parametrize(
    "answer",
    [
        '创建新对象 "cyan" 与新对象 "magenta" 并将 cursor 重新绑定到它。',
        '可能创建新对象 "cyan" 并将 cursor 重新绑定到它。',
        '没有创建新对象 "cyan" 并将 cursor 重新绑定到它。',
        '创建新对象 "cyan" 并将 cursor 永久重新绑定到它。',
        '创建新对象 "cyan"。并将 cursor 重新绑定到它。',
        '新对象 "cyan" 仍在内存中。将 cursor 重新绑定到它。',
        '老师说：“创建新对象 "cyan" 并将 cursor 重新绑定到它。”',
    ],
)
def test_intra_unit_binding_does_not_guess_ambiguity_modality_or_raw_neighbors(answer):
    assert not any("重新绑定到" in f["text"] for f in supported(answer, source=answer))


def test_intra_unit_proof_replays_and_cannot_change_antecedent_or_resurrect_gc():
    unit = '创建一个全新的字符串对象 "cyan" 并将 cursor 重新绑定到它'
    answer = unit + "（直到被垃圾回收）。没有任何变量引用旧对象。"
    source = unit + "。"
    candidate, quality, evidence = review(answer, source=source)
    facts = facts_from_review(SCOPE, candidate, quality, evidence)
    fact = next(f for f in facts if "重新绑定到" in f["text"])
    assert fact["source_claim"]["source_text"] == unit
    assert len(fact["source_units"]) == 1
    assert "垃圾回收" not in fact["text"] and "没有任何" not in fact["text"]
    assert generation_view([fact], evidence, {"e1": "canonical"})
    changed = copy.deepcopy(fact)
    changed["text"] = changed["text"].replace("cyan", "magenta")
    assert valid_fact(changed, SCOPE) is None
    changed = copy.deepcopy(evidence)
    changed[0]["text"] += " changed"
    assert generation_view([fact], changed, {"e1": "canonical"}) == []


@pytest.mark.parametrize("pointer", ["它", "这个新对象", "该新字符串对象"])
@pytest.mark.parametrize("prefix", ["", '执行 cursor = "cyan" 后，', "因为字符串不可变，"])
def test_cross_atomic_rebinding_uses_adjacent_verified_creation_with_scope(prefix, pointer):
    creation = '而是创建一个全新的字符串对象 "cyan"，'
    target = f"并将 cursor 重新绑定到{pointer}。"
    answer = prefix + creation + target
    facts = supported(answer, source=answer)
    fact = next(f for f in facts if "重新绑定到" in f["text"])
    assert '重新绑定到一个全新的字符串对象 "cyan"' in fact["text"]
    assert pointer not in fact["text"]
    assert prefix.rstrip("，") in fact["text"]
    assert fact["source_claim"]["source_text"] == target
    assert len(fact["source_units"]) == (3 if prefix else 2)
    assert creation in [u["source_text"] for u in fact["source_units"]]
    assert valid_fact(json.loads(json.dumps(fact)), SCOPE)
    candidate, quality, evidence = review(answer, source=answer)
    assert generation_view([fact], evidence, {"e1": "canonical"})
    for source in fact["source_units"]:
        assert answer[source["start"] : source["end"]] == source["source_text"]
        assert not any(
            "重新绑定到" in f["text"]
            for f in supported(
                answer,
                source=answer,
                rejected=[source["source_text"]],
            )
        )
    assert facts_from_review(SCOPE, candidate, quality, evidence) == facts


@pytest.mark.parametrize("failure", ["unknown", "model_unknown", "rejected", "foreign", "span", "disjoint"])
@pytest.mark.parametrize("role", ["creation", "target"])
def test_cross_atomic_rebinding_requires_both_exact_positive_compatible_units(failure, role):
    answer = '创建一个全新的字符串对象 "cyan"，并将 cursor 重新绑定到这个新对象。'
    candidate, quality, evidence = review(answer, source=answer)
    unit = quality["atomic_assessments"][0 if role == "creation" else -1]
    if failure == "unknown":
        quality["atomic_assessments"].remove(unit)
    elif failure == "model_unknown":
        unit["model_supported"] = None
    elif failure == "rejected":
        unit.update(supported=False, model_supported=False, evidence_ids=[])
    elif failure == "foreign":
        unit["evidence_ids"] = ["foreign"]
    elif failure == "span":
        unit["end"] -= 1
    else:
        evidence.append({**evidence[0], "evidence_id": "separate"})
        quality["atomic_basis"]["evidence"].append(
            {
                **quality["atomic_basis"]["evidence"][0],
                "evidence_id": "separate",
            }
        )
        quality["atomic_basis"]["evidence_ids"].append("separate")
        candidate["evidence_ids"].append("separate")
        unit["evidence_ids"] = ["separate"]
    assert not any("重新绑定到" in f["text"] for f in facts_from_review(SCOPE, candidate, quality, evidence))


@pytest.mark.parametrize(
    "answer",
    [
        '创建新对象 "cyan" 与新对象 "magenta"，并将 cursor 重新绑定到这个新对象。',
        '可能创建新对象 "cyan"，并将 cursor 重新绑定到这个新对象。',
        '没有创建新对象 "cyan"，并将 cursor 重新绑定到这个新对象。',
        '创建新对象 "cyan"，并将 cursor 永久重新绑定到这个新对象。',
        '创建新对象 "cyan"，并将 cursor 重新绑定到这个新对象（直到被垃圾回收）。',
        '创建新对象 "cyan"。并将 cursor 重新绑定到这个新对象。',
        '创建新对象 "cyan"，旧对象仍在内存中，并将 cursor 重新绑定到这个新对象。',
        '创建对象 "新字符串"，并将 cursor 重新绑定到这个新字符串对象。',
        '创建新对象 "cyan"，并将 cursor 重新绑定到该新字符串对象。',
        '老师说：“创建新对象 "cyan"，并将 cursor 重新绑定到这个新对象。”',
    ],
)
def test_cross_atomic_rebinding_fails_closed_on_ambiguity_scope_or_nonadjacency(answer):
    # A rejected lifetime after the independently verified rebinding cannot
    # strengthen that relation; it may still be published without the lifetime.
    if "直到" in answer:
        facts = supported(answer, source='创建新对象 "cyan"，并将 cursor 重新绑定到这个新对象。')
        assert all("垃圾回收" not in f["text"] for f in facts)
    else:
        assert not any("重新绑定到" in f["text"] for f in supported(answer, source=answer))


@pytest.mark.parametrize("barrier_state", ["supported", "unknown", "rejected"])
def test_cross_atomic_rebinding_never_bridges_an_intervening_unit(barrier_state):
    answer = '创建新对象 "cyan"，对象保持原样，并将 cursor 重新绑定到这个新对象。'
    candidate, quality, evidence = review(answer, source=answer)
    barrier = quality["atomic_assessments"][1]
    if barrier_state == "unknown":
        quality["atomic_assessments"].remove(barrier)
    elif barrier_state == "rejected":
        barrier.update(supported=False, model_supported=False, evidence_ids=[])
    assert not any("重新绑定到" in f["text"] for f in facts_from_review(SCOPE, candidate, quality, evidence))


def test_cross_atomic_proof_replays_and_rejects_dropped_or_changed_antecedent():
    answer = '创建新对象 "cyan"，并将 cursor 重新绑定到这个新对象。没有任何变量引用旧对象。'
    source = answer.split("。")[0] + "。"
    candidate, quality, evidence = review(answer, source=source)
    facts = facts_from_review(SCOPE, candidate, quality, evidence)
    fact = next(f for f in facts if "重新绑定到" in f["text"])
    assert len(fact["source_units"]) == 2
    assert not any("没有任何" in f["text"] for f in facts)
    changed = copy.deepcopy(fact)
    changed["source_units"] = [changed["source_claim"]]
    assert valid_fact(changed, SCOPE) is None
    changed = copy.deepcopy(fact)
    changed["text"] = changed["text"].replace("cyan", "magenta")
    assert valid_fact(changed, SCOPE) is None
    changed = copy.deepcopy(fact)
    changed["source_units"][-1]["source_text"] = '创建新对象 "magenta"，'
    assert valid_fact(changed, SCOPE) is None
    changed = copy.deepcopy(evidence)
    changed[0]["text"] += " changed"
    assert generation_view([fact], changed, {"e1": "canonical"}) == []
