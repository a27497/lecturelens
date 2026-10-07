import copy
import json

import httpx
import pytest
from test_study import read, setup  # noqa: F401
from test_study_atomic import judgment, response

from lecturelens_agent.study.atomic import atomic_claims
from lecturelens_agent.study.atomic_delta import digest
from lecturelens_agent.study.contracts import StudyCommand, tool_schemas
from lecturelens_agent.study.ledger import valid_fact
from lecturelens_agent.study.provider import ChatProvider, constrain_explanation_schemas
from lecturelens_agent.study.revision import UnfulfilledGoal, assemble_revision, freeze_revision


def frozen_history():
    answer = "The method compares neighboring values. It selects the middle position. The recursion stops at one item."
    claims = atomic_claims(answer)
    checks = [
        {
            **claim,
            "supported": i != 1,
            "model_supported": i != 1,
            "strengthening_guards": [],
            "evidence_ids": ["source"] if i != 1 else [],
        }
        for i, claim in enumerate(claims)
    ]
    history = [
        {
            "tool": "create_explanation",
            "arguments": {"title": "Method", "explanation": answer, "evidence_ids": ["source"]},
            "result": {
                "quality": {"atomic_basis": {"answer_sha256": digest(answer)}, "atomic_assessments": checks}
            },
        }
    ]
    return history


def test_revision_freezes_supported_rejected_and_raw_learner_goal():
    frozen = freeze_revision(
        frozen_history(),
        {"raw_question": "What does each step do?", "resolved_goal": "Middle position formula"},
    )
    assert [claim["id"] for claim in frozen["rejected"]] == ["a2"]
    assert [claim["id"] for claim in frozen["supported"]] == ["a1", "a3"]
    assert frozen["required_goals"][0]["text"] == "What does each step do?"
    answer = assemble_revision(frozen, [{"id": "a2", "replacement": "It checks one value. "}])["explanation"]
    assert answer == "The method compares neighboring values. The recursion stops at one item."


def test_unproved_replacement_is_deleted_before_assembly():
    answer = "扫描复杂度为Θ(n)，需要对输入逐个检查；而分治法将规模减半。"
    claims = atomic_claims(answer)
    checks = [
        {
            **claim,
            "supported": claim["id"] != "a2",
            "model_supported": True,
            "strengthening_guards": ["exhaustive_scan"] if claim["id"] == "a2" else [],
            "evidence_ids": ["source"],
        }
        for claim in claims
    ]
    history = [
        {
            "tool": "create_explanation",
            "arguments": {"title": "Compare", "explanation": answer, "evidence_ids": ["source"]},
            "result": {
                "quality": {
                    "atomic_basis": {
                        "answer_sha256": digest(answer),
                        "evidence": [
                            {"evidence_id": "source", "text_sha256": digest("Θ(n) versus halving.")}
                        ],
                    },
                    "atomic_assessments": checks,
                }
            },
        }
    ]
    frozen = freeze_revision(history, {"raw_question": "Compare.", "resolved_goal": "Compare."})
    assembled = assemble_revision(
        frozen,
        [{"id": "a2", "replacement": "对每个元素执行一次检查；"}],
        evidence=[{"evidence_id": "source", "text": "Θ(n) versus halving."}],
    )
    assert assembled["explanation"] == "扫描复杂度为Θ(n)，而分治法将规模减半。"


def test_unproved_count_replacement_narrows_to_source_bound_comparison():
    source = "每一步可能有两次比较，分别查看左侧和右侧邻居。"
    answer = "每一步执行两次比较，分别查看左侧和右侧邻居。"
    claims = atomic_claims(answer)
    checks = [
        {
            **claim,
            "supported": claim["id"] != "a1",
            "model_supported": True,
            "strengthening_guards": ["freeze_count_modality"] if claim["id"] == "a1" else [],
            "evidence_ids": ["source"],
        }
        for claim in claims
    ]
    history = [
        {
            "tool": "create_explanation",
            "arguments": {"title": "Compare", "explanation": answer, "evidence_ids": ["source"]},
            "result": {
                "quality": {
                    "atomic_basis": {
                        "answer_sha256": digest(answer),
                        "evidence": [{"evidence_id": "source", "text_sha256": digest(source)}],
                    },
                    "atomic_assessments": checks,
                }
            },
        }
    ]
    frozen = freeze_revision(
        history, {"raw_question": "What happens each step?", "resolved_goal": "What happens each step?"}
    )
    edits = [{"id": "a1", "replacement": "每一步执行两次比较并选择左半边，"}]
    revised = assemble_revision(frozen, edits, evidence=[{"evidence_id": "source", "text": source}])
    assert revised["explanation"] == "每一步执行比较，分别查看左侧和右侧邻居。"
    with pytest.raises(UnfulfilledGoal):
        assemble_revision(frozen, edits, evidence=[{"evidence_id": "source", "text": source + " 已更改。"}])


