"""Ledger authority, canonical equivalence and PostgreSQL recovery mechanics."""

import json

import httpx
import pytest
from test_study import read, setup  # noqa: F401
from test_study_atomic import judgment, response

from lecturelens_agent.study.atomic import atomic_claims
from lecturelens_agent.study.atomic_review import AtomicAnswerVerdict, DeltaAtomicAnswerVerdict
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.ledger import canonical_claim, facts_from_review, generation_view, valid_fact
from lecturelens_agent.study.provider import ChatProvider
from lecturelens_agent.study.quality import review_messages, review_wire_messages

CLIENT = httpx.Client
SCOPE = dict(owner_id=42, course_id="C", revision=1, session_id="S", run_id="R")
TEXT = '原来的 "red" 对象仍然存在于容器中的某个地方，但它不再被变量 v 引用。'
NARROW = '原来的 "red" 对象仍存在于容器中，不再被变量 v 引用。'
SOURCE = '变量 v 重新绑定到新的 "blue" 对象。原来的 "red" 对象仍在容器中，v 不再引用旧对象。'


def test_unrelated_universal_words_do_not_license_exhaustive_scan_or_ledger_reuse():
    source = "全部展开递推式。直觉算法的复杂度是 θ(n)。"
    answer = "直接扫描需要逐个检查每个元素。"
    assert supported(answer, source=source) == []
    q, _ = delta(answer, facts=[], source=source)
    assert q["issues"] == ["unsupported_explanation"]
    assert "exhaustive_scan" in q["atomic_assessments"][0]["strengthening_guards"]
    assert supported(answer, source="线性扫描最坏情况下检查所有元素。")


@pytest.mark.parametrize(
    "answer",
    [
        '执行 v = "red" 时，变量 v 绑定到 "red" 对象。',
        "旧对象在变量重新绑定后，仍然存在于容器中。",
        "若令 m = 2^j，则 Θ(m) 变为 Θ(2^j)。",
        "等于处理子问题的时间。",
        "再加上一个常数时间。",
        "课程中。",
        "直接扫描算法。",
        "实际上就是另一种差别。",
        "”他进一步说明。",
        "老师接着强调。",
        "老师说：“所有对象都永久存在。”",
        "他还提到。",
        "课程指出。",
        "老师说：“对于一维情况，你真的很难做得更好。”",
        "即 Θ(log n)。",
        "重复此过程。",
        "并在输入规模约为一百万。",
        "这显示出两者之间巨大的性能差异。",
        "线性算法耗时约 9 秒。",
        "The algorithm takes 7 seconds.",
        "例如在一维峰值查找中。",
        "在每一层递归中。",
        "然。",
        '而是指向新创建的 "blue" 对象。',
        "另一个是分治法。",
        "所需的递归层数。",
        "恰好是 log₂m。",
        "并执行常数时间的工作。",
        "将规模 m 不断除以 2，直到变为 1。",
        "只是不再通过 v 访问。",
        "他进一步解释说。",
        "根据与上下邻居的比较结果。",
        "非具体数值。",
        "而非具体数值。",
        "需要对输入进行线性遍历。",
        "判断是否存在目标。",
        "与另一方法相比，在大规模输入下性能更优。",
        "强调了降低复杂度的重要性。",
        "并递归处理一半的输入。",
        "共进行 log₂m 次递归调用。",
        "最终在 log₂m 层递归后到达一个元素。",
        "随着递归不断减半。",
        "总工作量为 Θ(log m)。",
        "前者仅需 0.002 秒。",
        "后者需 9 秒。",
        "The former takes 0.002 seconds.",
        "The latter takes 9 seconds.",
        "老师指出，对于二维搜索问题。",
        "当持续递归下去。",
        "并说明在处理大规模输入时降低复杂度非常有意义。",
        "并将问题规模减半。",
        "共递归 log₂m 层。",
        "继续在一半的数组中搜索。",
        "分治算法通过每次将问题规模减半。",
        "随后他提到。",
        "取 m = 32。",
        "再取 m = 64。",
        "注意这里的 4、8。",
        "考虑两个输入规模：m=16 和 m=256。",
        "对 Θ(m) 来说。",
        "对于指数类而言。",
        "As for the logarithmic class.",
        "选择输入长度 m=64。",
        "Consider two hypothetical input lengths.",
        "递归持续进行，直到输入规模为一。",
        "The process repeats until a limit is reached.",
        "他接着说明缩减输入具有意义。",
        "She explains that the work is bounded.",
        "在 j 的尺度下。",
        "于局部坐标上。",
        "In the transformed scale.",
        "通过代入 m = 3^j。",
        "借助一个变量替换。",
        "Using an alternative parameter.",
        "Θ(m) 对应的数学尺度是 16。",
        "线性尺度为 4096。",
        "The logarithmic scale is 12.",
        "从 m 连续减半。",
        "From m, continue halving.",
        "对于m约为十万的输入。",
    ],
)
def test_context_dependent_fragments_never_become_unqualified_ledger_facts(answer):
    assert supported(answer, source=answer) == []


