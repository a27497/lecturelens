"""Independent diagnostic assertions describe current defects, not desired fixes.

Only disposable PostgreSQL schemas and explicitly injected MockTransport are used.
SQL holdout data and mixed-split authoring modules are never imported.
"""

import hashlib
import importlib
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval/tutor-v14-fresh-v1"))
import run_fresh as V14  # noqa: E402 -- installs the historical holdout fence
from lecturelens_real_eval.runner import SnapshotAuthority  # noqa: E402
from lecturelens_real_eval.tutor.claim_grounding_runtime import LessonAuthority  # noqa: E402
from lecturelens_real_eval.tutor.contracts import Command  # noqa: E402
from lecturelens_real_eval.tutor.draft_repair_runtime import DraftRepairTutorRuntime  # noqa: E402
from lecturelens_real_eval.tutor.runtime import SYSTEM, MockTutor  # noqa: E402
from lecturelens_real_eval.tutor.store import TutorStore  # noqa: E402

RUNS = {
    "v12": ("tutor-v12-real-20261107", "v12-original16", "eval/tutor-v12-rerun-v1", "rerun", 42, (16, 0, 0)),
    "v13": (
        "tutor-v13-resumed-20261107",
        "v13-new16-first",
        "eval/tutor-v13-preflight-fix-v1",
        "entry",
        34,
        (12, 1, 3),
    ),
    "v14": (
        "tutor-v14-live-20261107",
        "v14-frozen16-once",
        "eval/tutor-v14-fresh-v1",
        "run_fresh",
        32,
        (10, 2, 4),
    ),
}


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def save(name, value):
    with (Path(os.environ["TUTOR_AUDIT_OUTPUT"]) / name).open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, default=str)
        stream.write("\n")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    assert os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") == "1"
    original = os.environ.get

    def guarded(key, *args):
        if key in {"AGENT_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"}:
            pytest.fail("Credential access forbidden")
        return original(key, *args)

    monkeypatch.setattr(os.environ, "get", guarded)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kw: pytest.fail("Real HTTP forbidden"))


@pytest.fixture
def isolated():
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    schema = "zero_cost_audit_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        yield make_conninfo(dsn, options=f"-csearch_path={schema},public")
    finally:
        with psycopg.connect(dsn) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.mark.parametrize("name", list(RUNS))
def test_actual_historical_entries_exact_wire_replay(name, isolated):
    root, run, entry_path, entry_name, count, statuses = RUNS[name]
    original = ROOT / ".data" / root / run
    rows = lines(original / "turns.jsonl")
    frames = []
    for row in rows:
        proposals = iter(row.get("proposals", []))
        for call in row.get("calls", []):
            first = next(proposals)
            group = [first] + [next(proposals) for _ in range(first["dropped_tool_calls"])]
            frames.append((call, group))
        assert next(proposals, None) is None
    sent = []

    def send(request):
        index = len(sent)
        assert request.content == (original / f"wire/{index + 1:03d}-request.json").read_bytes()
        call, proposals = frames[index]
        assert hashlib.sha256(request.content).hexdigest() == call["request_sha256"]
        sent.append(index)
        return httpx.Response(
            200,
            json={
                "id": call["response_id"],
                "model": call["returned_model"],
                "system_fingerprint": call["system_fingerprint"],
                "usage": call["usage"],
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {"name": p["name"], "arguments": json.dumps(p["arguments"])},
                                }
                                for p in proposals
                            ]
                        },
                    }
                ],
            },
        )

    sys.path.insert(0, str(ROOT / entry_path))
    entry = importlib.import_module(entry_name)
    candidate = entry.contract.CANDIDATE if name != "v12" else entry.contract.candidate.CANDIDATE
    out = Path(os.environ["TUTOR_AUDIT_OUTPUT"]) / (name + "-replay")
    args = entry.parser().parse_args(
        [
            "--mock",
            "--agent",
            candidate,
            "--model",
            "deepseek-flash",
            "--max-calls",
            "80",
            "--max-usd",
            "0.70",
            "--output",
            str(out),
        ]
    )
    result = entry.run(args, dsn=isolated, transport=httpx.MockTransport(send))
    replay = lines(out / "turns.jsonl")
    assert len(sent) == count == len(frames)
    assert tuple(result[k] for k in ("completed", "failed", "skipped")) == statuses
    assert result["missing"] == 0
    for new, old in zip(replay, rows, strict=True):
        for key in (
            "turn_key",
            "status",
            "answer",
            "evaluation",
            "outcome",
            "error_code",
            "skip_code",
            "blocked_by",
            "root_failure",
            "reserved_tokens",
            "model_calls",
            "checkpoint",
        ):
            assert new.get(key) == old.get(key), (name, old["turn_key"], key)
    events = lines(out / "ledger.jsonl")
    with psycopg.connect(isolated) as conn:
        pg = [row[0] for row in conn.execute("SELECT record FROM p8_tutor_real_event ORDER BY sequence")]
    assert pg == events and len(pg) == 2 * count
    assert result["ledger"]["pending"] == 0
    save(
        name + "-replay-check.json",
        {
            "exact_wire_requests": count,
            "unchanged_turn_outcomes": 16,
            "pg_jsonl_events_equal": len(pg),
            "result": result,
            "raw_response_bytes_available": False,
            "reconstructed_envelopes": True,
            "ledger_amounts": "SIMULATED_RETAINED_USAGE_NOT_NEW_CHARGES",
        },
    )


