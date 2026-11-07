"""Retained v13 responses and PostgreSQL mechanics; never real-model quality."""

import copy
import json
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v14_contract as C
from lecturelens_agent.study.store import StudyError
from lecturelens_real_eval.tutor.claim_grounding_runtime import LessonAuthority
from lecturelens_real_eval.tutor.contracts import Command
from lecturelens_real_eval.tutor.draft_repair_runtime import ENTAILMENT, REPAIR_DRAFT, DraftRepairTutorRuntime
from lecturelens_real_eval.tutor.store import TutorStore

RAW = C.ROOT / ".data/tutor-v13-resumed-20261107/v13-new16-first"


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def save(name, value):
    output = Path(os.environ["V14_CHECK_OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    with (output / name).open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, default=str)
        stream.write("\n")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    assert os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") == "1"
    original = os.environ.get

    def get(key, *args):
        if key in {"AGENT_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"}:
            pytest.fail("Credential lookup forbidden")
        return original(key, *args)

    monkeypatch.setattr(os.environ, "get", get)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kw: pytest.fail("Real transport forbidden"))


@pytest.fixture
def isolated():
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    schema = "v14_offline_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        yield make_conninfo(dsn, options=f"-csearch_path={schema},public")
    finally:
        with psycopg.connect(dsn) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


class Capture:
    def __init__(self, decide):
        self.decide_inner, self.requests = decide, []

    def decide(self, messages, schemas, timeout):
        self.requests.append(copy.deepcopy((messages, schemas)))
        return self.decide_inner(json.loads(messages[-1]["content"]))


def execute(dsn, provider, *, runtime_class=DraftRepairTutorRuntime, question="Explain list copying"):
    _, _, snapshot, _, _ = C.historical.verify()
    authority = LessonAuthority(snapshot)
    scope = dict(owner_id=811012, course_id="v14-" + uuid.uuid4().hex, revision=1)
    authority.register(scope, "carpentries-python")
    store = TutorStore(dsn)
    runtime = runtime_class(store, authority, provider)
    runtime.initialize()
    try:
        scope["session_id"] = runtime.command(Command(**scope, operation="CREATE", request_key="s"))[
            "session"
        ]["session_id"]
        result = runtime.command(Command(**scope, operation="TURN", client_turn_id="one", text=question))
        candidate = dict(session_id=scope["session_id"], turn_id=result["turns"][-1]["turn_id"])
        runtime.execute(candidate)
        with store.connect() as conn:
            session, turn = store.rows(conn, candidate["turn_id"])
        return session, turn, authority, scope
    finally:
        runtime.close()


def proposal(text, evaluation=""):
    return dict(
        name="finish_tutor_turn", arguments=dict(outcome="answered", text=text, evaluation=evaluation)
    )


def sizes(first, second=None, *, field="text"):
    def decide(body):
        if not body["observations"]:
            return dict(name="search_tutor_evidence", arguments=dict(query="lists mutable copy memory"))
        repair = body["observations"][-1].get("error") == "TUTOR_FINISH_REPAIR_REQUIRED"
        n = second if repair else first
        eid = body["evidence"][0]["evidence_id"]
        value = "A [" + eid + "]"
        value += "字" * (n - len(value))
        return proposal(value) if field == "text" else proposal("Supported [" + eid + "]", value)

    return Capture(decide)


@pytest.mark.parametrize("field,limit", [("text", 1600), ("evaluation", 500)])
@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_exact_unicode_length_boundaries(isolated, field, limit, delta):
    p = sizes(limit + delta, limit, field=field)
    session, turn, _, _ = execute(isolated, p)
    assert turn["status"] == "completed"
    assert turn["model_calls"] == (3 if delta == 1 else 2)
    assert len(turn["answer"] if field == "text" else turn["evaluation"]) == min(limit, limit + delta)
    assert (
        turn["reserved_tokens"]
        == session["reserved_tokens"]
        == sum(len(json.dumps([m, s], ensure_ascii=False).encode()) + 1200 for m, s in p.requests)
    )
    assert turn["reserved_tokens"] <= 64000
    for messages, schemas in p.requests:
        finish = next((s for s in schemas if s["function"]["name"] == "finish_tutor_turn"), None)
        if finish:
            props = finish["function"]["parameters"]["properties"]
            assert props["text"]["maxLength"] == 1600 and props["evaluation"]["maxLength"] == 500
        body = json.loads(messages[-1]["content"])
        if "rejected_finish" in body:
            assert len(body["rejected_finish"][field]) == limit + 1
            assert [s["function"]["name"] for s in schemas] == ["finish_tutor_turn"]
            assert REPAIR_DRAFT in messages[0]["content"]
        else:
            assert REPAIR_DRAFT not in messages[0]["content"]


@pytest.mark.parametrize("initial,repair", [(1657, 1691), (1601, 1601), (1600, None)])
def test_format_exhaustion_preserves_failure_or_exact_answer(isolated, initial, repair):
    p = sizes(initial, repair)
    _, turn, _, _ = execute(isolated, p)
    assert turn["status"] == ("completed" if repair is None else "failed")
    if repair:
        assert turn["error_code"] == "TUTOR_FINISH_FORMAT_INVALID"
        assert turn["answer"] is None and not turn["citations"] and turn["model_calls"] == 3
        assert len(turn["checkpoint"]["response"]["arguments"]["text"]) == repair
    else:
        assert len(turn["answer"]) == initial


def test_original_repair_wire_omits_draft_and_new_request_restores_exact_draft(isolated):
    row = next(r for r in lines(RAW / "turns.jsonl") if r["status"] == "failed")
    old = read(RAW / "wire/034-request.json")
    oldbody = json.loads(old["messages"][-1]["content"])
    assert "rejected_finish" not in oldbody
    first = row["proposals"][1]["arguments"]
    assert len(first["text"]) == 1657 and first["text"] not in json.dumps(oldbody, ensure_ascii=False)
    requests = iter(copy.deepcopy(row["proposals"]))
    p = Capture(lambda body: next(requests))
    # The original failed task is the very first turn in its session; no fabricated history.
    _, _, snapshot, _, _ = C.historical.verify()
    authority = LessonAuthority(snapshot)
    scope = dict(owner_id=811012, course_id="v14-original-failure", revision=1)
    authority.register(scope, "carpentries-spreadsheets")
    runtime = DraftRepairTutorRuntime(TutorStore(isolated), authority, p)
    runtime.initialize()
    try:
        scope["session_id"] = runtime.command(Command(**scope, operation="CREATE", request_key="s"))[
            "session"
        ]["session_id"]
        result = runtime.command(
            Command(**scope, operation="TURN", client_turn_id="one", text=row["learner_text"])
        )
        candidate = dict(session_id=scope["session_id"], turn_id=result["turns"][-1]["turn_id"])
        runtime.execute(candidate)
        with runtime.store.connect() as conn:
            _, turn = runtime.store.rows(conn, candidate["turn_id"])
        assert turn["status"] == "failed" and turn["error_code"] == "TUTOR_FINISH_FORMAT_INVALID"
        messages, schemas = p.requests[-1]
        body = json.loads(messages[-1]["content"])
        assert body["rejected_finish"] == {"outcome": "answered", "text": first["text"], "evaluation": ""}
        assert body["evidence"] == oldbody["evidence"]
        assert schemas == old["tools"]
        assert (
            turn["reserved_tokens"]
            == sum(len(json.dumps([m, s], ensure_ascii=False).encode()) + 1200 for m, s in p.requests)
            < 64000
        )
        # Checkpointed prepaid request is the exact request sent, even across restart.
        assert turn["checkpoint"]["response"]["arguments"] == row["proposals"][-1]["arguments"]
        save("original-failure-new-context.json", dict(turn=turn, repair_body=body, requests=p.requests))
    finally:
        runtime.close()


@pytest.mark.parametrize("bad", [None, {}, {"name": "search_tutor_evidence", "arguments": {}}])
def test_missing_draft_is_protocol_failure_not_silent_regeneration(isolated, bad):
    p = sizes(1601, 1600)
    _, turn, authority, scope = execute(isolated, p)
    state = copy.deepcopy(turn["checkpoint"])
    state["response"] = bad
    runtime = DraftRepairTutorRuntime(TutorStore(isolated), authority, p)
    # None must also fail with a safe StudyError rather than leak a raw exception.
    with pytest.raises(StudyError, match="TUTOR_PROTOCOL_FAILURE"):
        runtime.request({**scope, "summary": ""}, turn, state, [])


def test_added_draft_cannot_bypass_existing_reservation(isolated):
    p = sizes(64001, 1600)
    _, turn, _, _ = execute(isolated, p)
    assert turn["status"] == "failed" and turn["error_code"] == "TUTOR_REPAIR_BUDGET_UNAVAILABLE"
    assert turn["model_calls"] == 2 and len(p.requests) == 2
    assert len(turn["checkpoint"]["response"]["arguments"]["text"]) == 64001
    assert turn["answer"] is None


@pytest.mark.parametrize("count", [4, 5])
def test_rejected_draft_cannot_reauthorize_removed_citations(isolated, count):
    drafts = []

    def decide(body):
        if not body["observations"]:
            return dict(name="search_tutor_evidence", arguments=dict(query="lists mutable copy memory"))
        if "rejected_finish" not in body:
            text = " ".join("Point [" + e["evidence_id"] + "]" for e in body["evidence"][:count])
            drafts.append(text)
            return proposal(text)
        assert body["rejected_finish"]["text"] == drafts[0]
        assert len(body["evidence"]) == 4
        removed = body["observations"][-1]["remove_ids"]
        assert len(removed) == 1 and removed[0] not in [e["evidence_id"] for e in body["evidence"]]
        # Reintroducing a fifth observed source is still a second format failure.
        return proposal(drafts[0])

    p = Capture(decide)
    _, turn, _, _ = execute(isolated, p)
    assert turn["status"] == ("completed" if count == 4 else "failed")
    assert turn["model_calls"] == (2 if count == 4 else 3)
    if count == 5:
        assert turn["error_code"] == "TUTOR_FINISH_FORMAT_INVALID" and turn["answer"] is None


def test_development_manifest_tamper_refused(tmp_path, monkeypatch):
    manifest = read(C.HERE / "candidate.json")
    manifest["default_registration"] = True
    (tmp_path / "candidate.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(C, "HERE", tmp_path)
    with pytest.raises(ValueError, match="V14_IDENTITY_CHANGED"):
        C.verify_candidate()


def test_actual_long_initial_with_complete_cited_mock_repair(isolated):
    row = next(r for r in lines(RAW / "turns.jsonl") if r["status"] == "failed")
    first = row["proposals"][1]["arguments"]
    ids = row["checkpoint"]["observations"][-1]["keep_ids"]
    # Test-only composition audited against original lines 91–100. This is not
    # an answer generator, prompt example, reference leak or measured improvement.
    answer = (
        "Save the original formula-containing file with a name marking it as original data. "
        "Create a separately named and versioned working file containing values rather than formulas. "
        "Formulas refer to other cells, so moving cells can compromise data integrity. [" + ids[0] + "]\n"
        "Create a README to track files and manipulations so your future self or another researcher "
        "can understand and replicate them. Document all files, including documentation, their "
        "content and format, the organizing principles of folders/subfolders, and the manipulations "
        "or analyses performed on each file. [" + ids[3] + "]"
    )
    assert len(answer) < 1200
    responses = iter([row["proposals"][0], row["proposals"][1], proposal(answer)])
    p = Capture(lambda body: copy.deepcopy(next(responses)))
    _, _, snapshot, _, _ = C.historical.verify()
    authority = LessonAuthority(snapshot)
    scope = dict(owner_id=811012, course_id="v14-complete-repair", revision=1)
    authority.register(scope, "carpentries-spreadsheets")
    runtime = DraftRepairTutorRuntime(TutorStore(isolated), authority, p)
    runtime.initialize()
    try:
        scope["session_id"] = runtime.command(Command(**scope, operation="CREATE", request_key="s"))[
            "session"
        ]["session_id"]
        submitted = runtime.command(
            Command(**scope, operation="TURN", client_turn_id="one", text=row["learner_text"])
        )
        turn_id = submitted["turns"][-1]["turn_id"]
        runtime.execute(dict(session_id=scope["session_id"], turn_id=turn_id))
        with runtime.store.connect() as conn:
            _, turn = runtime.store.rows(conn, turn_id)
        assert turn["status"] == "completed" and turn["answer"] == answer
        assert [e["evidence_id"] for e in turn["citations"]] == [ids[0], ids[3]]
        assert json.loads(p.requests[-1][0][-1]["content"])["rejected_finish"]["text"] == first["text"]
        save("complete-cited-mock-repair.json", dict(turn=turn, test_only=True, real_quality="NOT_RUN"))
    finally:
        runtime.close()


def patched_entry(monkeypatch):
    import trial_run_v2 as entry

    proxy = SimpleNamespace(**vars(C.historical))
    proxy.CANDIDATE, proxy.ENTRYPOINT, proxy.verify_candidate = C.CANDIDATE, C.ENTRYPOINT, C.verify_candidate
    monkeypatch.setattr(entry, "contract", proxy)
    monkeypatch.setattr(entry, "ClaimGroundingTutorRuntime", DraftRepairTutorRuntime)
    return entry


def args(entry, output, cap=80, money="0.70"):
    return entry.parser().parse_args(
        [
            "--mock",
            "--agent",
            entry.contract.CANDIDATE,
            "--model",
            "deepseek-flash",
            "--max-calls",
            str(cap),
            "--max-usd",
            money,
            "--output",
            str(output),
        ]
    )


@pytest.mark.parametrize("new", [False, True])
def test_full_v13_retained_parsed_response_replay(isolated, tmp_path, monkeypatch, new):
    import trial_run_v2 as original

    entry = patched_entry(monkeypatch) if new else original
    oldrows = lines(RAW / "turns.jsonl")
    frames = []
    for row in oldrows:
        proposals = iter(row.get("proposals", []))
        for call in row["calls"]:
            first = next(proposals)
            frames.append((call, [first] + [next(proposals) for _ in range(first["dropped_tool_calls"])]))
        assert next(proposals, None) is None
    sent = []

    def send(request):
        n = len(sent)
        if not new:
            assert request.content == (RAW / f"wire/{n + 1:03d}-request.json").read_bytes()
        else:
            assert ENTAILMENT in json.loads(request.content)["messages"][0]["content"]
        call, group = frames[n]
        sent.append(n)
        return httpx.Response(
            200,
            json=dict(
                id=call["response_id"],
                model=call["returned_model"],
                system_fingerprint=call["system_fingerprint"],
                usage=call["usage"],
                choices=[
                    dict(
                        finish_reason="tool_calls",
                        message=dict(
                            tool_calls=[
                                dict(
                                    type="function",
                                    function=dict(name=p["name"], arguments=json.dumps(p["arguments"])),
                                )
                                for p in group
                            ]
                        ),
                    )
                ],
            ),
        )

    output = tmp_path / ("v14-replay" if new else "v13-control")
    result = entry.run(args(entry, output), dsn=isolated, transport=httpx.MockTransport(send))
    replay = lines(output / "turns.jsonl")
    assert len(sent) == 34
    assert tuple(result[k] for k in ("completed", "failed", "skipped", "missing")) == (12, 1, 3, 0)
    assert [r["answer"] for r in replay] == [r["answer"] for r in oldrows]
    assert result["ledger"]["nano_usd"] == 45606300 and result["reviewer_calls"] == 0
    assert replay[12]["error_code"] == "TUTOR_FINISH_FORMAT_INVALID"
    assert all(r["root_failure"] == "new-sheets-qc:1" for r in replay[13:])
    save(
        "full-replay-" + str(new) + ".json",
        dict(
            summary=result,
            output=str(output),
            answers_unchanged=12,
            quality_improvement="NOT_RUN",
            original_body_bytes_retained=False,
        ),
    )


@pytest.mark.parametrize(
    "fault,cap,money,expected",
    [
        (None, 80, "0.70", (16, 0, 0, 0, 32)),
        ("local", 80, "0.70", (12, 1, 3, 0, 27)),
        ("usage", 80, "0.70", (0, 1, 0, 15, 1)),
        ("auth", 80, "0.70", (0, 1, 0, 15, 1)),
        ("fabricated", 80, "0.70", (0, 1, 0, 15, 2)),
        (None, 1, "0.70", (0, 1, 0, 15, 1)),
        (None, 80, "0.000000001", (0, 1, 0, 15, 0)),
    ],
)
def test_v14_full16_mock_failure_contract(isolated, tmp_path, monkeypatch, fault, cap, money, expected):
    from test_grounding import new_transport

    entry = patched_entry(monkeypatch)
    output = tmp_path / "v14-mock"
    result = entry.run(args(entry, output, cap, money), dsn=isolated, transport=new_transport(fault))
    assert (
        tuple(result[k] for k in ("completed", "failed", "skipped", "missing", "wire_requests")) == expected
    )
    assert result["reviewer_calls"] == 0 and result["quality_status"] == "NOT_RUN"
    rows = lines(output / "turns.jsonl")
    assert len(rows) == 16
    if fault == "local":
        assert rows[1]["skip_code"] == "DEPENDENCY_FAILED_OR_SKIPPED"
        assert rows[2]["skip_code"] == "SESSION_CLOSED_AFTER_LOCAL_FAILURE"
        assert all(r["status"] == "completed" for r in rows[4:])
        for wire in sorted((output / "wire").glob("*-request.json")):
            body = json.loads(read(wire)["messages"][-1]["content"])
            if body["learner_text"] == rows[4]["learner_text"]:
                assert body["history"] == [] and body["summary"] == ""
    with psycopg.connect(isolated) as conn:
        assert [
            r[0] for r in conn.execute("SELECT record FROM p8_tutor_real_event ORDER BY sequence")
        ] == lines(output / "ledger.jsonl")
    save("v14-mock-" + str(fault) + "-" + str(cap) + "-" + money + ".json", result)


@pytest.mark.parametrize(
    "claim",
    [
        "Only the list form produces the drop-down aid.",
        "Sorting is only safe for a well-structured dataset that does not contain formulas.",
        "If two names refer to the same list, an in-place edit changes the shared list.",
        "This tutorial covers only this example, not all applications.",
    ],
)
def test_entailment_guidance_does_not_pretend_to_verify_semantics(isolated, claim):
    def decide(body):
        if not body["observations"]:
            return dict(name="search_tutor_evidence", arguments=dict(query="lists mutable copy memory"))
        return proposal(claim + " [" + body["evidence"][0]["evidence_id"] + "]")

    p = Capture(decide)
    _, turn, _, _ = execute(isolated, p)
    assert turn["status"] == "completed" and turn["answer"].startswith(claim)
    assert all(ENTAILMENT in m[0]["content"] for m, _ in p.requests)
    # No lexical 'only' rejection, hidden semantic pass, truncation or citation auto-fill.
    # The first two are intentionally unsupported fixture outputs, not quality successes.


def test_candidate_verification_and_no_paid_entry():
    assert len(C.verify_offline()) == 64
    assert C.historical.verify_candidate() == C.PARENT_SHA
    assert C.historical.verify()[0]["candidate"] != C.CANDIDATE
    assert not (C.HERE / "rerun.py").exists()


def test_original_claim_offsets_source_quotes_usage_and_ledger_reconciliation():
    from v14_audit import audit

    result = audit()
    assert result["citations"]["explicit_pair_support"] == [37, 38]
    assert result["citations"]["supported_claim_coverage"] == [36, 37]
    save("historical-audit.json", result)