def test_reporting_prefix_and_negated_contrast_do_not_supply_reusable_facts():
    attributed = "他进一步解释说，复杂度是“指数级的差异”。"
    assert supported(attributed, source=attributed) == []
    contrast = "阶符号表示增长类而非具体数值。"
    facts = supported(contrast, source=contrast)
    assert [fact["text"] for fact in facts] == ["阶符号表示增长类"]
    assert all(valid_fact(fact, SCOPE) for fact in facts)


def test_recursive_condition_does_not_become_unconditional_array_mutation():
    answer = "当持续递归下去，数组最终会缩小到只有一个元素。"
    assert not supported(answer, source=answer)
    # A complete independently named source assertion remains reusable.
    bound = "递归子问题的输入包含一个元素。"
    assert supported(bound, source=bound)


def test_split_predicate_cannot_invent_an_algorithm_or_comparator_subject():
    answer = "递推式描述一半规模的工作，解得时间复杂度为 Θ(log m)，远优于线性复杂度。"
    facts = supported(answer, source=answer)
    assert all("解得" not in f["text"] and "远优于" not in f["text"] for f in facts)
    assert supported("分治算法的时间复杂度为 Θ(log m)。", source=answer)


def test_comparison_and_half_size_do_not_license_unsourced_control_condition():
    source = "比较当前元素与左右邻居，递归到一半规模，单元素时返回元素。"
    answer = "若未找到峰值，则递归处理一半输入。"
    q, _ = delta(answer, facts=[], source=source)
    assert "predicate_condition_specialization" in q["atomic_assessments"][0]["strengthening_guards"]
    assert not supported(answer, source=source)


def test_timing_or_incomplete_operation_source_does_not_prove_a_stopping_input():
    answer = "递归在单元素数组时停止。"
    source = "比较邻居，递归处理一半输入，运行用时九秒。"
    q, _ = delta(answer, facts=[], source=source)
    assert "single_element_base" in q["atomic_assessments"][0]["strengthening_guards"]
    assert not supported(answer, source=source)
    assert supported(answer, source="递归到一元素数组时结束。")


def test_rebinding_passage_does_not_license_an_uncited_immutability_cause():
    source = '变量 v 绑定到新的 "blue" 对象，旧的 "red" 对象仍然存在。'
    answer = '原来的 "red" 对象因字符串的不可变性未被修改。'
    q, _ = delta(answer, facts=[], source=source)
    assert "immutability" in q["atomic_assessments"][0]["strengthening_guards"]
    assert not supported(answer, source=source)
    assert supported(answer, source="字符串对象创建后不能被修改。")


