"""All P8 paid-channel tests use fake transport and isolated PG; no live opt-in."""

import json
import os
import uuid
from dataclasses import replace

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from lecturelens_real_eval.tutor_channel import Channel, EvalError, Ledger, TutorPolicy, encode
from lecturelens_real_eval.tutor_runner import (
    DATA,
    Review,
    fake_transport,
    run_evaluation,
    summarize,
    verify_inputs,
)

TUTOR = [{"type": "function", "function": {"name": "search_tutor_evidence", "parameters": {}}}]
REVIEW = [
    {"type": "function", "function": {"name": "review_tutor_turn", "parameters": Review.model_json_schema()}}
]
MESSAGES = [{"role": "user", "content": "private learner text"}]


@pytest.fixture
def isolated(tmp_path):
    dsn = make_conninfo(os.environ["AGENT_TEST_DATABASE_URL"], dbname="lecturelens_agent_acceptance")
    schema = "p8_eval_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    yield make_conninfo(dsn, options=f"-csearch_path={schema},public"), tmp_path
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def account(isolated, policy=None):
    dsn, path = isolated
    ledger = Ledger(dsn, path / "ledger.jsonl", "test-" + uuid.uuid4().hex, policy or TutorPolicy())
    ledger.install()
    return ledger


def response(name="search_tutor_evidence", arguments=None, usage=None):
    return httpx.Response(
        200,
        json={
            "usage": usage or {"prompt_tokens": 10, "completion_tokens": 10},
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(arguments or {"query": "BFS"}),
                                },
                            }
                        ]
                    },
                }
            ],
        },
    )


def test_live_requires_dual_switch_and_fake_requires_transport(monkeypatch):
    monkeypatch.delenv("LECTURELENS_REAL_EVAL", raising=False)
    with pytest.raises(EvalError, match="SWITCH_REQUIRED"):
        TutorPolicy(live=True).validate()
    with pytest.raises(EvalError, match="FAKE_TRANSPORT_REQUIRED"):
        Channel(type("L", (), {"policy": TutorPolicy()})())


@pytest.mark.parametrize(
    "change",
    [
        {"max_calls": 401},
        {"max_nano_usd": 700000001},
        {"allowed_route": "https://evil.invalid"},
        {"model": "deepseek-v4-pro"},
        {"max_tokens": 1201},
    ],
)
def test_caps_and_tutor_model_cannot_expand(change):
    with pytest.raises(EvalError, match="POLICY_INVALID"):
        replace(TutorPolicy(), **change).validate()


@pytest.mark.parametrize(
    "change", [{"host": "localhost"}, {"port": "5432"}, {"hostaddr": "203.0.113.1"}, {"dbname": "production"}]
)
def test_dsn_restrictions_never_connect(isolated, change):
    with pytest.raises(EvalError, match="ISOLATED_DATABASE"):
        Ledger(make_conninfo(isolated[0], **change), isolated[1] / "none", "blocked", TutorPolicy())


def test_routing_and_price_ceiling_by_purpose_and_reservation_visible_before_send(isolated):
    ledger = account(isolated)
    seen = []

    def send(request):
        assert ledger.check()["pending"] == 1
        with ledger.connect() as conn:
            records = [
                r["record"]
                for r in conn.execute(
                    "SELECT record FROM p8_tutor_real_event WHERE run_id=%s ORDER BY sequence",
                    (ledger.run_id,),
                )
            ]
        file_records = [json.loads(line) for line in ledger.path.read_text().splitlines()]
        assert records == file_records
        payload = json.loads(request.content)
        reservation = file_records[-1]
        seen.append(payload["model"])
        if payload["model"] == "deepseek-v4-pro":
            assert reservation["input_rate"] == 1740 and reservation["output_rate"] == 3960
            return response(
                "review_tutor_turn",
                dict(
                    answer_supported=True,
                    context_retained=True,
                    socratic_compliant=True,
                    abstention_clean=True,
                ),
            )
        assert reservation["input_rate"] == 300 and reservation["output_rate"] == 1200
        return response()

    channel = Channel(ledger, transport=httpx.MockTransport(send))
    channel.request(MESSAGES, TUTOR)
    channel.request(MESSAGES, REVIEW, purpose="review")
    assert seen == ["deepseek-flash", "deepseek-v4-pro"]
    assert ledger.check()["nano_usd"] == 10 * (300 + 1200 + 1740 + 3960)
    for schemas, purpose in [(REVIEW, "tutor"), (TUTOR, "review")]:
        with pytest.raises(EvalError, match="REQUEST_INVALID"):
            channel.request(MESSAGES, schemas, purpose=purpose)
    assert ledger.check()["calls"] == 2


