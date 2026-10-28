"""Every paid path uses injected httpx transport; external sockets are forbidden."""

import hashlib
import json
import os
import socket
import traceback
import uuid
from dataclasses import replace

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from lecturelens_agent.study.acceptance_cost import CostDenied, CostPolicy, verify_development_agent
from lecturelens_real_eval.channel import Channel, EvalChatProvider, EvalError, Ledger, RealPolicy, encode
from lecturelens_real_eval.runner import (
    DATA,
    GraphAdapter,
    SnapshotAuthority,
    fake_transport,
    review_cards,
    run_evaluation,
    summarize,
    verify_inputs,
)

SCHEMAS = [{"type": "function", "function": {"name": "search_card_evidence", "parameters": {}}}]
MESSAGES = [{"role": "user", "content": "test"}]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original = socket.socket.connect

    def local(sock, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
            raise AssertionError("No external sockets in P7 tests")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", local)
    monkeypatch.delenv("LECTURELENS_REAL_EVAL", raising=False)
    monkeypatch.delenv("AGENT_LLM_API_KEY", raising=False)


@pytest.fixture
def isolated(tmp_path):
    dsn = make_conninfo(os.environ["AGENT_TEST_DATABASE_URL"], dbname="lecturelens_agent_acceptance")
    schema = "p7_real_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    scoped = make_conninfo(dsn, options=f"-csearch_path={schema},public")
    yield scoped, tmp_path / "ledger.jsonl"
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def ledger(isolated, policy=None):
    dsn, path = isolated
    result = Ledger(dsn, path, "test-" + uuid.uuid4().hex, policy or RealPolicy())
    result.install()
    return result


def response(usage=None, *, name="search_card_evidence", arguments=None):
    return httpx.Response(
        200,
        json={
            "usage": usage or {"prompt_tokens": 100, "completion_tokens": 100},
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(arguments or {"query": "test"}),
                                },
                            }
                        ]
                    },
                }
            ],
        },
    )


def test_live_requires_both_switches(monkeypatch):
    with pytest.raises(EvalError, match="SWITCH_REQUIRED"):
        RealPolicy(live=True).validate()
    monkeypatch.setenv("LECTURELENS_REAL_EVAL", "1")
    RealPolicy(live=True).validate()
    assert not RealPolicy().live
    # Environment alone cannot choose the network transport.
    with pytest.raises(EvalError, match="FAKE_TRANSPORT_REQUIRED"):
        Channel(type("L", (), {"policy": RealPolicy()})())


@pytest.mark.parametrize(
    "change",
    [
        {"host": "localhost"},
        {"host": "203.0.113.1"},
        {"hostaddr": "203.0.113.1"},
        {"dbname": "lecturelens_agent_test"},
        {"dbname": "production"},
        {"port": "19999"},
        {"port": "32768"},
        {"service": "untrusted"},
    ],
)
def test_nonisolated_dsn_refused_without_connecting(tmp_path, change):
    dsn = make_conninfo(host="127.0.0.1", port="25711", dbname="lecturelens_agent_acceptance")
    with pytest.raises(EvalError, match="ISOLATED_DATABASE"):
        Ledger(make_conninfo(dsn, **change), tmp_path / "never-created", "x", RealPolicy())
    assert not (tmp_path / "never-created").exists()


@pytest.mark.parametrize(
    "change",
    [
        {"allowed_route": "http://127.0.0.1:25711"},
        {"allowed_route": "https://api.deepseek.com.evil"},
        {"allowed_route": "https://api.deepseek.com/v1"},
        {"model": "deepseek-chat"},
        {"thinking": "enabled"},
        {"max_tokens": 1201},
        {"max_calls": 121},
        {"max_nano_usd": 1_000_000_001},
        {"max_nano_usd": 0},
    ],
)
def test_policy_envelope_cannot_expand(change):
    with pytest.raises(EvalError, match="POLICY_INVALID"):
        replace(RealPolicy(), **change).validate()