def test_comparison_fragment_cannot_borrow_identity_from_rejected_qualifier():
    answer = '这个旧对象成为一个独立存在的对象，与新的 "blue" 对象完全不同。'
    first = atomic_claims(answer)[0]["source_text"]
    assert not supported(answer, source=answer, rejected=[first])
    bound = '原来的 "red" 对象仍存在于容器中，与新的 "blue" 对象完全不同。'
    facts = supported(bound, source=bound)
    comparison = next(f for f in facts if "完全不同" in f["text"])
    assert comparison["text"].startswith('原来的 "red" 对象与')
    assert len(comparison["source_units"]) == 2
    assert valid_fact(comparison, SCOPE)


@pytest.mark.parametrize(
    "answer",
    [
        "递归返回后可能需要合并子问题的解。",
        "只在包含峰值的一半中继续搜索。",
    ],
)
def test_generic_algorithm_operations_are_not_inferred_from_recurrence(answer):
    source = "检查元素与相邻值，每层有常量工作，并递归到一半规模，最终返回单元素。"
    assert supported(answer, source=source) == []
    assert supported(answer, source=answer)


def test_local_predicate_check_does_not_prove_global_existence():
    source = "检查当前元素是否为峰值，比较其左侧和右侧邻居。"
    assert supported("判断是否存在峰值。", source=source) == []
    q, _ = delta("判断是否存在峰值。", facts=[], source=source)
    assert "existence_specialization" in q["atomic_assessments"][0]["strengthening_guards"]
    assert supported("检查当前元素是否为峰值。", source=source)


@pytest.mark.parametrize(
    "answer",
    [
        "Θ(m) 是 2ᵏ。",
        "Θ(log m) 是 k。",
        "Θ(m) 的规模是 512。",
        "Θ(log m) 对应的规模是 9。",
        "Theta(m) equals 512.",
    ],
)
def test_growth_classes_cannot_become_scalar_ledger_facts_even_with_claimed_source(answer):
    assert supported(answer, source=answer) == []
    q, _ = delta(answer, facts=[], source=answer)
    assert "asymptotic_value" in q["atomic_assessments"][0]["strengthening_guards"]


def test_growth_class_guard_preserves_function_scales_and_comparison_work():
    for answer in ["线性尺度 m 是 512。", "Θ(m) 是 Θ(2^j)。", "Θ(1) 对应的是 2 次比较。"]:
        assert supported(answer, source=answer)


def test_comparison_targets_do_not_change_to_the_neighbors_predicate():
    source = "比较当前元素与左右邻居，检查当前元素是否为峰值。"
    answer = "检查当前元素左右邻居是否构成峰值。"
    assert supported(answer, source=source) == []
    q, _ = delta(answer, facts=[], source=source)
    assert "subject_specialization" in q["atomic_assessments"][0]["strengthening_guards"]
    assert supported("检查左右邻居是否为峰值。", source="检查左右邻居是否为峰值。")


def test_mathematical_scales_do_not_license_numeric_operation_counts():
    source = "输入规模为 32，减半层数为 5。每层可能有两个比较。"
    assert not supported("算法大约需要 32 次操作。", source=source)
    assert not supported("算法仅需 5 次比较。", source=source)
    assert supported("例如进行 2 次比较。", source=source)
    assert supported("For example, two comparisons.", source=source)


def test_halving_levels_do_not_prove_exact_symbolic_operation_counts():
    source = "每层常量工作，规模减半直到一个元素，展开 log₂n 层。"
    assert not supported("总共进行 log₂n 次操作。", source=source)
    assert not supported("There are n operations.", source="Linear work is Θ(n).")
    assert supported("总共进行 log₂n 次操作。", source="总共进行 log₂n 次操作。")


def message(answer, facts=None, scope=None, source=SOURCE):
    evidence = [dict(evidence_id="canonical", text=source, start_ms=10, end_ms=20)]
    candidate = dict(kind="explanation", title="State", explanation=answer, evidence_ids=["canonical"])
    m = review_messages(
        "Explain the objects.",
        candidate,
        evidence,
        ledger_facts=facts,
        ledger_scope=scope or SCOPE,
        answer_review_mode="atomic_answer_support_v1",
    )
    return json.loads(m[-1]["content"]), m, candidate, evidence