@pytest.mark.parametrize(
    "directory",
    [
        "tutor-v12-real-20261107",
        "tutor-v13-resumed-20261107",
        "tutor-v14-offline-20261107",
        "tutor-v14-live-20261107",
        "tutor-v14-diagnosis-20261107",
    ],
)
def test_historical_manifest_unchanged(directory):
    root = ROOT / ".data" / directory
    manifest = read(root / "artifact-manifest.json")
    for path, expected in manifest["files"].items():
        target = (root / path).resolve()
        assert target.is_relative_to(root.resolve())
        assert not any(term in path.lower() for term in ("credential", "secret", ".env", "api-key"))
        assert hashlib.sha256(target.read_bytes()).hexdigest() == expected, path
    save(directory + "-integrity.json", {"verified_files": len(manifest["files"]), "all_equal": True})


@pytest.mark.parametrize("name", list(RUNS))
def test_every_historical_wire_context_is_source_only_and_session_local(name):
    root, run, *_ = RUNS[name]
    original = ROOT / ".data" / root / run
    rows = lines(original / "turns.jsonl")
    sequence = 0
    for row in rows:
        for call in row.get("calls", []):
            sequence += 1
            wire = read(original / f"wire/{sequence:03d}-request.json")
            assert (
                hashlib.sha256((original / f"wire/{sequence:03d}-request.json").read_bytes()).hexdigest()
                == call["request_sha256"]
            )
            assert wire["max_tokens"] == 1200 and wire["temperature"] == 0
            assert wire["thinking"] == {"type": "disabled"}
            assert wire["parallel_tool_calls"] is False
            body = json.loads(wire["messages"][-1]["content"])
            assert not set(body) & {
                "reference",
                "reference_points",
                "expected_topic",
                "expected_insufficient",
                "rubric",
            }
            prior = [
                r
                for r in rows
                if r["dialogue_id"] == row["dialogue_id"]
                and r["ordinal"] < row["ordinal"]
                and r["status"] == "completed"
            ][-6:]
            assert body["history"] == [
                {k: r[k] for k in ("ordinal", "learner_text", "answer", "evaluation", "outcome")}
                for r in prior
            ]
    save(
        name + "-context-check.json",
        {"wires_checked": sequence, "actual_history_only": True, "reference_metadata_absent": True},
    )


def make_runtime(dsn, provider, *, runtime_class=DraftRepairTutorRuntime):
    snapshot = read(ROOT / "eval/tutor-v14-fresh-v1/snapshot.json")
    authority = LessonAuthority(snapshot)
    scope = {"owner_id": 811012, "course_id": "audit-" + uuid.uuid4().hex, "revision": 1}
    authority.register(scope, "carpentries-python")
    store = TutorStore(dsn)
    runtime = runtime_class(store, authority, provider)
    runtime.initialize()
    scope["session_id"] = runtime.command(Command(**scope, operation="CREATE", request_key="s"))["session"][
        "session_id"
    ]
    return store, runtime, scope


