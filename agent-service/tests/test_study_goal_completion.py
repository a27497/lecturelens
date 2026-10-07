import copy
import json

import httpx
import pytest
from test_study import read, setup  # noqa: F401
from test_study_atomic import judgment, response
from test_study_ledger import supported
from test_study_revision import procedure_transaction

from lecturelens_agent.study.atomic_delta import digest
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.goal_completion import complete_obligations, source_sentences
from lecturelens_agent.study.goal_obligations import missing_obligations
from lecturelens_agent.study.provider import ChatProvider
from lecturelens_agent.study.revision import (
    InsufficientGoalEvidence,
    assemble_revision,
    freeze_revision,
)


def transaction(source=None):
    history, semantic, evidence = procedure_transaction(
        source=source
        or "The method compares left and right neighbors. The input halves. The base case returns one item.",
        answer="方法将某个元素与左右邻居比较。如果未找到峰值，则选择一侧子数组。直到单元素基础情况，返回该元素。",
    )
    for check in history[0]["result"]["quality"]["atomic_assessments"]:
        if "则选择" in check["source_text"]:
            check.update(supported=False, strengthening_guards=["branch_specialization"])
    return history, semantic, evidence


def test_missing_wording_is_completed_only_from_exact_current_source():
    history, semantic, evidence = transaction()
    frozen = freeze_revision(history, semantic, evidence)
    audit = []
    revised = assemble_revision(
        frozen,
        [{"id": c["id"], "replacement": ""} for c in frozen["rejected"]],
        evidence=evidence,
        completion_audit=audit,
    )
    answer = revised["explanation"]
    assert "一侧子数组" not in answer and "如果" not in answer
    assert not missing_obligations(frozen["goal_obligations"], answer, evidence)
    assert all(c["source_text"] in answer for c in frozen["supported"])
    assert len(audit) == 1 and audit[0]["obligation_id"] == "procedure_input_change"
    item = audit[0]
    assert evidence[0]["text"][item["start"] : item["end"]] == item["source_text"]
    assert item["source_text"].strip() == "The input halves."
    assert item["evidence_hashes"] == {"owned": digest(evidence[0]["text"])}
    assert "The base case returns one item." not in answer  # Already satisfied; no unrelated source copying.
    assert json.loads(json.dumps(frozen)) == frozen


@pytest.mark.parametrize("failure", ["missing", "stale", "foreign"])
def test_completion_never_borrows_non_frozen_evidence(failure):
    history, semantic, evidence = transaction()
    frozen = freeze_revision(history, semantic, evidence)
    changed = copy.deepcopy(evidence)
    if failure == "missing":
        changed = []
    elif failure == "stale":
        changed[0]["text"] += " Different version."
    else:
        changed[0]["evidence_id"] = "foreign"
    with pytest.raises(InsufficientGoalEvidence):
        assemble_revision(
            frozen, [{"id": c["id"], "replacement": ""} for c in frozen["rejected"]], evidence=changed
        )


def test_live_evidence_extraction_failure_is_not_evidence_insufficiency():
    history, semantic, evidence = transaction()
    frozen = freeze_revision(history, semantic, evidence)
    answer, additions, missing, insufficient = complete_obligations(
        frozen,
        "The method compares left and right neighbors. The base case returns one item.",
        evidence,
        [],
        lambda *_: False,
    )
    assert additions == [] and missing and insufficient == []


@pytest.mark.parametrize("corrupt", [False, True])
def test_only_verified_current_fact_can_supply_completion(corrupt):
    history, semantic, evidence = transaction()
    evidence[0]["evidence_id"] = "canonical"
    prior = history[0]
    prior["arguments"]["evidence_ids"] = ["canonical"]
    prior["result"]["quality"]["atomic_basis"]["evidence"][0]["evidence_id"] = "canonical"
    for c in prior["result"]["quality"]["atomic_assessments"]:
        c["evidence_ids"] = ["canonical"]
    facts = supported("The input halves.", source=evidence[0]["text"])
    assert len(facts) == 1
    if corrupt:
        facts[0]["source_claim"]["supported"] = False
    frozen = freeze_revision(history, semantic, evidence)
    audit = []
    revised = assemble_revision(
        frozen,
        [{"id": c["id"], "replacement": ""} for c in frozen["rejected"]],
        evidence=evidence,
        supported_facts=facts,
        completion_audit=audit,
    )
    assert "The input halves" in revised["explanation"]
    assert ("fact_id" in audit[0]) is not corrupt
    assert ("source_text" in audit[0]) is corrupt