def test_prepaid_both_ledgers_visible_before_dispatch_and_append_only(isolated):
    account = ledger(isolated)
    original = account.path.read_bytes()
    seen = []

    def send(request):
        state = account.check()
        assert state["calls"] == state["pending"] == 1
        row = json.loads(account.path.read_text().splitlines()[-1])
        assert row["state"] == "reserved"
        with account.connect() as conn:
            assert (
                conn.execute(
                    "SELECT record FROM p7_real_event WHERE run_id=%s", (account.run_id,)
                ).fetchone()["record"]
                == row
            )
        seen.append(request)
        return response()

    Channel(account, transport=httpx.MockTransport(send)).request(MESSAGES, SCHEMAS)
    rows = [json.loads(line) for line in account.path.read_text().splitlines()]
    assert account.path.read_bytes().startswith(original)
    assert len(seen) == 1 and len(rows) == 2
    assert rows[0]["call_id"] == rows[1]["call_id"]
    assert rows[0]["reserved_nano_usd"] == len(seen[0].content) * 300 + 1200 * 1200
    assert account.check() == {"calls": 1, "nano_usd": 150000, "pending": 0, "blocked": None}


def test_120_calls_is_a_persistent_hard_limit(isolated):
    account = ledger(isolated)
    sent = []
    channel = Channel(account, transport=httpx.MockTransport(lambda request: sent.append(1) or response()))
    for _ in range(120):
        channel.request(MESSAGES, SCHEMAS)
    with pytest.raises(EvalError, match="BUDGET_EXHAUSTED"):
        channel.request(MESSAGES, SCHEMAS)
    assert len(sent) == 120 and account.check()["calls"] == 120
    recovered = Ledger(account.dsn, account.path, account.run_id, account.policy)
    with pytest.raises(EvalError, match="ALREADY_EXISTS"):
        recovered.install()
    assert recovered.check()["blocked"]


def test_one_dollar_ceiling_refuses_before_send_and_stops_round(isolated):
    account = ledger(isolated)
    raw = b"x" * 65000
    for _ in range(47):
        reserved = account.reserve(raw, 1200)
        account.settle(reserved, error="REAL_EVAL_REQUEST_FAILED")
    with pytest.raises(EvalError, match="BUDGET_EXHAUSTED"):
        account.reserve(raw, 1200)
    assert account.check()["nano_usd"] <= 1_000_000_000
    assert account.check()["calls"] == 47
    with pytest.raises(EvalError, match="RUN_STOPPED"):
        account.reserve(b"x", 1)


def test_actual_usage_above_reservation_is_accounted_and_stops_round(isolated):
    account = ledger(isolated)
    channel = Channel(
        account,
        transport=httpx.MockTransport(
            lambda _: response({"prompt_tokens": 10_000_000, "completion_tokens": 100})
        ),
    )
    with pytest.raises(EvalError, match="USAGE_EXCEEDED"):
        channel.request(MESSAGES, SCHEMAS)
    assert account.check()["nano_usd"] == 3_000_120_000
    with pytest.raises(EvalError, match="RUN_STOPPED"):
        channel.request(MESSAGES, SCHEMAS)
    assert account.check()["calls"] == 1


