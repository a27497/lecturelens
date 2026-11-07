"""Source-context and frozen-response regressions; no semantic model-quality oracle."""

import copy
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v13_contract as C
from lecturelens_real_eval.tutor.claim_grounding_runtime import (
    GROUNDING,
    ClaimGroundingTutorRuntime,
    LessonAuthority,
    lesson_passages,
)
from lecturelens_real_eval.tutor.contracts import Command
from lecturelens_real_eval.tutor.grounded_runtime import PassageAuthority
from lecturelens_real_eval.tutor.runtime import MockTutor
from lecturelens_real_eval.tutor.store import TutorStore

RAW = C.ROOT / ".data/tutor-v12-real-20261107"
OUT = C.ROOT / ".data/tutor-v13-stage-20261107"


def read(p):
    return json.loads(p.read_text())


def lines(p):
    return [json.loads(x) for x in p.read_text().splitlines()]


def save(name, value):
    output = Path(os.environ["V13_CHECK_OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    with (output / name).open("x") as f:
        json.dump(value, f, indent=2, default=str)
        f.write("\n")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    assert os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") == "1"
    original = os.environ.get

    def get(k, *args):
        if k in {"AGENT_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"}:
            pytest.fail("Credential lookup forbidden")
        return original(k, *args)

    monkeypatch.setattr(os.environ, "get", get)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kw: pytest.fail("Real transport forbidden"))


@pytest.fixture
def isolated():
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    schema = "v13_ground_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    yield make_conninfo(dsn, options=f"-csearch_path={schema},public")
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_historical_negative_index_context_and_exact_member_fidelity():
    _, _, snapshot, _, _ = C.parent.contract.verify()
    old, new = PassageAuthority(snapshot), LessonAuthority(snapshot)
    scope = dict(owner_id=811012, course_id="source-diagnostic", revision=1)
    for a in (old, new):
        a.register(scope, "carpentries-python")
    turn = lines(RAW / "v12-original16/turns.jsonl")[0]
    query = turn["checkpoint"]["observations"][0]["query"]
    original = old.read(scope, "SEARCH", query=query)["evidence"]
    current = new.read(scope, "SEARCH", query=query)["evidence"]
    assert not any("```output\nn\ne\n```" in e["text"] for e in original)
    assert any("What is `element[-1]`?" in e["text"] and "```output\nn\ne\n```" in e["text"] for e in current)
    blocks = {e["evidence_id"]: e for e in snapshot["lectures"]["carpentries-python"]["evidence"]}
    for e in new.rows(scope):
        members = [blocks[i] for i in e["member_evidence_ids"]]
        assert e["text"] == "\n\n".join(m["text"] for m in members)
        assert e["line_start"] == members[0]["line_start"]
        assert e["line_end"] == members[-1]["line_end"]
        assert e["content_hash"] == hashlib.sha256(e["text"].encode()).hexdigest()
    save("negative-index-context.json", dict(old=original, new=current, source_only=True))


@pytest.mark.parametrize("change", ["foreign-source", "oversized", "ordinary-heading", "out-of-order"])
def test_context_boundaries(change):
    _, _, snapshot, _, _ = C.parent.contract.verify()
    rows = copy.deepcopy(
        [e for e in snapshot["lectures"]["carpentries-python"]["evidence"] if 512 <= e["line_start"] <= 522]
    )
    if change == "foreign-source":
        rows[-1]["source_path"] = "other.md"
    elif change == "oversized":
        rows[-1]["text"] = "x" * 1100
    elif change == "ordinary-heading":
        rows[2]["text"] = "## Different topic"
    else:
        rows[-1]["line_start"] = 1
    groups = lesson_passages(rows)
    assert len(groups) >= 2
    assert all(
        not ("What is `element[-1]`?" in e["text"] and "```output\nn\ne\n```" in e["text"]) for e in groups
    )


def test_raw_three_outcomes_and_fifteen_gap_audit():
    audit = read(OUT / "cause-audit.json")
    assert len(audit["coverage_cases"]) == 15
    assert sum(c["category"] == "SCORING_DUPLICATE" for c in audit["coverage_cases"]) == 1
    old = read(RAW / "codex-source-review.json")
    assert old["task_correctness"]["numerator"] == 13 and old["supported_claim_coverage"]["denominator"] == 74
    # The candidate has no semantic filter: source/citation existence is not entailment.
    assert "optional additions" in GROUNDING and "every requested part" in GROUNDING
    assert "whole-unit absence" in GROUNDING and "nearby citation" in GROUNDING


class Capture:
    def __init__(self):
        self.base, self.requests = MockTutor(), []

    def decide(self, messages, schemas, timeout):
        self.requests.append((copy.deepcopy(messages), copy.deepcopy(schemas)))
        return self.base.decide(messages, schemas, timeout)


@pytest.mark.parametrize(
    "question,socratic",
    [
        ("Explain the slice's start and stop with valid values[1:4] syntax.", False),
        ("Please guide my understanding of mutable lists.", True),
        ("The excerpt lacks a deep-copy specification; do not invent one.", False),
    ],
)
def test_pg_normal_and_guided_requests(isolated, question, socratic):
    _, _, snapshot, _, _ = C.parent.contract.verify()
    a = LessonAuthority(snapshot)
    scope = dict(owner_id=811012, course_id="v13-" + uuid.uuid4().hex, revision=1)
    a.register(scope, "carpentries-python")
    p = Capture()
    store = TutorStore(isolated)
    runtime = ClaimGroundingTutorRuntime(store, a, p)
    runtime.initialize()
    try:
        scope["session_id"] = runtime.command(Command(**scope, operation="CREATE", request_key="session"))[
            "session"
        ]["session_id"]
        result = runtime.command(
            Command(**scope, operation="TURN", client_turn_id="one", text=question, socratic=socratic)
        )
        candidate = dict(session_id=scope["session_id"], turn_id=result["turns"][-1]["turn_id"])
        runtime.execute(candidate)
        with store.connect() as conn:
            session, turn = store.rows(conn, candidate["turn_id"])
        assert turn["status"] == "completed" and turn["model_calls"] == 2
        amounts = []
        for messages, schemas in p.requests:
            assert GROUNDING in messages[0]["content"]
            assert "square brackets" in messages[0]["content"]
            body = json.loads(messages[-1]["content"])
            assert set(body) == {
                "learner_text",
                "socratic",
                "summary",
                "history",
                "evidence",
                "observations",
                "search_calls_remaining",
                "evaluation_required",
            }
            amounts.append(len(json.dumps([messages, schemas], ensure_ascii=False).encode()) + 1200)
        assert turn["reserved_tokens"] == sum(amounts) <= 64000
        assert session["reserved_tokens"] == turn["reserved_tokens"]
    finally:
        runtime.close()


def test_v12_full_retained_response_replay(isolated, tmp_path):
    oldrows = lines(RAW / "v12-original16/turns.jsonl")
    frames = []
    for r in oldrows:
        props = iter(r["proposals"])
        for call in r["calls"]:
            first = next(props)
            group = [first] + [next(props) for _ in range(first["dropped_tool_calls"])]
            frames.append(dict(turn_key=r["turn_key"], call=call, group=group))
        assert next(props, None) is None
    sent = []

    def send(request):
        n = len(sent)
        frame = frames[n]
        raw = (RAW / f"v12-original16/wire/{n + 1:03d}-request.json").read_bytes()
        assert request.content == raw
        sent.append(n + 1)
        c = frame["call"]
        return httpx.Response(
            200,
            json=dict(
                id=c["response_id"],
                model=c["returned_model"],
                system_fingerprint=c["system_fingerprint"],
                usage=c["usage"],
                choices=[
                    dict(
                        finish_reason="tool_calls",
                        message=dict(
                            tool_calls=[
                                dict(
                                    type="function",
                                    function=dict(name=p["name"], arguments=json.dumps(p["arguments"])),
                                )
                                for p in frame["group"]
                            ]
                        ),
                    )
                ],
            ),
        )

    args = C.parent.parser().parse_args(
        [
            "--mock",
            "--agent",
            "p8-tutor-repair-context-v12-development",
            "--model",
            "deepseek-flash",
            "--max-calls",
            "80",
            "--max-usd",
            "0.70",
            "--output",
            str(tmp_path / "old-control"),
        ]
    )
    result = C.parent.run(args, dsn=isolated, transport=httpx.MockTransport(send))
    replay = lines(tmp_path / "old-control/turns.jsonl")
    assert len(sent) == 42 and result["completed"] == 16
    assert [r["answer"] for r in replay] == [r["answer"] for r in oldrows]
    assert result["ledger"]["nano_usd"] == 57713400
    save(
        "v12-full-replay.json",
        dict(
            summary=result,
            exact_requests=42,
            answers_unchanged=16,
            interpretation="Retained parsed response replay, not original raw body bytes or model quality improvement",
        ),
    )


def new_transport(fault=None):
    model = MockTutor()
    first_text = C.verify()[1][0]["turns"][0]["text"]

    def send(request):
        payload = json.loads(request.content)
        body = json.loads(payload["messages"][-1]["content"])
        if fault == "auth":
            return httpx.Response(401)
        decision = model.decide(payload["messages"], payload["tools"], 20)
        if fault == "local" and body["learner_text"] == first_text and body["observations"]:
            decision = dict(name="finish_tutor_turn", arguments=dict(outcome="answered", text="X" * 1601))
        if fault == "fabricated" and body["observations"]:
            decision = dict(
                name="finish_tutor_turn", arguments=dict(outcome="answered", text="Unsupported [e999]")
            )
        if fault == "unsupported" and body["observations"]:
            eid = body["evidence"][0]["evidence_id"]
            decision = dict(
                name="finish_tutor_turn",
                arguments=dict(
                    outcome="answered",
                    text="This excerpt guarantees every application repairs all data automatically. ["
                    + eid
                    + "]",
                ),
            )
        value = dict(
            id="synthetic-id",
            model="MOCK_ONLY",
            usage=dict(
                prompt_tokens=10,
                completion_tokens=10,
                total_tokens=20,
                prompt_cache_hit_tokens=0,
                prompt_cache_miss_tokens=10,
            ),
            choices=[
                dict(
                    finish_reason="tool_calls",
                    message=dict(
                        tool_calls=[
                            dict(
                                type="function",
                                function=dict(
                                    name=decision["name"], arguments=json.dumps(decision["arguments"])
                                ),
                            )
                        ]
                    ),
                )
            ],
        )
        if fault == "usage":
            value.pop("usage")
        return httpx.Response(200, json=value)

    return httpx.MockTransport(send)


@pytest.mark.parametrize(
    "fault,cap,money,expected",
    [
        (None, 80, "0.70", (16, 0, 0, 0, 32)),
        ("local", 80, "0.70", (12, 1, 3, 0, 27)),
        ("auth", 80, "0.70", (0, 1, 0, 15, 1)),
        ("usage", 80, "0.70", (0, 1, 0, 15, 1)),
        ("fabricated", 80, "0.70", (0, 1, 0, 15, 2)),
        (None, 1, "0.70", (0, 1, 0, 15, 1)),
        (None, 80, "0.000000001", (0, 1, 0, 15, 0)),
    ],
)
def test_new_full_entry_and_failure_contract(isolated, tmp_path, fault, cap, money, expected):
    import trial_run as entry

    args = entry.parser().parse_args(
        [
            "--mock",
            "--agent",
            C.CANDIDATE,
            "--model",
            "deepseek-flash",
            "--max-calls",
            str(cap),
            "--max-usd",
            money,
            "--output",
            str(tmp_path / "new-batch"),
        ]
    )
    summary = entry.run(args, dsn=isolated, transport=new_transport(fault))
    assert (
        tuple(summary[k] for k in ("completed", "failed", "skipped", "missing", "wire_requests")) == expected
    )
    assert summary["reviewer_calls"] == 0 and summary["quality_status"] == "NOT_RUN"
    rows = lines(tmp_path / "new-batch/turns.jsonl")
    assert len(rows) == 16 and sum(summary[k] for k in ("completed", "failed", "skipped", "missing")) == 16
    if fault == "local":
        assert rows[1]["skip_code"] == "DEPENDENCY_FAILED_OR_SKIPPED"
        assert rows[2]["skip_code"] == "SESSION_CLOSED_AFTER_LOCAL_FAILURE"
        assert rows[3]["root_failure"] == rows[0]["turn_key"]
        assert all(r["status"] == "completed" for r in rows[4:])
    if expected[3]:
        assert rows[-1]["missing_code"] == "GLOBAL_STOP_BEFORE_TURN"
    events = lines(tmp_path / "new-batch/ledger.jsonl")
    with psycopg.connect(isolated) as conn:
        assert [
            e[0] for e in conn.execute("SELECT record FROM p8_tutor_real_event ORDER BY sequence")
        ] == events
    save("entry-" + str(fault) + "-" + str(cap) + "-" + money + ".json", summary)


def test_valid_id_is_not_semantic_support(isolated, tmp_path):
    import trial_run as entry

    args = entry.parser().parse_args(
        [
            "--mock",
            "--agent",
            C.CANDIDATE,
            "--model",
            "deepseek-flash",
            "--max-calls",
            "80",
            "--max-usd",
            "0.70",
            "--output",
            str(tmp_path / "semantic-negative"),
        ]
    )
    result = entry.run(args, dsn=isolated, transport=new_transport("unsupported"))
    assert result["completed"] == 16 and result["quality_status"] == "NOT_RUN"
    rows = lines(tmp_path / "semantic-negative/turns.jsonl")
    assert all("guarantees every application" in r["answer"] for r in rows)
    save(
        "semantic-negative-preserved.json",
        dict(
            mechanics=result,
            semantic_fixture_verdict="UNSUPPORTED_NOT_A_QUALITY_PASS",
            unsupported_answers_preserved=16,
        ),
    )