def supported(answer=TEXT, source=SOURCE, rejected=()):
    b, _, c, e = message(answer, source=source)
    q = AtomicAnswerVerdict.model_validate(judgment(b, rejected), context=b).review().model_dump()
    # Runtime resolves wire IDs before committing the quality observation.
    from lecturelens_agent.study.context import aliases_in

    q = aliases_in(q, {"e1": "canonical"})
    return facts_from_review(SCOPE, c, q, e)


def delta(answer=NARROW, facts=None, scope=None, source=SOURCE):
    b, m, _, _ = message(answer, facts if facts is not None else supported(), scope, source)
    wire = json.loads(review_wire_messages(m)[-1]["content"])
    v = judgment(wire)
    contract = (
        DeltaAtomicAnswerVerdict if b.get("review_mode") == "atomic_delta_support_v1" else AtomicAnswerVerdict
    )
    q = contract.model_validate(v, context=b).review().model_dump()
    q["atomic_delta"] = q.get("atomic_delta") or {"ledger_reused_ids": []}
    return q, wire


def test_resolved_subject_connective_punctuation_and_location_equivalence_reuse():
    facts = supported()
    assert len(facts) == 2
    q, wire = delta()
    assert q["issues"] == [] and len(q["atomic_delta"]["ledger_reused_ids"]) == 2
    assert wire["atomic_claims"] == []
    assert "ledger_facts" not in wire
    assert any("变量 v不再引用" in f["normalized_claim"] for f in facts)


def test_current_guards_filter_historical_positive_proofs_before_generation_and_reuse(monkeypatch):
    from lecturelens_agent.study import ledger
    from lecturelens_agent.study.context import aliases_in

    source = "Inspect an element and its neighbours."
    answer = "Inspect the middle element."
    body, _, candidate, evidence = message(answer, source=source)
    quality = AtomicAnswerVerdict.model_validate(judgment(body), context=body).review().model_dump()
    for check in quality["atomic_assessments"]:
        check.update(supported=True, model_supported=True, strengthening_guards=[])
    quality = aliases_in(quality, {"e1": "canonical"})
    assert facts_from_review(SCOPE, candidate, quality, evidence) == []
    with monkeypatch.context() as old_policy:
        old_policy.setattr(ledger, "strengthening_guards", lambda *args: [])
        historical = facts_from_review(SCOPE, candidate, quality, evidence)
    assert historical and valid_fact(historical[0], SCOPE)
    assert generation_view(historical, evidence, {"e1": "canonical"}) == []
    current, wire = delta(answer, historical, source=source)
    assert not current["atomic_delta"]["ledger_reused_ids"] and len(wire["atomic_claims"]) == 1
    assert current["issues"] == ["unsupported_explanation"]


def test_shifted_exact_spans_rebind_to_current_answer():
    answer = "An introduction. " + NARROW
    q, wire = delta(answer)
    assert len(q["atomic_delta"]["ledger_reused_ids"]) == 2
    assert len(wire["atomic_claims"]) == 1
    for c in q["atomic_assessments"]:
        assert answer[c["start"] : c["end"]] == c["source_text"]


@pytest.mark.parametrize(
    "old,new",
    [
        ("s does not reference X.", "No variable references X."),
        ("The gate may open.", "The gate will open."),
        ("The gate is currently open.", "The gate is open until the timer expires."),
        ("Some items are ready.", "All items are ready."),
        ("The gate opens if A holds.", "The gate opens if B holds."),
        ("The gate opens because A holds.", "The gate opens because B holds."),
        ('原来的 "red" 对象不再被变量 v 引用。', '新的 "red" 对象不再被变量 v 引用。'),
    ],
)
def test_semantic_qualifiers_never_canonicalize_away(old, new):
    facts = supported(old, source=old)
    q, wire = delta(new, facts=facts, source=old)
    assert wire["atomic_claims"]
    assert not q["atomic_delta"]["ledger_reused_ids"]