def submit(store, runtime, scope, text="Explain the loop", key="t1", **kwargs):
    view = runtime.command(Command(**scope, operation="TURN", client_turn_id=key, text=text, **kwargs))
    candidate = {"session_id": scope["session_id"], "turn_id": view["turns"][-1]["turn_id"]}
    runtime.execute(candidate)
    return runtime.command(Command(**scope, operation="GET"))["turns"][-1]


def test_unsupported_answer_and_uncited_evaluation_publish_with_valid_identity(isolated):
    class Provider:
        def decide(self, messages, schemas, timeout):
            body = json.loads(messages[-1]["content"])
            if not body["observations"]:
                return {"name": "search_tutor_evidence", "arguments": {"query": "loop"}}
            eid = body["evidence"][0]["evidence_id"]
            return {
                "name": "finish_tutor_turn",
                "arguments": {
                    "outcome": "answered",
                    "text": "The unit proves every loop cures influenza. [" + eid + "]",
                    "evaluation": "You have permanently mastered all programming; your answer is correct.",
                },
            }

    store, runtime, scope = make_runtime(isolated, Provider())
    try:
        result = submit(store, runtime, scope)
        assert result["status"] == "completed" and "cures influenza" in result["answer"]
        assert result["evaluation"] and len(result["citations"]) == 1
        assert "influenza" not in result["citations"][0]["text"]
        save("unsupported-publication.json", result)
    finally:
        runtime.close()


def test_socratic_full_solution_with_question_mark_is_publishable(isolated):
    class Provider:
        def decide(self, messages, schemas, timeout):
            body = json.loads(messages[-1]["content"])
            if not body["observations"]:
                return {"name": "search_tutor_evidence", "arguments": {"query": "polynomial coefs enumerate"}}
            eid = body["evidence"][0]["evidence_id"]
            return {
                "name": "finish_tutor_turn",
                "arguments": {
                    "outcome": "socratic_prompt",
                    "text": "The complete solution is y=0; for idx, coef in enumerate(coefs): y += coef * x**idx; the result is 97. Understood? ["
                    + eid
                    + "]",
                },
            }

    store, runtime, scope = make_runtime(isolated, Provider())
    try:
        result = submit(store, runtime, scope, socratic=True)
        assert result["status"] == "completed" and result["outcome"] == "socratic_prompt"
        save("socratic-surface-only.json", result)
    finally:
        runtime.close()


def test_long_history_drops_corrections_from_evaluation(isolated):
    store, runtime, scope = make_runtime(isolated, None)
    try:
        for n in range(1, 9):
            runtime.command(Command(**scope, operation="TURN", client_turn_id=f"t{n}", text=f"learner {n}"))
            with store.connect() as conn:
                conn.execute(
                    "UPDATE tutor_turn SET status='completed',outcome='answered',answer=%s,evaluation=%s WHERE session_id=%s AND ordinal=%s",
                    (
                        "x" * 250 + " IMPORTANT_TAIL_CORRECTION",
                        "EVALUATION_ONLY_CORRECTION",
                        scope["session_id"],
                        n,
                    ),
                )
        runtime.command(
            Command(**scope, operation="TURN", client_turn_id="t9", text="Remember the first correction?")
        )
        with store.connect() as conn:
            session, turn = store.rows(conn, store.candidates()[0]["turn_id"])
            history = runtime.context(conn, session, turn)
            messages, _, _ = runtime.request(session, turn, turn["checkpoint"], history)
        body = json.loads(messages[-1]["content"])
        assert [p["ordinal"] for p in history] == [3, 4, 5, 6, 7, 8]
        assert "EVALUATION_ONLY_CORRECTION" not in body["summary"]
        assert "IMPORTANT_TAIL_CORRECTION" not in body["summary"]
        save(
            "long-context-loss.json",
            {
                "older_ordinals": [1, 2],
                "history_ordinals": [3, 4, 5, 6, 7, 8],
                "summary": body["summary"],
                "evaluation_and_tail_lost": True,
            },
        )
    finally:
        runtime.close()