@pytest.mark.parametrize("kind", ["http", "timeout", "parse", "missing_usage", "truncated", "wrong_tool"])
def test_failures_are_charged_full_reservation_without_retry(isolated, kind):
    account, sent = ledger(isolated), []

    def send(request):
        sent.append(1)
        if kind == "http":
            return httpx.Response(503, text="untrusted provider details")
        if kind == "timeout":
            raise httpx.ReadTimeout("untrusted provider details")
        if kind == "parse":
            return httpx.Response(200, text="not json")
        data = json.loads(response().content)
        if kind == "missing_usage":
            del data["usage"]
        elif kind == "truncated":
            data["choices"][0]["finish_reason"] = "length"
        else:
            data["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = "evil"
        return httpx.Response(200, json=data)

    with pytest.raises(EvalError, match="REQUEST_FAILED"):
        Channel(account, transport=httpx.MockTransport(send)).request(MESSAGES, SCHEMAS)
    rows = [json.loads(line) for line in account.path.read_text().splitlines()]
    assert len(sent) == 1
    assert rows[-1]["charged_nano_usd"] == rows[0]["reserved_nano_usd"]
    assert rows[-1]["state"] == "failed"


def test_live_schema_failure_never_enters_chatprovider_repair(isolated, monkeypatch):
    monkeypatch.setenv("LECTURELENS_REAL_EVAL", "1")
    monkeypatch.setenv("AGENT_LLM_API_KEY", "synthetic-p7-key-do-not-log")
    account, sent = ledger(isolated, RealPolicy(live=True)), []
    provider = EvalChatProvider(
        Channel(
            account,
            transport=httpx.MockTransport(lambda _: sent.append(1) or response(arguments={"bad": "schema"})),
        ),
        validate=lambda r: (_ for _ in ()).throw(ValueError("secret-output")),
    )
    with pytest.raises(EvalError, match="PROTOCOL_FAILURE"):
        provider.flashcards(MESSAGES, SCHEMAS, 20)
    with pytest.raises(EvalError, match="FLASHCARDS_ONLY"):
        provider.decide(MESSAGES, 20)
    assert len(sent) == account.check()["calls"] == 1
    rows = [json.loads(line) for line in account.path.read_text().splitlines()]
    assert rows[-1]["charged_nano_usd"] == rows[0]["reserved_nano_usd"]


@pytest.mark.parametrize("echo", ["exception", "response", "escaped_arguments"])
def test_key_never_in_exception_logs_or_ledgers(isolated, monkeypatch, caplog, capsys, echo):
    key = "synthetic-p7-key-never-persist-abc987"
    monkeypatch.setenv("LECTURELENS_REAL_EVAL", "1")
    monkeypatch.setenv("AGENT_LLM_API_KEY", key)
    account = ledger(isolated, RealPolicy(live=True))

    def send(request):
        assert request.headers["Authorization"] == "Bearer " + key
        if echo == "exception":
            raise httpx.ReadError(key)
        if echo == "escaped_arguments":
            data = json.loads(response().content)
            escaped = "".join("\\u%04x" % ord(c) for c in key)
            data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = (
                '{"query":"' + escaped + '"}'
            )
            return httpx.Response(200, json=data)
        return httpx.Response(200, text=key)

    with pytest.raises(EvalError) as caught:
        Channel(account, transport=httpx.MockTransport(send)).request(MESSAGES, SCHEMAS)
    assert caught.value.__context__ is None
    formatted = "".join(traceback.format_exception(caught.value))
    with account.connect() as conn:
        pg = str(conn.execute("SELECT record FROM p7_real_event").fetchall())
    captured = capsys.readouterr()
    assert key not in formatted + caplog.text + captured.out + captured.err + account.path.read_text() + pg


def test_body_limit_and_fake_mode_never_reads_credential(isolated, monkeypatch):
    account = ledger(isolated)
    channel = Channel(account, transport=fake_transport())
    with pytest.raises(EvalError, match="BODY_LIMIT"):
        channel.request([{"role": "user", "content": "x" * 65536}], SCHEMAS)
    assert account.check()["calls"] == 0
    original = os.environ.get

    def read(name, *args):
        assert name != "AGENT_LLM_API_KEY"
        return original(name, *args)

    monkeypatch.setattr(os.environ, "get", read)
    Channel(account, transport=httpx.MockTransport(lambda _: response())).request(MESSAGES, SCHEMAS)


def test_ledger_divergence_blocks_send_and_never_rewrites_file(isolated):
    account = ledger(isolated)
    account.path.write_bytes(encode({"run_id": account.run_id, "state": "forged"}) + b"\n")
    before = account.path.read_bytes()
    with pytest.raises(EvalError, match="LEDGER_MISMATCH"):
        Channel(account, transport=httpx.MockTransport(lambda _: pytest.fail("must not send"))).request(
            MESSAGES, SCHEMAS
        )
    assert account.path.read_bytes() == before


def test_unknown_reserved_outcome_cannot_be_replayed(isolated):
    account = ledger(isolated)
    account.reserve(b"x", 100)
    with pytest.raises(EvalError, match="UNKNOWN_OUTCOME"):
        account.reserve(b"x", 100)
    assert account.check()["pending"] == 1


def test_authority_is_read_only_lecture_scoped_and_uses_no_labels():
    _, snapshot, _ = verify_inputs()
    authority = SnapshotAuthority(snapshot)
    scope = {"owner_id": 1, "course_id": "a", "revision": 1}
    authority.register(scope, "algorithms-l1")
    with pytest.raises(EvalError, match="AUTHORITY_SCOPE"):
        authority.read({**scope, "owner_id": 2})
    with pytest.raises(EvalError, match="CITATION_FABRICATED"):
        authority.read(scope, "READ", evidence_ids=["v2-algorithms-l2-p01-e00"])
    with pytest.raises(EvalError, match="READ_ONLY"):
        authority.read(scope, "WRITE")


def test_frozen_data_24_tasks_eight_lectures_three_courses():
    tasks, snapshot, _ = verify_inputs()
    assert len(tasks) == 24 and len({t["lecture_id"] for t in tasks}) == 8
    assert len({d["course"] for d in snapshot["lectures"].values()}) >= 3
    assert sum(t["expected_stop"] for t in tasks) == 2
    for lecture in snapshot["lectures"].values():
        for e in lecture["evidence"]:
            assert hashlib.sha256(e["text"].encode()).hexdigest() == e["content_hash"]


def test_review_is_independent_and_unclear_counts_as_failure(isolated):
    account = ledger(isolated)
    observed = []

    def send(request):
        data = json.loads(request.content)
        observed.append(data)
        return response(
            name="review_card_sources", arguments={"checks": [{"index": 0, "verdict": "unclear"}]}
        )

    card = {"front": "a", "back": "b", "citations": [{"evidence_id": "e", "text": "source"}]}
    review = review_cards(Channel(account, transport=httpx.MockTransport(send)), [card])
    assert "goal" not in json.loads(observed[0]["messages"][-1]["content"])
    thresholds = json.loads((DATA / "thresholds.json").read_text())
    row = {"task": {"expected_stop": False}, "cards": [card], "latency_s": 1, "protocol_failure": False}
    result = summarize([row], [review], account.check(), thresholds, None, False)
    assert result["values"]["source_supported_rate"] == 0
    assert result["verdict"] == "PARTIAL"


def test_generation_cannot_make_fourth_call(isolated):
    account = ledger(isolated)
    adapter = GraphAdapter(Channel(account, transport=fake_transport()), None)
    adapter.task_calls = 3
    with pytest.raises(EvalError, match="GENERATION_CALL_LIMIT"):
        adapter.flashcards([], [], 20)
    assert account.check()["calls"] == 0


def test_mock_end_to_end_24_tasks_summary_and_reproducible_sample(isolated, tmp_path):
    dsn, path = isolated
    result = run_evaluation(dsn, path, "mock-e2e", RealPolicy(), output_root=tmp_path / "results")
    directory = tmp_path / "results/mock-e2e"
    assert result["verdict"] == "PASS", result
    assert result["quality_status"] == "NOT_RUN_MOCK_MECHANICS_ONLY"
    assert result["completed_tasks"] == 24 and result["calls"] == 72
    assert len((directory / "generations.jsonl").read_text().splitlines()) == 24
    assert len((directory / "reviews.jsonl").read_text().splitlines()) == 24
    assert (directory / "sample.md").read_text().count("## ") == 10
    assert result["values"]["correct_stop_rate"] == 1.0


def test_nonexistent_citation_stops_entire_round_fail(isolated, tmp_path):
    dsn, path = isolated
    fake = fake_transport()
    calls = []

    def send(request):
        calls.append(1)
        if len(calls) == 2:
            return response(
                name="create_evidence_cards",
                arguments={"cards": [{"front": "x", "back": "y", "evidence_ids": ["does-not-exist"]}]},
            )
        return fake.handle_request(request)

    result = run_evaluation(
        dsn,
        path,
        "citation-fail",
        RealPolicy(),
        transport=httpx.MockTransport(send),
        output_root=tmp_path / "results",
    )
    assert result["verdict"] == "FAIL" and result["fatal"] == "REAL_EVAL_CITATION_FABRICATED"
    assert result["completed_tasks"] == 1 and len(calls) == result["calls"] == 2
    assert result["card_count"] == 0


def test_prior_offline_frozen_gate_unchanged():
    from datetime import datetime, timedelta, timezone

    assert verify_development_agent() == 63
    now = datetime.now(timezone.utc)
    policy = CostPolicy("offline", now.isoformat(), (now + timedelta(hours=1)).isoformat())
    policy.validate()
    with pytest.raises(CostDenied):
        replace(policy, mode="live").validate()


def test_partial_jsonl_tail_and_pg_only_events_fail_closed(isolated):
    account = ledger(isolated)
    account.path.write_bytes(encode({"run_id": "other-run"}))
    with pytest.raises(EvalError, match="LEDGER_MISMATCH"):
        account.check()
    account.path.write_bytes(b"")
    with account.connect() as conn:
        from psycopg.types.json import Jsonb

        conn.execute(
            "INSERT INTO p7_real_event VALUES (%s,1,%s)", (account.run_id, Jsonb({"run_id": account.run_id}))
        )
    with pytest.raises(EvalError, match="LEDGER_MISMATCH"):
        account.check()


def test_ledger_policy_cannot_be_changed_to_replenish_budget(isolated):
    account = ledger(isolated)
    different = Ledger(account.dsn, account.path, account.run_id, replace(account.policy, max_calls=119))
    with pytest.raises(EvalError, match="POLICY_MISMATCH"):
        different.check()


def test_schema_failure_preserves_usage_and_failed_proposal(isolated):
    account = ledger(isolated)
    _, snapshot, _ = verify_inputs()
    authority = SnapshotAuthority(snapshot)
    scope = {"owner_id": 1, "course_id": "test", "revision": 1}
    authority.register(scope, "algorithms-l1")
    adapter = GraphAdapter(
        Channel(account, transport=httpx.MockTransport(lambda _: response(arguments={"extra": "invalid"}))),
        authority,
    )
    adapter.start(scope)
    with pytest.raises(EvalError, match="PROTOCOL_FAILURE"):
        adapter.flashcards([{"role": "user", "content": json.dumps({"evidence": []})}], SCHEMAS, 20)
    assert adapter.proposals[0]["arguments"] == {"extra": "invalid"}
    assert account.check()["calls"] == 1


def test_invalid_review_indices_are_charged_without_reask(isolated):
    account, sent = ledger(isolated), []
    channel = Channel(
        account,
        transport=httpx.MockTransport(
            lambda _: sent.append(1) or response(name="review_card_sources", arguments={"checks": []})
        ),
    )
    card = {"front": "f", "back": "b", "citations": [{"evidence_id": "e", "text": "text"}]}
    with pytest.raises(EvalError, match="PROTOCOL_FAILURE"):
        review_cards(channel, [card])
    assert len(sent) == account.check()["calls"] == 1


def test_cli_live_missing_switch_refuses_before_pg_or_transport(monkeypatch, capsys):
    import sys

    from lecturelens_real_eval.runner import main

    monkeypatch.setattr(sys, "argv", ["run.py", "--live", "--dsn", "not-a-dsn"])
    assert main() == 1
    assert "PREFLIGHT_FAILED" in capsys.readouterr().out


def test_http_error_stops_round_with_failure_artifacts(isolated, tmp_path):
    dsn, path = isolated
    sent = []
    result = run_evaluation(
        dsn,
        path,
        "http-fail",
        RealPolicy(),
        transport=httpx.MockTransport(lambda _: sent.append(1) or httpx.Response(503)),
        output_root=tmp_path / "results",
    )
    assert result["verdict"] == "FAIL" and result["completed_tasks"] == 1
    assert result["calls"] == len(sent) == 1
    directory = tmp_path / "results/http-fail"
    assert all(
        (directory / name).exists()
        for name in ["summary.json", "sample.md", "generations.jsonl", "reviews.jsonl"]
    )


def test_wrong_lecture_citation_in_malformed_proposal_stops_round(isolated):
    account = ledger(isolated)
    _, snapshot, _ = verify_inputs()
    authority = SnapshotAuthority(snapshot)
    scope = {"owner_id": 1, "course_id": "x", "revision": 1}
    authority.register(scope, "algorithms-l1")
    proposal = {"cards": [None, {"front": "x", "evidence_ids": ["v2-algorithms-l2-p01-e00"]}]}
    adapter = GraphAdapter(
        Channel(
            account,
            transport=httpx.MockTransport(
                lambda _: response(name="create_evidence_cards", arguments=proposal)
            ),
        ),
        authority,
    )
    adapter.start(scope)
    schemas = [{"type": "function", "function": {"name": "create_evidence_cards", "parameters": {}}}]
    with pytest.raises(EvalError):
        adapter.flashcards([{"role": "user", "content": json.dumps({"evidence": []})}], schemas, 20)
    assert account.check()["blocked"] == "REAL_EVAL_CITATION_FABRICATED"


@pytest.mark.parametrize("failure", ["unobserved", "blank"])
def test_card_admission_failures_charge_full_reservation(isolated, failure):
    account = ledger(isolated)
    _, snapshot, _ = verify_inputs()
    authority = SnapshotAuthority(snapshot)
    scope = {"owner_id": 1, "course_id": "test", "revision": 1}
    authority.register(scope, "algorithms-l1")
    card = {
        "front": " " if failure == "blank" else "front",
        "back": "back",
        "evidence_ids": ["v2-algorithms-l1-p01-e00"],
    }
    adapter = GraphAdapter(
        Channel(
            account,
            transport=httpx.MockTransport(
                lambda _: response(name="create_evidence_cards", arguments={"cards": [card]})
            ),
        ),
        authority,
    )
    adapter.start(scope)
    messages = [
        {
            "role": "user",
            "content": json.dumps(
                {"evidence": [{"evidence_id": card["evidence_ids"][0]}] if failure == "blank" else []}
            ),
        }
    ]
    schemas = [{"type": "function", "function": {"name": "create_evidence_cards", "parameters": {}}}]
    with pytest.raises(EvalError, match="PROTOCOL_FAILURE"):
        adapter.flashcards(messages, schemas, 20)
    rows = [json.loads(line) for line in account.path.read_text().splitlines()]
    assert rows[-1]["charged_nano_usd"] == rows[0]["reserved_nano_usd"]
    assert not account.check()["blocked"]


def _parallel(second_name):
    data = json.loads(response().content)
    calls = data["choices"][0]["message"]["tool_calls"]
    extra = json.loads(json.dumps(calls[0]))
    extra["id"] = "call-parallel-2"
    extra["function"]["name"] = second_name
    calls.append(extra)
    return httpx.Response(200, json=data)


def test_parallel_tool_calls_execute_first_only_without_extra_request(isolated, monkeypatch):
    monkeypatch.setenv("LECTURELENS_REAL_EVAL", "1")
    monkeypatch.setenv("AGENT_LLM_API_KEY", "synthetic-p7-key-do-not-log")
    account, sent = ledger(isolated, RealPolicy(live=True)), []
    first = json.loads(response().content)["choices"][0]["message"]["tool_calls"][0]["function"]
    channel = Channel(
        account,
        transport=httpx.MockTransport(lambda _: sent.append(1) or _parallel(first["name"])),
    )
    result = channel.request(MESSAGES, SCHEMAS)
    assert result["name"] == first["name"]
    assert result["arguments"] == json.loads(first["arguments"])
    assert result["dropped_tool_calls"] == 1 and channel.dropped_tool_calls == 1
    assert len(sent) == account.check()["calls"] == 1


def test_parallel_tool_calls_with_unknown_tool_fail_closed(isolated, monkeypatch):
    monkeypatch.setenv("LECTURELENS_REAL_EVAL", "1")
    monkeypatch.setenv("AGENT_LLM_API_KEY", "synthetic-p7-key-do-not-log")
    account, sent = ledger(isolated, RealPolicy(live=True)), []
    channel = Channel(account, transport=httpx.MockTransport(lambda _: sent.append(1) or _parallel("evil")))
    with pytest.raises(EvalError, match="REQUEST_FAILED"):
        channel.request(MESSAGES, SCHEMAS)
    rows = [json.loads(line) for line in account.path.read_text().splitlines()]
    assert len(sent) == 1 and rows[-1]["state"] == "failed"
    assert rows[-1]["charged_nano_usd"] == rows[0]["reserved_nano_usd"]