def test_ledger_itself_refuses_swapped_model_tool_routes(isolated):
    ledger = account(isolated)
    for model, schemas in [("deepseek-v4-pro", TUTOR), ("deepseek-flash", REVIEW)]:
        with pytest.raises(EvalError, match="ROUTE_INVALID"):
            ledger.reserve(encode({"model": model, "tools": schemas}), 100)
    assert ledger.check()["calls"] == 0


def test_unknown_reservation_and_tamper_block_dispatch(isolated):
    ledger = account(isolated)
    raw = encode({"model": "deepseek-flash", "tools": TUTOR})
    ledger.reserve(raw, 1200)
    transport = httpx.MockTransport(lambda _: pytest.fail("pending cannot dispatch"))
    with pytest.raises(EvalError, match="UNKNOWN_OUTCOME"):
        Channel(ledger, transport=transport).request(MESSAGES, TUTOR)
    assert ledger.check()["pending"] == 1
    ledger.path.write_text("")
    with pytest.raises(EvalError, match="LEDGER_MISMATCH"):
        ledger.check()


def test_budget_no_retries_on_transport_error_and_fake_never_reads_key(isolated, monkeypatch):
    ledger = account(isolated, TutorPolicy(max_calls=1))
    original = os.environ.get

    def guarded(key, *args):
        if key == "AGENT_LLM_API_KEY":
            pytest.fail("fake must never read credentials")
        return original(key, *args)

    monkeypatch.setattr(os.environ, "get", guarded)
    sends = []

    def send(request):
        sends.append(1)
        raise RuntimeError("sk-offline-test-key-must-not-appear")

    channel = Channel(ledger, transport=httpx.MockTransport(send))
    with pytest.raises(EvalError, match="REQUEST_FAILED") as error:
        channel.request(MESSAGES, TUTOR)
    with pytest.raises(EvalError, match="BUDGET_EXHAUSTED"):
        channel.request(MESSAGES, TUTOR)
    assert sends == [1]
    assert "sk-offline" not in str(error.value) + ledger.path.read_text()
    assert ledger.check()["nano_usd"] > 0


def test_frozen_scripts_absence_and_threshold_hashes():
    scripts, thresholds = verify_inputs()
    assert len(scripts) == 24 and sum(len(d["turns"]) for d in scripts) == 80
    assert sum(any(t["context_followup"] for t in d["turns"]) for d in scripts) == 24
    assert sum(any(t["expected_insufficient"] for t in d["turns"]) for d in scripts) == 8
    assert sum(any(t["socratic"] for t in d["turns"]) for d in scripts) == 8
    assert thresholds["max_calls"] == 400 and thresholds["max_usd"] == 0.70


def test_modified_frozen_input_refuses_before_egress(monkeypatch, tmp_path):
    from lecturelens_real_eval import tutor_runner

    source = json.loads((DATA / "frozen.json").read_text())
    source["files"]["eval/p8-tutor/thresholds.json"] = "0" * 64
    (tmp_path / "frozen.json").write_text(json.dumps(source))
    monkeypatch.setattr(tutor_runner, "DATA", tmp_path)
    with pytest.raises(EvalError, match="FROZEN_INPUT_CHANGED"):
        verify_inputs()


def test_mock_eval_e2e_writes_summary_dialogues_sources_reviews_and_mirrored_usage(isolated):
    dsn, directory = isolated
    result = run_evaluation(
        dsn, directory / "eval-ledger.jsonl", "mock-round", TutorPolicy(), output_root=directory
    )
    assert result["verdict"] == "PASS", result
    assert result["quality_status"] == "NOT_RUN_MOCK_MECHANICS_ONLY"
    assert result["dialogues"] == 24 and result["turns"] == result["reviewed_turns"] == 80
    assert result["accounting"]["calls"] == 240 and result["accounting"]["pending"] == 0
    output = directory / "mock-round"
    rows = [json.loads(line) for line in (output / "dialogues.jsonl").read_text().splitlines()]
    assert all(len(d["turns"]) in {3, 4} for d in rows)
    assert all(c["text"] and c["page"] for d in rows for t in d["turns"] for c in t["citations"])
    assert (output / "sample.py").exists() and (output / "summary.json").exists()
    ledger = Ledger(
        dsn,
        directory / "eval-ledger.jsonl",
        "mock-round",
        replace(TutorPolicy(), candidate_sha256=result["candidate_sha256"]),
    )
    assert ledger.check() == result["accounting"]