@pytest.mark.parametrize(
    "edits",
    [
        [],
        [{"id": "a1", "replacement": ""}],
        [{"id": "a2", "replacement": ""}, {"id": "a2", "replacement": ""}],
        [{"id": "a2", "replacement": "", "title": "changed"}],
    ],
)
def test_revision_rejects_missing_duplicate_or_extra_edits(edits):
    frozen = freeze_revision(frozen_history(), {"raw_question": "Explain.", "resolved_goal": "Explain."})
    with pytest.raises(ValueError):
        assemble_revision(frozen, edits)


def test_revision_schema_accepts_edits_only():
    schemas = constrain_explanation_schemas(
        tool_schemas(),
        {
            "revision_transaction": {
                "rejected": [{"id": "a2", "text": "bad"}],
                "supported": [{"id": "a1", "text": "good"}],
                "required_goals": [{"id": "g1", "text": "Explain."}],
            },
        },
        "Explain.",
        [],
    )
    params = next(
        s["function"]["parameters"] for s in schemas if s["function"]["name"] == "create_explanation"
    )
    assert params["required"] == ["revision_edits"]
    assert set(params["properties"]) == {"revision_edits"}
    assert params["properties"]["revision_edits"]["items"]["properties"]["id"]["enum"] == ["a2"]


def procedure_transaction(source=None, answer=None):
    source = source or (
        "方法将某个元素与左右邻居比较，随后递归处理输入规模减半的子问题。直到单元素基础情况，返回该元素。"
    )
    answer = answer or (
        "方法将某个元素与左右邻居比较。如果没有找到目标，"
        "则方法递归处理输入规模减半的子问题（即 T(m/2)）。"
        "直到单元素基础情况，返回该元素。"
    )
    claims = atomic_claims(answer)
    checks = [
        {
            **c,
            "supported": not (
                "如果" in c["source_text"] or "则方法" in c["source_text"] or "（即" in c["source_text"]
            ),
            "model_supported": True,
            "evidence_ids": ["owned"],
            "strengthening_guards": ["predicate_condition_specialization"]
            if "如果" in c["source_text"]
            else ["freeze_dependent_scope"]
            if "则方法" in c["source_text"] or "（即" in c["source_text"]
            else [],
        }
        for c in claims
    ]
    history = [
        {
            "tool": "create_explanation",
            "arguments": dict(title="Method", explanation=answer, evidence_ids=["owned"]),
            "result": {
                "quality": {
                    "atomic_basis": {
                        "answer_sha256": digest(answer),
                        "evidence": [{"evidence_id": "owned", "text_sha256": digest(source)}],
                    },
                    "atomic_assessments": checks,
                }
            },
        }
    ]
    evidence = [dict(evidence_id="owned", text=source)]
    semantic = dict(
        raw_question="Explain the method in concrete steps.",
        resolved_goal="Explain the method in concrete steps.",
    )
    return history, semantic, evidence


@pytest.mark.parametrize("proposal", ["", "则方法递归处理子问题。", "选择更大的邻居一侧继续递归。"])
def test_required_input_change_survives_deleted_or_invalid_proposed_branch(proposal):
    history, semantic, evidence = procedure_transaction()
    frozen = freeze_revision(history, semantic, evidence)
    edits = [
        {"id": c["id"], "replacement": proposal if "则方法" in c["source_text"] else ""}
        for c in frozen["rejected"]
    ]
    revised = assemble_revision(frozen, edits, evidence=evidence)["explanation"]
    assert "方法递归处理输入规模减半的子问题。" in revised
    assert "如果" not in revised and "更大" not in revised
    assert "左右邻居比较" in revised and "单元素基础情况" in revised
    assert all(c["source_text"] in revised for c in frozen["supported"])
    assert (
        revised == assemble_revision(json.loads(json.dumps(frozen)), edits, evidence=evidence)["explanation"]
    )


