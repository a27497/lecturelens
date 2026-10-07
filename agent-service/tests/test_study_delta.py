"""Run-local delta authority/replay and conservative strengthening regressions."""

import copy
import json

import httpx
import pytest
from pydantic import ValidationError
from test_study import read, setup  # noqa: F401
from test_study_atomic import judgment, response

from lecturelens_agent.study.atomic_delta import claim_fingerprint, delta_plan
from lecturelens_agent.study.atomic_review import AtomicAnswerVerdict, DeltaAtomicAnswerVerdict
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.provider import ChatProvider
from lecturelens_agent.study.quality import review_messages, review_wire_messages

CLIENT = httpx.Client
SOURCE = "A is ready. B runs."
INITIAL = "A is ready. Until the timer fires. B runs."
NARROWED = "A is ready. B runs."


def messages(answer, prior=None, source=SOURCE, citations=None):
    return review_messages(
        "Explain the state.",
        {
            "kind": "explanation",
            "title": "State",
            "explanation": answer,
            "evidence_ids": citations or ["canonical"],
        },
        [{"evidence_id": "canonical", "text": source}, {"evidence_id": "other", "text": source}],
        prior_atomic_review=prior,
        answer_review_mode="atomic_answer_support_v1",
    )


def input_body(answer, prior=None, **kwargs):
    return json.loads(messages(answer, prior, **kwargs)[-1]["content"])


def initial_review(answer=INITIAL, source=SOURCE, rejected=()):
    b = input_body(answer, source=source)
    quality = AtomicAnswerVerdict.model_validate(judgment(b, rejected), context=b).review().model_dump()
    return {"candidate": b["candidate"], "quality": quality}


def delta_verdict(body, rejected=()):
    verdict = judgment(body, rejected)
    verdict["claim_checks"] = [c for c in verdict["claim_checks"] if c["id"] in body["review_claim_ids"]]
    return verdict


def test_deleted_unsupported_qualifier_reuses_every_unchanged_supported_claim():
    prior = initial_review()
    b = input_body(NARROWED, prior)
    reused, plan = delta_plan(b)
    assert plan.rechecked_ids == [] and len(reused) == 2
    final = DeltaAtomicAnswerVerdict.model_validate(delta_verdict(b), context=b).review()
    assert final.issues == [] and len(final.atomic_assessments) == 2
    assert all(c.supported for c in final.atomic_assessments)
    old_b = prior["quality"]["atomic_assessments"][-1]
    rebound = final.atomic_assessments[-1]
    assert rebound.start != old_b["start"]
    assert rebound.fingerprint == old_b["fingerprint"]
    assert NARROWED[rebound.start : rebound.end] == rebound.source_text
    assert len(plan.deleted_fingerprints) == 1


def test_empty_rejection_survives_checkpoint_and_only_changed_claims_are_rechecked():
    b = input_body(INITIAL)
    verdict = judgment(b)
    verdict["claim_checks"][1].update(supported=False, evidence_ids=[])
    if verdict["claim_checks"][1].get("relation"):
        verdict["claim_checks"][1]["relation"]["grounds"] = []
    prior = {
        "candidate": b["candidate"],
        "quality": AtomicAnswerVerdict.model_validate(verdict, context=b).review().model_dump(),
    }
    prior = json.loads(json.dumps(prior))
    b = input_body(NARROWED + " C shines.", prior)
    reused, plan = delta_plan(b)
    assert list(reused) == ["a1"]
    assert plan.rechecked_ids == ["a2", "a3"]
    final = DeltaAtomicAnswerVerdict.model_validate(delta_verdict(b), context=b).review()
    assert len(final.atomic_assessments) == 3
    assert all(c.supported and c.evidence_ids for c in final.atomic_assessments)


def test_stated_termination_endpoint_is_still_subject_to_atomic_support():
    answer = "The process continues until the base case is reached."
    b = input_body(answer, source="Repeated steps eventually reach the base case.")
    supported = AtomicAnswerVerdict.model_validate(judgment(b), context=b).review()
    assert supported.issues == []
    rejected = judgment(b)
    rejected["claim_checks"][-1].update(supported=False, evidence_ids=[])
    if rejected["claim_checks"][-1].get("relation"):
        rejected["claim_checks"][-1]["relation"]["grounds"] = []
    assert AtomicAnswerVerdict.model_validate(rejected, context=b).review().issues == [
        "unsupported_explanation"
    ]
    b = input_body("The object remains until it is collected.", source="The object remains in memory.")
    review = AtomicAnswerVerdict.model_validate(judgment(b), context=b).review()
    assert "duration" in review.atomic_assessments[-1].strengthening_guards