def test_sentence_extraction_keeps_decimal_and_modality_scope():
    text = "Each step may inspect half-sized inputs in 0.5 seconds. The base case has size 1. End."
    spans = list(source_sentences(text))
    assert [s[2].strip() for s in spans] == [
        "Each step may inspect half-sized inputs in 0.5 seconds.",
        "The base case has size 1.",
        "End.",
    ]
    assert all(text[start:end] == literal for start, end, literal in spans)


@pytest.mark.parametrize("reject_completion", [False, True])
def test_runtime_reviews_completion_before_publication_and_never_researches(
    setup,  # noqa: F811 -- imported PostgreSQL fixture
    monkeypatch,
    reject_completion,
):
    store, authority, runtime, scope = setup
    history, _, evidence = transaction()
    initial = history[0]["arguments"]["explanation"]
    original_read = authority.read
    requests = []

    def course_read(scope, action="CHECK", **kw):
        result = original_read(scope, action, **kw)
        for e in result.get("evidence", []):
            e["text"] = evidence[0]["text"]
        return result

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["history"]:
            return dict(
                name="search_course_evidence", arguments=dict(query=body["goal"], output_kind="explanation")
            )
        if body.get("revision_transaction"):
            return dict(
                name="create_explanation",
                arguments=dict(
                    revision_edits=[
                        dict(id=c["id"], replacement="") for c in body["revision_transaction"]["rejected"]
                    ]
                ),
            )
        return dict(
            name="create_explanation",
            arguments=dict(title="Method", explanation=initial, evidence_ids=["e1"]),
        )

    def handle(request):
        body = json.loads(json.loads(request.content)["messages"][-1]["content"])
        requests.append(body)
        verdict = judgment(body)
        if len(requests) == 2:
            assert "goal_scope_binding" in body and "revision_goal_obligations" not in body
            completion = next(
                c
                for c in body["atomic_claims"]
                if "The input halves." in body["candidate"]["explanation"][c["start"] : c["end"]]
            )
            assert completion["id"] in body["review_claim_ids"]
            assert body["reused_claim_ids"]
            if reject_completion:
                rejected = next(c for c in verdict["claim_checks"] if c["id"] == completion["id"])
                rejected.update(supported=False, evidence_ids=[])
                rejected["relation"]["grounds"] = []
        return response(verdict)

    authority.read = course_read
    runtime.provider.decide = decide
    client_type = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: client_type(transport=httpx.MockTransport(handle), **kw)
    )
    runtime.provider.review = ChatProvider("https://fixture.invalid/v1", "qwen3-max", "fixture").review
    started = store.command(
        StudyCommand(
            **scope,
            operation="START",
            request_key="goal-completion",
            goal="Explain the method in concrete steps.",
        ),
        "mock",
    )
    run = next(r for r in store.candidates() if r["run_id"] == started["run"]["run_id"])
    runtime.execute(run)
    result = read(setup)
    assert len(requests) == 2 and result["run"]["model_calls"] == 5
    assert authority.reads.count("SEARCH") == 1
    if reject_completion:
        assert result["run"]["status"] == "failed" and result["artifact"] is None
        assert result["run"]["error_code"] == "QUALITY_REPAIR_EXHAUSTED"
        assert not any("The input halves." in f["text"] for f in store.supported_facts(run))
    else:
        assert result["run"]["status"] == "succeeded"
        assert "The input halves." in result["artifact"]["explanation"]
    public = json.dumps(read(setup, "EVENTS"))
    assert "source_text" not in public and "transaction_sha256" not in public
    with store.connect() as conn:
        event = conn.execute(
            "SELECT trace_detail FROM study_event WHERE run_id=%s AND event_type='revision_goal_completed'",
            (run["run_id"],),
        ).fetchone()
    assert event["trace_detail"]["additions"][0]["source_text"].strip() == "The input halves."