@pytest.mark.parametrize("failure", ["goal", "obligations", "protected", "rejected", "basis"])
def test_frozen_obligations_and_transaction_cannot_be_mutated(failure):
    history, semantic, evidence = procedure_transaction()
    frozen = freeze_revision(history, semantic, evidence)
    changed = copy.deepcopy(frozen)
    if failure == "goal":
        changed["goal_obligations"]["resolved_goal"] = "Explain only cost."
    elif failure == "obligations":
        changed["goal_obligations"]["obligations"].pop()
    elif failure == "protected":
        changed["supported"][0]["source_text"] = "Other."
    elif failure == "rejected":
        changed["rejected"][-1]["source_text"] = "Recurse on all branches."
    else:
        changed["evidence_basis"]["owned"] = digest("different")
    with pytest.raises(ValueError, match="transaction changed"):
        assemble_revision(
            changed, [{"id": c["id"], "replacement": ""} for c in changed["rejected"]], evidence=evidence
        )


def test_committed_obligations_are_replayed_without_rebinding_to_new_goal_or_sources():
    history, semantic, evidence = procedure_transaction()
    frozen = freeze_revision(history, semantic, evidence)
    history[0]["result"]["revision_transaction"] = frozen
    recovered = json.loads(json.dumps(history))
    assert freeze_revision(recovered, semantic, []) == frozen
    with pytest.raises(ValueError, match="frozen answer or learner goal"):
        freeze_revision(recovered, {**semantic, "resolved_goal": "Explain only cost."}, evidence)
    changed = copy.deepcopy(recovered)
    changed[0]["arguments"]["explanation"] += " Added."
    with pytest.raises(ValueError, match="frozen answer or learner goal"):
        freeze_revision(changed, semantic, evidence)


@pytest.mark.parametrize("failure", ["stale", "missing", "foreign"])
def test_goal_preservation_never_restores_a_needed_predicate_without_live_frozen_evidence(failure):
    history, semantic, evidence = procedure_transaction()
    frozen = freeze_revision(history, semantic, evidence)
    changed = copy.deepcopy(evidence)
    if failure == "stale":
        changed[0]["text"] += " changed"
    elif failure == "foreign":
        changed[0]["evidence_id"] = "foreign"
    else:
        changed = []
    with pytest.raises(UnfulfilledGoal):
        assemble_revision(
            frozen, [{"id": c["id"], "replacement": ""} for c in frozen["rejected"]], evidence=changed
        )


def test_explicit_required_but_unsourced_detail_is_not_synthesized_from_goal():
    history, semantic, evidence = procedure_transaction(source="Only neighbor comparisons are observed.")
    semantic = dict(
        raw_question="Explain concrete steps and how the input halves.",
        resolved_goal="Explain concrete steps and how the input halves.",
    )
    frozen = freeze_revision(history, semantic, evidence)
    missing = next(o for o in frozen["goal_obligations"]["obligations"] if o["kind"] == "input_change")
    assert missing["evidence_ids"] == []
    with pytest.raises(UnfulfilledGoal):
        assemble_revision(
            frozen, [{"id": c["id"], "replacement": ""} for c in frozen["rejected"]], evidence=evidence
        )


def test_source_bound_component_question_does_not_inherit_whole_method_obligations():
    history, _, evidence = procedure_transaction()
    semantic = dict(
        raw_question="Explain the constant term in concrete steps.",
        resolved_goal="Explain the constant term.",
    )
    frozen = freeze_revision(history, semantic, evidence)
    assert [o["kind"] for o in frozen["goal_obligations"]["obligations"]] == ["whole_goal"]
    assert frozen["goal_obligations"]["resolved_goal"] == semantic["resolved_goal"]


@pytest.mark.parametrize(
    "goal",
    [
        "Explain the method in concrete steps, without halving the input.",
        "具体解释这个方法，但不要解释规模减半。",
    ],
)
def test_frozen_goal_obligations_preserve_explicit_learner_exclusions(goal):
    history, _, evidence = procedure_transaction()
    frozen = freeze_revision(history, dict(raw_question=goal, resolved_goal=goal), evidence)
    assert all(o["kind"] != "input_change" for o in frozen["goal_obligations"]["obligations"])
    assert frozen["required_goals"][0]["text"] == goal


def test_a_prior_review_of_a_different_goal_cannot_supply_revision_obligations():
    history, semantic, evidence = procedure_transaction()
    history[0]["result"]["quality"]["atomic_basis"]["goal_sha256"] = digest("Different learner goal.")
    assert freeze_revision(history, semantic, evidence) is None


def test_replacing_rejected_punctuation_cannot_modify_protected_exact_span():
    history, semantic, evidence = procedure_transaction()
    frozen = freeze_revision(history, semantic, evidence)
    edits = [{"id": c["id"], "replacement": "。" if i == 0 else ""} for i, c in enumerate(frozen["rejected"])]
    revised = assemble_revision(frozen, edits, evidence=evidence)["explanation"]
    assert all(c["source_text"] in revised for c in frozen["supported"])