@pytest.mark.parametrize("field", ["owner_id", "course_id", "revision", "session_id"])
def test_scope_isolation(field):
    scope = {**SCOPE, field: 99 if field in {"owner_id", "revision"} else "OTHER"}
    q, wire = delta(scope=scope)
    assert not q["atomic_delta"]["ledger_reused_ids"] and len(wire["atomic_claims"]) == 2


def test_changed_evidence_and_verifier_version_force_recheck():
    facts = supported()
    q, wire = delta(facts=facts, source=SOURCE + " Changed.")
    assert not q["atomic_delta"]["ledger_reused_ids"] and wire["atomic_claims"]
    for f in facts:
        f["verifier_version"] = "older"
    q, wire = delta(facts=facts)
    assert not q["atomic_delta"]["ledger_reused_ids"] and wire["atomic_claims"]


def test_unsupported_or_ambiguous_subject_never_enters_ledger():
    facts = supported(rejected=["但它不再被变量 v 引用。"])
    assert len(facts) == 1 and "引用" not in facts[0]["normalized_claim"]
    ambiguous = '"red" 对象和 "blue" 对象位于容器中，但它不再被变量 v 引用。'
    facts = supported(ambiguous)
    assert all("引用" not in f["normalized_claim"] for f in facts)


def test_empty_evidence_rejection_cannot_enter_ledger_or_supply_a_context_binding():
    answer = '原来的 "red" 对象仍存在于容器中（直到容器关闭），但它不再被变量 v 引用。'
    b, _, candidate, evidence = message(answer)
    verdict = judgment(b)
    for claim, check in zip(b["atomic_claims"], verdict["claim_checks"], strict=True):
        if "直到" in claim["source_text"]:
            check.update(supported=False, evidence_ids=[])
            if check.get("relation"):
                check["relation"]["grounds"] = []
    quality = AtomicAnswerVerdict.model_validate(verdict, context=b).review().model_dump()
    from lecturelens_agent.study.context import aliases_in

    facts = facts_from_review(SCOPE, candidate, aliases_in(quality, {"e1": "canonical"}), evidence)
    assert facts
    assert all(valid_fact(f, SCOPE) for f in facts)
    assert all("直到" not in f["text"] for f in facts)
    assert all(u["supported"] and u["evidence_ids"] for f in facts for u in f["source_units"])


def test_contextual_comparison_and_dangling_condition_do_not_become_independent_facts():
    from lecturelens_agent.study.atomic import atomic_claims

    for text in ["这种方法性能差异巨大。", "时性能差异巨大。", "条件下结果有效。"]:
        assert canonical_claim(atomic_claims(text)[0]) is None


def test_checkpoint_json_replay_keeps_identical_verdict_and_fact_identity():
    b, _, _, _ = message(NARROW, supported())
    v = judgment(
        json.loads(review_wire_messages([{"role": "user", "content": json.dumps(b)}])[-1]["content"])
    )
    first = DeltaAtomicAnswerVerdict.model_validate(v, context=b).review().model_dump()
    recovered = json.loads(json.dumps(b))
    assert first == DeltaAtomicAnswerVerdict.model_validate(v, context=recovered).review().model_dump()


def test_contingent_predicate_is_not_generalized_into_ledger():
    a = "If condition A holds, the gate is open."
    b = "If condition B holds, the gate is open."
    from lecturelens_agent.study.atomic import atomic_claims

    assert canonical_claim(atomic_claims(a)[-1]) is None
    assert canonical_claim(atomic_claims(b)[-1]) is None