@pytest.mark.parametrize(
    "fault", ["new", "text", "citation", "source", "type", "normalization", "goal", "basis"]
)
def test_changed_binding_never_reuses_a_verdict(fault):
    prior = initial_review()
    answer, options = NARROWED, {}
    if fault == "new":
        answer += " C shines."
    elif fault == "text":
        answer = "A is ready. B flies."
    elif fault == "citation":
        options["citations"] = ["canonical", "other"]
    elif fault == "source":
        options["source"] = "A is ready. B flies."
    elif fault == "type":
        prior["quality"]["atomic_assessments"][0]["claim_type"] = "qualification"
    elif fault == "normalization":
        prior["quality"]["atomic_assessments"][0]["normalized_claim"] = "Another fact."
    elif fault == "basis":
        prior["quality"]["atomic_basis"]["version"] = "stale"
    b = input_body(answer, prior, **options)
    if fault == "goal":
        b["goal"] = "Explain a different state."
    reused, plan = delta_plan(b)
    if fault == "citation":
        assert len(reused) == 2 and not plan.rechecked_ids
    elif fault in {"new", "text"}:
        target = next(c for c in b["atomic_claims"] if c["source_text"].strip() in {"C shines.", "B flies."})
        assert target["id"] in plan.rechecked_ids
    else:
        assert not reused and len(plan.rechecked_ids) == len(b["atomic_claims"])


def test_added_own_citation_preserves_exact_proofs_and_rechecks_only_new_claim():
    prior = initial_review()
    b = input_body(NARROWED + " C shines.", prior, citations=["canonical", "other"])
    reused, plan = delta_plan(b)
    assert list(reused) == ["a1"] and plan.rechecked_ids == ["a2", "a3"]
    final = DeltaAtomicAnswerVerdict.model_validate(delta_verdict(b), context=b).review()
    assert final.issues == []
    assert all(
        c.fingerprint == claim_fingerprint(c.model_dump(), b["candidate"]["evidence_ids"])
        for c in final.atomic_assessments
    )
    wire = json.loads(
        review_wire_messages(messages(NARROWED + " C shines.", prior, citations=["canonical", "other"]))[-1][
            "content"
        ]
    )
    assert [c["id"] for c in wire["atomic_claims"]] == ["a2", "a3"]


def test_removed_or_changed_actual_proof_source_never_reuses_unchanged_claim():
    prior = initial_review()
    for options in [{"citations": ["other"]}, {"source": "A is missing. B stops."}]:
        reused, plan = delta_plan(input_body(NARROWED, prior, **options))
        assert not reused and len(plan.rechecked_ids) == 2


def test_wire_alias_change_does_not_change_exact_claim_identity():
    from lecturelens_agent.study.context import aliases_in

    b = input_body(NARROWED, initial_review())
    remapped = aliases_in(b, {"e1": "e7", "e2": "e8"})
    reused, plan = delta_plan(remapped)
    assert len(reused) == 2 and not plan.rechecked_ids
    assert all(c.evidence_ids == ["e7"] for c in reused.values())


def test_current_strengthening_policy_rechecks_a_historical_positive_proof(monkeypatch):
    from lecturelens_agent.study import strengthening

    b = input_body(NARROWED, initial_review())
    monkeypatch.setattr(strengthening, "strengthening_guards", lambda *args: ["new_scope_guard"])
    reused, plan = delta_plan(b)
    assert not reused and len(plan.rechecked_ids) == 2


def test_legacy_checkpoint_fingerprints_remain_verifiable_without_rewriting_history():
    from lecturelens_agent.study.atomic_delta import legacy_claim_fingerprint

    prior = initial_review()
    for c in prior["quality"]["atomic_assessments"]:
        c["fingerprint"] = legacy_claim_fingerprint(c, prior["candidate"]["evidence_ids"])
    snapshot = copy.deepcopy(prior)
    reused, plan = delta_plan(input_body(NARROWED, prior, citations=["canonical", "other"]))
    assert len(reused) == 2 and not plan.rechecked_ids
    assert prior == snapshot