def test_fabricated_citation_stops_round_and_fails_even_if_other_fields_invalid(isolated):
    dsn, directory = isolated
    fake = fake_transport()

    def fabricated(request):
        payload = json.loads(request.content)
        if payload["tools"][0]["function"]["name"] == "search_tutor_evidence" and len(payload["tools"]) > 1:
            return response(
                "finish_tutor_turn",
                {"text": "Wrong [fake-id]", "evidence_ids": ["fake-id"], "outcome": "bad"},
            )
        return fake.handle_request(request)

    result = run_evaluation(
        dsn,
        directory / "fabricated.jsonl",
        "fabricated",
        TutorPolicy(),
        transport=httpx.MockTransport(fabricated),
        output_root=directory,
    )
    assert result["verdict"] == "FAIL" and result["fatal"] == "REAL_EVAL_CITATION_FABRICATED"
    assert result["dialogues"] == 1 and result["turns"] == 1 and result["accounting"]["calls"] == 2
    row = json.loads((directory / "fabricated/dialogues.jsonl").read_text())["turns"][0]
    assert row["status"] == "failed" and row["answer"] is None
    assert row["proposals"][-1]["arguments"]["outcome"] == "bad"


def test_channel_error_fails_round_and_preserves_partial_trial(isolated):
    dsn, directory = isolated
    result = run_evaluation(
        dsn,
        directory / "error.jsonl",
        "error",
        TutorPolicy(),
        transport=httpx.MockTransport(lambda _: httpx.Response(429)),
        output_root=directory,
    )
    # Runtime may redact a transport failure into a failed turn, but ledger errors are fatal.
    assert result["verdict"] == "FAIL"
    assert result["accounting"]["calls"] > 0
    assert (directory / "error/dialogues.jsonl").exists()


def test_no_reviewer_cannot_claim_quality_pass(isolated):
    scripts, thresholds = verify_inputs()
    result = summarize([], [], {"calls": 0, "nano_usd": 0, "blocked": None}, thresholds, None, False)
    assert result["verdict"] == "PARTIAL"


def test_fabricated_citation_in_dropped_parallel_call_also_stops_round(isolated):
    dsn, directory = isolated
    fake = fake_transport()

    def extra(request):
        payload = json.loads(request.content)
        result = fake.handle_request(request)
        if len(payload["tools"]) > 1:
            body = json.loads(result.content)
            body["choices"][0]["message"]["tool_calls"].append(
                {
                    "type": "function",
                    "function": {
                        "name": "finish_tutor_turn",
                        "arguments": json.dumps(
                            {"outcome": "answered", "text": "invented [bad-id]", "evidence_ids": ["bad-id"]}
                        ),
                    },
                }
            )
            return httpx.Response(200, json=body)
        return result

    result = run_evaluation(
        dsn,
        directory / "extra.jsonl",
        "extra",
        TutorPolicy(),
        transport=httpx.MockTransport(extra),
        output_root=directory,
    )
    assert result["verdict"] == "FAIL" and result["fatal"] == "REAL_EVAL_CITATION_FABRICATED"
    assert result["accounting"]["calls"] == 2


def test_missing_reviewer_judgments_count_as_failed_metrics():
    from lecturelens_real_eval.tutor.contracts import ABSTENTION

    _, thresholds = verify_inputs()
    turn = {
        "ordinal": 1,
        "script": {"context_followup": True, "expected_insufficient": True, "socratic": False},
        "citation_validity": [],
        "status": "completed",
        "outcome": "insufficient_evidence",
        "answer": ABSTENTION,
        "citations": [],
        "latency_s": 0.1,
    }
    result = summarize(
        [{"dialogue_id": "test", "turns": [turn]}],
        [],
        {"calls": 1, "nano_usd": 1, "blocked": None},
        thresholds,
        None,
        False,
    )
    assert result["metrics"]["no_evidence_abstain_rate"] == 0
    assert result["metrics"]["context_retention_rate"] == 0
    assert result["verdict"] == "PARTIAL"


def test_pending_or_unknown_accounting_can_never_pass():
    _, thresholds = verify_inputs()
    for accounting in ({"calls": 1, "nano_usd": 1, "pending": 1}, {"calls": None, "nano_usd": None}):
        result = summarize([], [], accounting, thresholds, None, False)
        assert result["verdict"] == "FAIL" and result["fatal"] == "REAL_EVAL_UNKNOWN_ACCOUNTING"