@pytest.mark.parametrize("crash", [False, True])
@pytest.mark.parametrize(
    "initial_answer",
    [
        TEXT,
        '执行 v = "blue" 后，Python 解除 v 与原 "red" 对象的绑定，并将 v 重新绑定到新的 "blue" 对象。' + TEXT,
        '执行 v = "blue" 后，创建一个全新的字符串对象 "blue" 并将 v 重新绑定到它。' + TEXT,
        '执行 v = "blue" 后，创建一个全新的字符串对象 "blue"，并将 v 重新绑定到这个新对象。' + TEXT,
    ],
)
def test_session_ledger_followup_reads_authority_without_repeat_search_and_replays(
    setup,  # noqa: F811 -- imported PostgreSQL fixture
    monkeypatch,
    crash,
    initial_answer,
):
    store, authority, runtime, scope = setup
    original_read, original_decide = authority.read, runtime.provider.decide
    reviews, generations = [], []

    def course_read(s, action="CHECK", **kw):
        value = original_read(s, action, **kw)
        for e in value.get("evidence", []):
            e["text"] = SOURCE
        return value

    def decide(messages, timeout):
        b = json.loads(messages[-1]["content"])
        if not b["evidence"]:
            return original_decide(messages, timeout)
        generations.append(b)
        return {
            "name": "create_explanation",
            "arguments": dict(
                title="Objects",
                explanation=NARROW if b.get("supported_facts") else initial_answer,
                evidence_ids=["e1"],
                **({"resolved_goal": "Explain the original object."} if b.get("supported_facts") else {}),
            ),
        }

    def handle(request):
        b = json.loads(json.loads(request.content)["messages"][-1]["content"])
        reviews.append(b)
        return response(judgment(b))

    authority.read = course_read
    runtime.provider.decide = decide
    monkeypatch.setattr(httpx, "Client", lambda **kw: CLIENT(transport=httpx.MockTransport(handle), **kw))
    runtime.provider.review = ChatProvider("https://fixture.invalid/v1", "qwen3-max", "fixture").review

    def start(key, goal):
        s = store.command(StudyCommand(**scope, operation="START", request_key=key, goal=goal), "mock")
        return next(r for r in store.candidates() if r["run_id"] == s["run"]["run_id"])

    runtime.execute(start("first", "Explain the objects."))
    assert read(setup)["run"]["status"] == "succeeded"
    first_searches = authority.reads.count("SEARCH")
    follow = start("follow", "What about that original object?")
    snapshot = store.supported_facts(follow)
    assert snapshot
    if initial_answer != TEXT:
        projected = [f for f in snapshot if f["text"].startswith('执行 v = "blue" 后，')]
        assert len(projected) == (1 if "创建" in initial_answer else 2)
        assert all(len(f["source_units"]) == (3 if "这个新对象" in initial_answer else 2) for f in projected)
    original_save = store.save_tool

    def save_crash(*args, **kwargs):
        value = original_save(*args, **kwargs)
        if value.get("supported_facts"):
            store.save_tool = original_save
            raise SystemExit("after committed ledger")
        return value

    if crash:
        store.save_tool = save_crash
        with pytest.raises(SystemExit):
            runtime.execute(follow)
        from langgraph.checkpoint.postgres import PostgresSaver

        contaminated = json.loads(json.dumps(snapshot[0]))
        contaminated["verifier_version"] = "atomic_ledger_v1"
        contaminated["text"] += " until discarded"
        config = {"configurable": {"thread_id": follow["session_id"]}}
        with PostgresSaver.from_conn_string(store.dsn) as saver:
            graph = runtime.graph(follow, "unused", saver)
            old = graph.update_state(config, {"supported_facts": [contaminated]}, as_node="decide")
    runtime.execute(follow)
    final = read(setup)
    assert final["run"]["status"] == "succeeded" and final["artifact"]["explanation"] == NARROW
    assert final["run"]["model_calls"] == 2 and final["run"]["tool_calls"] == 1
    assert authority.reads.count("SEARCH") == first_searches
    assert reviews[-1]["atomic_claims"] == [] and generations[-1]["supported_facts"]
    assert store.supported_facts({**follow, "owner_id": 999}) == []
    assert "supported_facts" not in json.dumps(read(setup, "EVENTS"))
    if crash:
        with PostgresSaver.from_conn_string(store.dsn) as saver:
            graph = runtime.graph(follow, "unused", saver)
            recovered = graph.get_state(config).values["supported_facts"]
            assert recovered and all(valid_fact(f, follow) for f in recovered)
            assert all("discarded" not in f["text"] for f in recovered)
            assert graph.get_state(old).values["supported_facts"] == [contaminated]