def test_previously_unsupported_claim_is_rechecked_even_if_text_unchanged():
    prior = initial_review()
    b = input_body(INITIAL, prior)
    _, plan = delta_plan(b)
    target = next(c for c in b["atomic_claims"] if "Until" in c["source_text"])
    assert target["id"] in plan.rechecked_ids


def test_ambiguous_duplicates_are_rechecked_conservatively():
    prior = initial_review("A is ready. A is ready. A is ready.")
    b = input_body("A is ready. A is ready.", prior)
    reused, plan = delta_plan(b)
    assert not reused and len(plan.rechecked_ids) == 2


def test_unchanged_pronoun_with_changed_antecedent_is_not_reused():
    prior = initial_review("X exists, and it is red.", "X exists and is red. Y exists.")
    b = input_body("Y exists, and it is red.", prior, source="X exists and is red. Y exists.")
    reused, plan = delta_plan(b)
    target = next(c for c in b["atomic_claims"] if "it is red" in c["source_text"])
    assert target["id"] not in reused and target["id"] in plan.rechecked_ids


def test_delta_validator_rejects_omitted_new_targets_and_unoffered_reused_checks():
    prior = initial_review()
    b = input_body(NARROWED + " C shines.", prior)
    verdict = delta_verdict(b)
    # A changed containing context, including its boundary, requires recheck.
    assert len(verdict["claim_checks"]) == 2
    bad = copy.deepcopy(verdict)
    bad["claim_checks"] = []
    with pytest.raises(ValidationError, match="every exact claim"):
        DeltaAtomicAnswerVerdict.model_validate(bad, context=b)
    bad = copy.deepcopy(verdict)
    bad["claim_checks"].append({"id": "a1", "supported": True, "evidence_ids": ["e1"]})
    with pytest.raises(ValidationError, match="every exact claim"):
        DeltaAtomicAnswerVerdict.model_validate(bad, context=b)
    b["review_claim_ids"] = []
    with pytest.raises(ValidationError, match="target plan"):
        DeltaAtomicAnswerVerdict.model_validate(verdict, context=b)


def test_complete_goal_is_still_reviewed_when_no_claim_needs_review():
    prior = initial_review()
    b = input_body(NARROWED, prior)
    verdict = delta_verdict(b)
    verdict["goal_checks"][0]["matches"] = False
    assert DeltaAtomicAnswerVerdict.model_validate(verdict, context=b).review().issues == ["goal_mismatch"]


def test_checkpoint_json_replay_produces_same_plan_fingerprints_and_verdict():
    prior = initial_review()
    b = input_body(NARROWED, prior)
    before = DeltaAtomicAnswerVerdict.model_validate(delta_verdict(b), context=b).review().model_dump()
    recovered = json.loads(json.dumps(b))
    after = (
        DeltaAtomicAnswerVerdict.model_validate(delta_verdict(recovered), context=recovered)
        .review()
        .model_dump()
    )
    assert before == after
    for claim in after["atomic_assessments"]:
        assert claim["fingerprint"] == claim_fingerprint(claim, b["candidate"]["evidence_ids"])


def test_delta_wire_keeps_referent_answer_but_not_duplicate_evidence_or_cached_verdict():
    prior = initial_review()
    m = messages(NARROWED + " C shines.", prior)
    b = json.loads(m[-1]["content"])
    b["semantic_context"] = {
        "raw_question": "What about it?",
        "resolved_goal": "Explain X.",
        "previous_turns": [
            {
                "goal": "Explain X.",
                "title": "State",
                "explanation": "X is ready.",
                "evidence_references": [{"text": "large duplicate"}],
            }
        ],
    }
    m[-1]["content"] = json.dumps(b)
    wire = json.loads(review_wire_messages(m)[-1]["content"])
    assert "prior_atomic_review" not in wire
    assert [c["source_text"].strip() for c in wire["atomic_claims"]] == ["B runs.", "C shines."]
    assert wire["candidate"]["explanation"] == NARROWED + " C shines."
    assert all("context_text" not in c and "normalized_claim" not in c for c in wire["atomic_claims"])
    assert all("context_text" in c for c in b["atomic_claims"])
    assert wire["semantic_context"]["previous_turns"][0]["explanation"] == "X is ready."
    assert "large duplicate" not in json.dumps(wire)