def test_cancelled_call_loses_turn_usage_but_keeps_reservation(isolated):
    class Provider:
        def decide(self, messages, schemas, timeout):
            runtime.command(Command(**scope, operation="CANCEL", client_turn_id="t1"))
            return {
                "name": "search_tutor_evidence",
                "arguments": {"query": "loop"},
                "usage": {"prompt_tokens": 123, "completion_tokens": 45},
            }

    store, runtime, scope = make_runtime(isolated, Provider())
    try:
        result = submit(store, runtime, scope)
        assert result["status"] == "cancelled" and result["usage"] == []
        assert result["model_calls"] == 1 and result["reserved_tokens"] > 0
        save("cancelled-usage-loss.json", result)
    finally:
        runtime.close()


@pytest.mark.parametrize("query", ["糖尿病中文课程", "?", "zzzzzzzzzzzzunmatched"])
def test_zero_overlap_search_still_returns_eight_sources(query):
    snapshot = read(ROOT / "eval/tutor-v14-fresh-v1/snapshot.json")
    authority = SnapshotAuthority(snapshot)
    scope = {"owner_id": 811012, "course_id": "audit-search", "revision": 1}
    authority.register(scope, "carpentries-python")
    result = authority.read(scope, "SEARCH", query=query)["evidence"]
    assert len(result) == 8
    assert [e["evidence_id"] for e in result] == [e["evidence_id"] for e in authority.rows(scope)[:8]]


def test_current_frozen_entry_and_question_solution_projection():
    plan, scripts, snapshot, expected, protocol = V14.contract.verify()
    derived = LessonAuthority(snapshot).snapshot
    checks = []
    for lecture in derived["lectures"].values():
        for evidence in lecture["evidence"]:
            assert hashlib.sha256(evidence["text"].encode()).hexdigest() == evidence["content_hash"]
            assert len(evidence["member_evidence_ids"]) == len(evidence["member_locations"])
            checks.append(evidence["evidence_id"])
    assert len(checks) == len(set(checks))
    assert len(expected) == 16 and len(scripts) == 4
    save(
        "current-freeze-check.json",
        {
            "candidate": plan["candidate"],
            "projected_sources": len(checks),
            "expected": 16,
            "protocol": protocol["version"],
        },
    )


def test_reference_requires_extra_specific_example_not_named_in_question():
    questions = read(ROOT / "eval/tutor-v14-fresh-v1/questions.json")
    task = next(d for d in questions["dialogues"] if d["dialogue_id"] == "v14-sheets-lineends")["turns"][1]
    assert "Excel reopening" in task["reference_points"][1]
    assert "Excel" not in task["text"] and "reopen" not in task["text"]
    raw = ROOT / ".data/tutor-v14-live-20261107/v14-frozen16-once"
    row = next(r for r in lines(raw / "turns.jsonl") if r["turn_key"] == "v14-sheets-lineends:2")
    body = json.loads(read(raw / "wire/029-request.json")["messages"][-1]["content"])
    assert any("When opening your CSV file in Excel again" in e["text"] for e in body["evidence"])
    assert len(row["answer"]) == 1285 and "reopen" not in row["answer"].lower()
    save(
        "question-reference-gap.json",
        {
            "question": task["text"],
            "frozen_reference": task["reference_points"],
            "source_present": True,
            "answer_chars": 1285,
            "strict_historical_score_changed": False,
        },
    )