def test_named_relation_active_passive_and_resolved_pronoun_are_equivalent():
    facts = supported()
    q, wire = delta('原来的 "red" 对象仍存在于容器中，变量 v 不再指向它。', facts=facts)
    assert len(q["atomic_delta"]["ledger_reused_ids"]) == 2 and wire["atomic_claims"] == []


def test_authority_span_change_and_own_citation_removal_prevent_reuse():
    b, m, _, _ = message(NARROW, supported())
    b["ledger_evidence_bindings"]["canonical"]["start_ms"] += 1
    m[-1]["content"] = json.dumps(b)
    assert json.loads(review_wire_messages(m)[-1]["content"])["atomic_claims"]
    b, m, _, _ = message(NARROW, supported())
    b["candidate"]["evidence_ids"] = ["other"]
    m[-1]["content"] = json.dumps(b)
    assert json.loads(review_wire_messages(m)[-1]["content"])["atomic_claims"]


def test_comparison_requires_two_bound_operands_and_complete_supported_source():
    answer = '变量 v 绑定到新的 "blue" 对象。原来的 "red" 对象在容器中，但它是一个完全不同的对象。'
    facts = supported(answer)
    assert any("与" in f["normalized_claim"] and "不同" in f["normalized_claim"] for f in facts)
    facts = supported(answer, rejected=['变量 v 绑定到新的 "blue" 对象。'])
    assert not any("不同" in f["normalized_claim"] for f in facts)


def test_object_type_qualifier_is_not_erased():
    old = '原来的 "red" 对象在容器中。'
    new = '原来的 "red" 字符串对象在容器中。'
    q, wire = delta(new, facts=supported(old, source=old), source=old)
    assert not q["atomic_delta"]["ledger_reused_ids"] and wire["atomic_claims"]


def test_dangling_cause_and_condition_are_not_standalone_ledger_facts():
    for answer in [
        "The gate is open because the sensor is active.",
        "The gate is open if the sensor is active.",
    ]:
        facts = supported(answer, source=answer)
        assert not any(f["claim_type"] == "qualification" for f in facts)


def test_rejected_gc_parenthesis_does_not_reenter_supported_fact():
    answer = '原来的 "red" 对象仍存在于内存中（直到被垃圾回收），但它不再被变量 v 引用。'
    facts = supported(answer, source=SOURCE, rejected=["（直到被垃圾回收），"])
    assert facts
    assert any("仍存在于内存中" in f["text"] for f in facts)
    assert all("垃圾回收" not in f["text"] + f["normalized_claim"] for f in facts)


@pytest.mark.parametrize("suffix", ["（直到闸门关闭）", "直到闸门关闭", "因为闸门关闭"])
def test_rejected_time_or_cause_is_never_copied_from_context(suffix):
    answer = f'原来的 "red" 对象仍存在于内存中{suffix}。变量 v 重新绑定到新的 "blue" 对象。'
    from lecturelens_agent.study.atomic import atomic_claims

    rejected = [c["source_text"] for c in atomic_claims(answer) if "闸门" in c["source_text"]]
    facts = supported(answer, rejected=rejected)
    assert facts
    assert all("闸门" not in f["text"] + f["normalized_claim"] for f in facts)
    assert all(all(u["supported"] is True for u in f["source_units"]) for f in facts)