STRENGTHENINGS = [
    ("single_subject", "No variable references X.", "s does not reference X."),
    ("single_process", "No process accesses channel K.", "Process P does not access channel K."),
    ("some_all", "All items are ready.", "Some items are ready."),
    ("may_will", "The gate will open.", "The gate may open."),
    ("current_until", "The gate is open until the timer expires.", "The gate is currently open."),
    ("isolation", "The object is completely isolated.", "s no longer refers to the object."),
    ("cn_no_variables", "没有任何变量引用对象 X。", "变量 s 不再引用对象 X。"),
    ("cn_isolation", "对象 X 已经完全孤立。", "变量 s 不再引用对象 X。"),
    ("cn_some_all", "所有样本都符合条件。", "部分样本符合条件。"),
    ("cn_future", "进程最终会退出。", "进程可能退出。"),
    (
        "position",
        "Inspect the middle element and its neighbours.",
        "Inspect an element and its left and right neighbours.",
    ),
    ("branch", "Continue recursively in the left half.", "Recur on a problem of half the size."),
    (
        "cn_branch",
        "根据比较结果确定搜索方向，在左半边继续递归。",
        "查看元素的左右邻居，再处理规模减半的子问题。",
    ),
    (
        "cn_recursive_direction",
        "比较左右邻居来决定递归方向。",
        "查看元素的左右邻居，再处理规模减半的子问题。",
    ),
    (
        "recursive_direction",
        "Neighbour comparisons determine the recursive branch.",
        "Compare neighbours and halve the problem size.",
    ),
    ("bare_merge", "无需额外合并。", "递归处理一半规模的输入，单元素数组返回峰值。"),
    (
        "exponential_speedup",
        "This gives an exponential speedup.",
        "Linear n versus logarithmic n has an exponential difference under a change of parameter.",
    ),
    (
        "parameterized_all_elements",
        "线性算法需处理全部 n 个元素。",
        "直觉算法复杂度为 θ(n)，分治算法复杂度为 θ(log n)。",
    ),
    ("english_parameterized_all", "The linear algorithm processes all m elements.", "Linear work is Θ(m)."),
    ("linear_traversal", "该方法需线性遍历输入。", "该方法的时间复杂度为 Θ(m)。"),
    (
        "english_linear_traversal",
        "The method linearly traverses the input.",
        "The method has complexity Θ(m).",
    ),
    ("possible_gc", '原来的 "red" 对象可能被垃圾回收。', '变量 v 绑定到新的 "blue" 对象，旧对象仍在内存中。'),
    (
        "possible_english_gc",
        "The old object may be garbage collected.",
        "The old object remains in memory; v refers to the new object.",
    ),
    ("implicit_predicate_branch", "若不是，则继续递归。", "检查某个元素是否为峰值，递归处理一半规模。"),
    ("one_by_one_scan", "该方法需逐个检查输入。", "该方法的复杂度是 Θ(m)。"),
    ("unchanged_array", "原数组不会被修改。", "递归处理规模减半的输入，直到规模为一。"),
    ("attributed_substitution", "老师通过代入 m=2^j 来比较增长类。", "线性增长与对数增长的差别很大。"),
    ("implicit_larger_direction", "向较大的邻居所在的一侧递归。", "比较左右邻居，递归处理一半输入。"),
    ("predicate_inequality", "若元素大于等于左右邻居，则是峰值。", "检查元素是否为峰值，比较左右邻居。"),
    ("recursive_fanout", "递归地求解每个子问题。", "每次处理规模减半的一个子问题。"),
    (
        "cn_half_decision",
        "比较当前值与邻居来决定向哪一半继续搜索。",
        "比较当前值的左右邻居，递归处理一半规模的输入。",
    ),
    (
        "english_half_decision",
        "Compare neighbours to choose which half to search.",
        "Compare neighbours and recur on half-size input.",
    ),
    ("cn_disconnection", "旧对象与新对象完全无关。", "旧对象与新对象是不同的对象。"),
    ("cn_independence", "对象成为一个独立的字符串对象。", "变量 v 不再引用原对象。"),
    ("cn_unreferenced", "原对象成为独立的、未被引用的对象。", "变量 v 不再引用原对象。"),
    ("named_algorithm", "Use binary search on these values.", "Divide the current problem size by two."),
]