@pytest.mark.parametrize("crash", [False, True])
@pytest.mark.parametrize("unavailable", [False, True])
def test_goal_preserving_revision_commits_obligations_and_recovers_without_repeat_review(
    setup,  # noqa: F811 -- imported PostgreSQL fixture
    monkeypatch,
    crash,
    unavailable,
):
    store, authority, runtime, scope = setup
    history, _, sources = procedure_transaction(
        source="The method compares left and right neighbors." if unavailable else None
    )
    initial = history[0]["arguments"]["explanation"]
    original_read, original_save = authority.read, store.save_tool
    reviews, views = [], []
    client_type = httpx.Client

    def course_read(s, action="CHECK", **kw):
        result = original_read(s, action, **kw)
        for e in result.get("evidence", []):
            e["text"] = sources[0]["text"]
        return result

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["history"]:
            return dict(
                name="search_course_evidence",
                arguments=dict(
                    query=body["goal"],
                    practice_kind="general",
                    output_kind="explanation",
                ),
            )
        frozen = body.get("revision_transaction")
        if frozen:
            views.append(frozen)
            return dict(
                name="create_explanation",
                arguments=dict(revision_edits=[dict(id=c["id"], replacement="") for c in frozen["rejected"]]),
            )
        return dict(
            name="create_explanation",
            arguments=dict(
                title="Method",
                explanation=initial,
                evidence_ids=["e1"],
            ),
        )

    def handle(request):
        body = json.loads(json.loads(request.content)["messages"][-1]["content"])
        reviews.append(body)
        if "candidate" not in body:
            return response(
                dict(
                    support="absent",
                    course_fact="Input reduction is not observed.",
                    evidence_ids=["e1"],
                    missing_goal_quote="how the input halves",
                )
            )
        return response(judgment(body))

    def save_crash(*args, **kwargs):
        result = original_save(*args, **kwargs)
        if args[3] == "create_explanation" and result.get("revision_transaction"):
            store.save_tool = original_save
            raise SystemExit("after committed immutable goal obligations")
        return result

    authority.read = course_read
    runtime.provider.decide = decide
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: client_type(transport=httpx.MockTransport(handle), **kw)
    )
    runtime.provider.review = ChatProvider("https://fixture.invalid/v1", "qwen3-max", "fixture").review
    started = store.command(
        StudyCommand(
            **scope,
            operation="START",
            request_key="goal-preserving",
            goal="Explain the method in concrete steps and how the input halves."
            if unavailable
            else "Explain the method in concrete steps.",
        ),
        "mock",
    )
    run = next(r for r in store.candidates() if r["run_id"] == started["run"]["run_id"])
    if crash:
        store.save_tool = save_crash
        with pytest.raises(SystemExit, match="committed immutable"):
            runtime.execute(run)
        assert len(reviews) == 1
    runtime.execute(run)
    result = read(setup)
    assert result["run"]["status"] == "succeeded"
    assert result["run"]["model_calls"] == 5
    assert len(reviews) == 2 and len(views) == 1
    answer = result["artifact"]["explanation"]
    if unavailable:
        assert result["artifact"]["kind"] == "insufficient_evidence"
        assert "do not provide enough support" in answer
        assert "candidate" not in reviews[-1]  # Independent coverage-only refusal check.
    else:
        assert "goal_scope_binding" in reviews[-1] and "revision_goal_obligations" not in reviews[-1]
        assert "左右邻居" in answer and "规模减半" in answer and "单元素基础情况" in answer
        assert "如果" not in answer
        for claim in history[0]["result"]["quality"]["atomic_assessments"]:
            if claim["supported"]:
                assert claim["source_text"] in answer
    facts = store.supported_facts(run)
    assert any("规模减半" in f["text"] for f in facts) is (not unavailable)
    assert all(valid_fact(f, run) for f in facts)
    with store.connect() as conn:
        saved = conn.execute(
            "SELECT result FROM study_tool_result WHERE run_id=%s AND tool_name='create_explanation' ORDER BY call_id",
            (run["run_id"],),
        ).fetchall()
    frozen = next(
        row["result"]["revision_transaction"] for row in saved if "revision_transaction" in row["result"]
    )
    assert views[0]["goal_obligations_sha256"] == frozen["transaction_sha256"]
    assert all(
        u["supported"] and u["model_supported"] is True and not u["strengthening_guards"]
        for f in facts
        for u in f["source_units"]
    )
    assert "transaction_sha256" not in json.dumps(read(setup, "EVENTS"))