def test_supported_neighbors_remain_independent_and_context_copies_only_subject():
    facts = supported()
    relation = next(f for f in facts if "引用" in f["text"])
    assert len(relation["source_units"]) == 2
    assert "容器" not in relation["text"]
    assert len(facts) == 2
    assert all(valid_fact(f, SCOPE) for f in facts)


@pytest.mark.parametrize("predicate", ["不再通过 v 访问", "只是无法再通过变量 v 访问到"])
def test_elliptical_access_relation_requires_a_supported_explicit_subject(predicate):
    answer = f'原来的 "red" 对象仍存在于容器中，但{predicate}。'
    facts = supported(answer, source=answer)
    relation = next(f for f in facts if predicate in f["text"])
    assert relation["text"].startswith('原来的 "red" 对象')
    assert len(relation["source_units"]) == 2
    assert valid_fact(relation, SCOPE)
    assert not supported(f"但{predicate}。", source=answer)
    rejected = [atomic_claims(answer)[0]["source_text"]]
    assert not any(predicate in f["text"] for f in supported(answer, source=answer, rejected=rejected))


def test_temporal_intro_is_not_a_standalone_fact():
    answer = '执行 v = "red" 时，变量 v 绑定到 "red" 对象。'
    facts = supported(answer, source=answer)
    # Dropping the time prefix must not promote its bound predicate into an
    # unconditional state. Exact verdicts remain available for revision reuse.
    assert not facts
    assert all(not f["text"].endswith("时") for f in facts)


@pytest.mark.parametrize("failure", ["unsupported", "unknown", "illegal_citation"])
def test_context_identity_requires_supported_legally_bound_unit(failure):
    b, _, candidate, evidence = message(TEXT)
    from lecturelens_agent.study.context import aliases_in

    q = aliases_in(
        AtomicAnswerVerdict.model_validate(judgment(b), context=b).review().model_dump(), {"e1": "canonical"}
    )
    if failure == "unknown":
        q["atomic_assessments"].pop(0)
    elif failure == "unsupported":
        q["atomic_assessments"][0]["supported"] = False
    else:
        q["atomic_assessments"][0]["evidence_ids"] = ["foreign"]
    facts = facts_from_review(SCOPE, candidate, q, evidence)
    assert not any("引用" in f["text"] for f in facts)


def test_purity_proof_rejects_tampering_and_old_version_without_historical_migration():
    facts = supported()
    bad = json.loads(json.dumps(facts[0]))
    bad["text"] += " until discarded"
    assert valid_fact(bad, SCOPE) is None
    old = {**facts[0], "verifier_version": "atomic_ledger_v2"}
    assert valid_fact(old, SCOPE) is None
    _, _, _, evidence = message(TEXT)
    assert generation_view([bad, old], evidence, {"e1": "canonical"}) == []
    assert old["verifier_version"] == "atomic_ledger_v2"
    bad = json.loads(json.dumps(facts[-1]))
    bad["source_units"][0]["supported"] = False
    assert valid_fact(bad, SCOPE) is None


def test_rejected_span_stays_audit_only_and_json_replay_fact_content_stays_pure():
    answer = '原来的 "red" 对象仍存在于内存中（直到被垃圾回收），但它不再被变量 v 引用。'
    facts = supported(answer, rejected=["（直到被垃圾回收），"])
    recovered = json.loads(json.dumps(facts))
    for fact in recovered:
        assert valid_fact(fact, SCOPE)
        assert "垃圾回收" not in fact["text"] + fact["normalized_claim"]
        assert all("垃圾回收" not in u["source_text"] for u in fact["source_units"])
        for unit in fact["source_units"]:
            assert answer[unit["start"] : unit["end"]] == unit["source_text"]
            assert unit["supported"] and set(unit["evidence_ids"]) <= set(fact["evidence_ids"])