@pytest.mark.parametrize("name,answer,source", STRENGTHENINGS, ids=[c[0] for c in STRENGTHENINGS])
def test_stronger_assertion_cannot_pass_even_when_model_misjudges_true(name, answer, source):
    b = input_body(answer, source=source)
    quality = AtomicAnswerVerdict.model_validate(judgment(b), context=b).review()
    assert quality.issues == ["unsupported_explanation"]
    bad = [c for c in quality.atomic_assessments if not c.supported]
    assert bad and all(c.model_supported is True and c.strengthening_guards for c in bad)


@pytest.mark.parametrize(
    "answer",
    [
        "No variable references X.",
        "All items are ready.",
        "The gate will open.",
        "The gate is open until the timer expires.",
        "The object is completely isolated.",
        "没有任何变量引用对象 X。",
        "Inspect the middle element and its neighbours.",
        "Continue recursively in the left half.",
        "Use binary search on these values.",
    ],
)
def test_explicitly_supported_scope_still_requires_and_can_pass_model_review(answer):
    b = input_body(answer, source=answer)
    assert AtomicAnswerVerdict.model_validate(judgment(b), context=b).review().issues == []
    rejected = judgment(b, [c["source_text"].strip() for c in b["atomic_claims"]])
    assert AtomicAnswerVerdict.model_validate(rejected, context=b).review().issues == [
        "unsupported_explanation"
    ]


@pytest.mark.parametrize("crash", [False, True])
def test_runtime_delta_and_recovery_reuse_supported_spans_without_extra_model_calls(
    setup,  # noqa: F811
    monkeypatch,
    crash,  # noqa: F811
):
    store, authority, runtime, scope = setup
    original_read, original_decide = authority.read, runtime.provider.decide
    requests, decisions = [], []

    def course_read(current_scope, action="CHECK", **arguments):
        result = original_read(current_scope, action, **arguments)
        for item in result.get("evidence", []):
            item["text"] = SOURCE
        return result

    def decide(messages, timeout):
        b = json.loads(messages[-1]["content"])
        if not b["evidence"]:
            return original_decide(messages, timeout)
        decisions.append(b)
        if len(decisions) == 2:
            return {
                "name": "create_explanation",
                "arguments": {
                    "revision_edits": [
                        {"id": b["revision_transaction"]["rejected"][0]["id"], "replacement": ""}
                    ]
                },
            }
        return {
            "name": "create_explanation",
            "arguments": {"title": "State", "explanation": INITIAL, "evidence_ids": ["e1"]},
        }

    def handle(request):
        b = json.loads(json.loads(request.content)["messages"][-1]["content"])
        requests.append(b)
        return response(judgment(b))

    authority.read = course_read
    runtime.provider.decide = decide
    monkeypatch.setattr(httpx, "Client", lambda **kw: CLIENT(transport=httpx.MockTransport(handle), **kw))
    runtime.provider.review = ChatProvider("https://fixture.invalid/v1", "qwen3-max", "fixture-key").review
    original_save = store.save_tool

    def crash_after_saved_review(*args, **kwargs):
        result = original_save(*args, **kwargs)
        if result.get("quality", {}).get("atomic_basis"):
            store.save_tool = original_save
            raise SystemExit("after committed atomic observation")
        return result

    if crash:
        store.save_tool = crash_after_saved_review
    started = store.command(
        StudyCommand(**scope, operation="START", request_key="delta", goal="Explain the state."), "mock"
    )
    run = next(r for r in store.candidates() if r["run_id"] == started["run"]["run_id"])
    if crash:
        with pytest.raises(SystemExit):
            runtime.execute(run)
    runtime.execute(run)
    final = read(setup)
    assert final["run"]["status"] == "succeeded" and final["artifact"]["explanation"] == NARROWED
    assert final["run"]["model_calls"] == 5 and final["run"]["tool_calls"] == 3
    assert len(requests) == 2 and len(decisions) == 2 and requests[1]["atomic_claims"] == []
    assert requests[1]["reused_claim_ids"] and requests[1]["review_claim_ids"] == []
    assert authority.reads.count("SEARCH") == 1
    with store.connect() as conn:
        result = conn.execute(
            "SELECT result FROM study_tool_result WHERE run_id=%s AND result ? 'quality' ORDER BY call_id DESC",
            (run["run_id"],),
        ).fetchone()["result"]
    assert len(result["quality"]["atomic_delta"]["reused_ids"]) == 2
    assert result["quality"]["atomic_delta"]["rechecked_ids"] == []
    assert "prior_atomic_review" not in json.dumps(read(setup, "EVENTS"))