@pytest.mark.parametrize(
    "name,expected", [("v12", (84, 74, 62, 59)), ("v13", (45, 37, 38, 37)), ("v14", (47, 42, 36, 36))]
)
def test_original_annotation_anchors_sources_and_denominators(name, expected):
    directory, run, *_ = RUNS[name]
    raw = ROOT / ".data" / directory
    rows = {r["turn_key"]: r for r in lines(raw / run / "turns.jsonl")}
    review = read(raw / "codex-source-review.json")
    totals = [0, 0, 0, 0]
    quotes_checked = 0
    source_root = (
        ROOT
        / {
            "v12": "eval/tutor-public-v1/materials",
            "v13": "eval/tutor-v13-grounding-v1/materials",
            "v14": "eval/tutor-v14-fresh-v1/materials",
        }[name]
    )
    for key, label in review["labels"].items():
        row = rows[key]
        for claim in label.get("claims", []):
            totals[0] += 1
            totals[1] += claim["requires_citation"]
            start, end = claim["answer_offsets"]
            assert row["answer"][start:end] == claim["text"]
            course = "python" if "python" in key else "spreadsheets"
            suffix = "" if name == "v12" else "-new"
            source = (source_root / f"carpentries-{course}{suffix}.md").read_text()
            for quote in claim.get("source_quotes", []):
                assert quote["quote"] in source
                quotes_checked += 1
        for pair in label.get("citation_checks", []):
            totals[2] += 1
            totals[3] += pair["label"] == "supported"
            assert any(
                e["evidence_id"] == pair["evidence_id"] and e["text"] == pair["observed_quote"]
                for e in row["citations"]
            )
        if row["status"] != "completed":
            assert label.get("task_correct") is not True
    assert tuple(totals) == expected
    completed = sum(r["status"] == "completed" for r in rows.values())
    correct = sum(label.get("task_correct") is True for label in review["labels"].values())
    assert (correct, completed) == {"v12": (13, 16), "v13": (11, 12), "v14": (9, 10)}[name]
    calls = lines(raw / run / "calls.jsonl")
    events = lines(raw / run / "ledger.jsonl")
    latest = {event["call_id"]: event for event in events}
    reservations = {event["call_id"]: event for event in events if event["state"] == "reserved"}
    for call in calls:
        reservation, settled = reservations[call["ledger_call_id"]], latest[call["ledger_call_id"]]
        assert call["request_sha256"] == reservation["wire_sha256"]
        assert settled["state"] == "settled"
        assert all(settled["usage"][k] == call["usage"][k] for k in ("prompt_tokens", "completion_tokens"))
        assert (
            settled["charged_nano_usd"]
            == call["usage"]["prompt_tokens"] * 300 + call["usage"]["completion_tokens"] * 1200
        )
    historical_charge = sum(e["charged_nano_usd"] for e in latest.values())
    assert historical_charge == {"v12": 57713400, "v13": 45606300, "v14": 46152000}[name]
    save(
        name + "-annotation-check.json",
        {
            "assertions": totals[0],
            "citation_requiring": totals[1],
            "pairs": totals[2],
            "supported_pairs": totals[3],
            "correct": correct,
            "scheduled": 16,
            "completed": completed,
            "literal_source_quotes_checked": quotes_checked,
            "historical_ledger_nano_usd": historical_charge,
            "historical_calls_reconciled": len(calls),
            "semantic_rejudgment": "NONBLIND_AUDIT_NOT_INDEPENDENT_HUMAN",
        },
    )


def test_supplied_source_integer_claim_is_not_a_python_runtime_fact():
    source = (ROOT / "eval/tutor-v14-fresh-v1/materials/carpentries-spreadsheets-new.md").read_text()
    assert "`2\\r` is not a valid integer" in source
    assert int("2\r") == 2
    save(
        "source-truth-limitation.json",
        {
            "source_claim": "2\\r is not a valid integer",
            "local_python_int": 2,
            "scope": "Python int conversion only; R and external importers NOT_CHECKED",
            "historical_attributed_source_rubric_changed": False,
        },
    )


def test_default_mock_corrupts_python_indexing():
    source = "The first value is obtained with values[0]."
    body = {
        "observations": [{"tool": "search_tutor_evidence"}],
        "history": [],
        "summary": "",
        "learner_text": "Give the first-value expression",
        "socratic": False,
        "evidence": [{"evidence_id": "e1", "text": source}],
    }
    result = MockTutor().decide([{"role": "user", "content": json.dumps(body)}], [], 20)
    assert result["arguments"]["text"] == "The first value is obtained with values(0). [e1]"
    assert "use parentheses for math/indexing" in SYSTEM
    save(
        "default-syntax-loss.json",
        {
            "source": source,
            "actual_mock_answer": result["arguments"]["text"],
            "default_prompt_conflict": True,
        },
    )
