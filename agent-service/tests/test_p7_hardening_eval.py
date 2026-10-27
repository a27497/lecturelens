"""Offline hardening acceptance: real isolated PG, exclusively injected HTTP transport."""

import importlib.util
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

from lecturelens_real_eval.channel import encode, isolated_dsn
from lecturelens_real_eval.hardening_channel import (
    GENERATOR_MODEL,
    PRICES,
    REVIEWER_MODEL,
    Channel,
    EvalError,
    Ledger,
    RealPolicy,
)
from lecturelens_real_eval.hardening_runner import (
    DATA,
    fake_transport,
    near_duplicate_pairs,
    review_cards,
    run_evaluation,
    select_tasks,
    summarize,
    verify_inputs,
)
from lecturelens_real_eval.runner import GraphAdapter

GEN = [{"type": "function", "function": {"name": "search_card_evidence", "parameters": {}}}]
REVIEW = [{"type": "function", "function": {"name": "review_card_sources", "parameters": {}}}]
MESSAGES = [{"role": "user", "content": "offline test"}]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original = socket.socket.connect

    def local(sock, address):
        if isinstance(address, tuple) and address[0] != "127.0.0.1":
            raise AssertionError("Hardening tests allow only isolated loopback PG")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", local)
    monkeypatch.delenv("LECTURELENS_REAL_EVAL", raising=False)
    monkeypatch.delenv("AGENT_LLM_API_KEY", raising=False)


@pytest.fixture
def isolated(tmp_path):
    dsn = make_conninfo(os.environ["AGENT_TEST_DATABASE_URL"], dbname="lecturelens_agent_acceptance")
    schema = "p7_hardening_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    # A retained standalone run may own public tables; never replay its artifacts.
    yield make_conninfo(dsn, options=f"-csearch_path={schema}"), tmp_path / "ledger.jsonl"
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def ledger(isolated, policy=None):
    dsn, path = isolated
    account = Ledger(dsn, path, "hardening-" + uuid.uuid4().hex, policy or RealPolicy())
    account.install()
    return account


def response(name="search_card_evidence", arguments=None, usage=None):
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
                                "function": {"name": name, "arguments": json.dumps(arguments or {})},
                            }
                        ]
                    },
                }
            ],
        },
    )


def card(front="front", back="back", evidence_id="e"):
    return {
        "front": front,
        "back": back,
        "citations": [{"evidence_id": evidence_id, "text": "source", "page": 1}],
    }


def records(account):
    return [json.loads(line) for line in account.path.read_text().splitlines()]


@pytest.mark.parametrize("schemas,wrong", [(GEN, REVIEWER_MODEL), (REVIEW, GENERATOR_MODEL)])
def test_wrong_model_rejected_before_reservation_or_send(isolated, schemas, wrong):
    account = ledger(isolated)
    channel = Channel(account, transport=httpx.MockTransport(lambda _: pytest.fail("must not send")))
    with pytest.raises(EvalError, match="MODEL_ROUTING"):
        channel.request(MESSAGES, schemas, model=wrong)
    assert account.check()["calls"] == 0
    raw = encode({"model": wrong, "tools": schemas, "max_tokens": 1200})
    with pytest.raises(EvalError, match="REQUEST_INVALID"):
        account.reserve(raw, 1200)


def test_mixed_review_generation_tools_rejected(isolated):
    account = ledger(isolated)
    with pytest.raises(EvalError, match="MODEL_ROUTING"):
        Channel(account, transport=fake_transport()).request(MESSAGES, GEN + REVIEW)
    assert not records(account)


@pytest.mark.parametrize(
    "changes",
    [
        {"model": REVIEWER_MODEL},
        {"reviewer_model": GENERATOR_MODEL},
        {"model": "other"},
        {"allowed_route": "https://example.invalid"},
        {"thinking": "enabled"},
        {"max_calls": 221},
        {"max_nano_usd": 600_000_001},
    ],
)
def test_policy_is_exact_and_capped(changes):
    with pytest.raises(EvalError, match="POLICY_INVALID"):
        replace(RealPolicy(), **changes).validate()


def test_dual_switch_fake_transport_and_isolation(isolated):
    with pytest.raises(EvalError, match="SWITCH_REQUIRED"):
        RealPolicy(live=True).validate()
    account = ledger(isolated)
    with pytest.raises(EvalError, match="FAKE_TRANSPORT_REQUIRED"):
        Channel(account)
    assert "25721" in isolated_dsn("postgresql://p7@127.0.0.1:25721/lecturelens_agent_acceptance")
    with pytest.raises(EvalError, match="ISOLATED_DATABASE_REQUIRED"):
        isolated_dsn("postgresql://p7@remote.invalid:25721/lecturelens_agent_acceptance")


@pytest.mark.parametrize("model,schemas", [(GENERATOR_MODEL, GEN), (REVIEWER_MODEL, REVIEW)])
def test_model_price_reservation_settlement_and_mirror(isolated, model, schemas):
    account = ledger(isolated)
    sent = []

    def send(request):
        # Observe durable matching reservations before transport receives the body.
        assert account.check()["pending"] == 1
        with account.connect() as conn:
            assert (
                conn.execute("SELECT record FROM p7_real_event").fetchone()["record"] == records(account)[0]
            )
        sent.append(json.loads(request.content))
        return response(schemas[0]["function"]["name"])

    Channel(account, transport=httpx.MockTransport(send)).request(MESSAGES, schemas, model=model)
    rows = records(account)
    ip, op = PRICES[model]
    assert sent[0]["model"] == model and sent[0]["thinking"] == {"type": "disabled"}
    assert rows[0]["reserved_nano_usd"] == rows[0]["input_bytes"] * ip + 1200 * op
    assert rows[1]["charged_nano_usd"] == 100 * (ip + op)
    assert rows[0]["model"] == rows[1]["model"] == model
    assert rows[0]["call_id"] == rows[1]["call_id"]
    assert account.check()["nano_usd"] == 100 * (ip + op)


@pytest.mark.parametrize("schemas", [GEN, REVIEW])
@pytest.mark.parametrize("kind", ["http", "timeout", "malformed", "schema"])
def test_failed_requests_charge_full_model_reservation_no_retry(isolated, schemas, kind):
    account, sent = ledger(isolated), []

    def send(request):
        sent.append(1)
        if kind == "timeout":
            raise httpx.ReadTimeout("untrusted body")
        if kind == "http":
            return httpx.Response(503)
        if kind == "malformed":
            return httpx.Response(200, text="broken json")
        return response(schemas[0]["function"]["name"])

    def validate(_):
        raise ValueError("private invalid output")

    with pytest.raises(EvalError):
        Channel(account, transport=httpx.MockTransport(send)).request(
            MESSAGES,
            schemas,
            validate=validate if kind == "schema" else None,
        )
    rows = records(account)
    assert len(sent) == 1
    assert rows[-1]["state"] == "failed"
    assert rows[-1]["charged_nano_usd"] == rows[0]["reserved_nano_usd"]


def test_220_calls_persistently_bounded(isolated):
    account = ledger(isolated)
    channel = Channel(account, transport=httpx.MockTransport(lambda _: response()))
    for _ in range(220):
        channel.request(MESSAGES, GEN)
    with pytest.raises(EvalError, match="BUDGET_EXHAUSTED"):
        channel.request(MESSAGES, GEN)
    assert account.check()["calls"] == 220
    with pytest.raises(EvalError, match="ALREADY_EXISTS"):
        account.install()
    with pytest.raises(EvalError, match="POLICY_MISMATCH"):
        Ledger(account.dsn, account.path, account.run_id, replace(account.policy, max_calls=219)).check()


def test_reviewer_reservation_hits_whole_run_usd_cap_before_send(isolated):
    account = ledger(isolated)
    raw = encode({"model": REVIEWER_MODEL, "tools": REVIEW, "max_tokens": 1200, "data": "x" * 64000})
    for _ in range(5):
        reservation = account.reserve(raw, 1200)
        account.settle(reservation, error="REAL_EVAL_REQUEST_FAILED")
    with pytest.raises(EvalError, match="BUDGET_EXHAUSTED"):
        account.reserve(raw, 1200)
    assert account.check()["calls"] == 5
    assert account.check()["nano_usd"] <= 600_000_000


def test_usage_over_reservation_and_unknown_outcome_fail_closed(isolated):
    account = ledger(isolated)
    channel = Channel(
        account,
        transport=httpx.MockTransport(
            lambda _: response(
                "review_card_sources",
                usage={"prompt_tokens": 1_000_000, "completion_tokens": 100},
            )
        ),
    )
    with pytest.raises(EvalError, match="USAGE_EXCEEDED"):
        channel.request(MESSAGES, REVIEW)
    assert account.check()["nano_usd"] == 1_740_396_000
    with pytest.raises(EvalError, match="RUN_STOPPED"):
        channel.request(MESSAGES, REVIEW)


def test_pending_and_divergent_ledgers_never_send(isolated):
    account = ledger(isolated)
    account.reserve(encode({"model": GENERATOR_MODEL, "tools": GEN, "max_tokens": 1}), 1)
    channel = Channel(account, transport=httpx.MockTransport(lambda _: pytest.fail("must not send")))
    with pytest.raises(EvalError, match="UNKNOWN_OUTCOME"):
        channel.request(MESSAGES, GEN)
    assert account.check()["pending"] == 1
    with account.path.open("ab") as file:
        file.write(b"partial")
    before = account.path.read_bytes()
    with pytest.raises(EvalError, match="LEDGER_MISMATCH"):
        channel.request(MESSAGES, GEN)
    assert account.path.read_bytes() == before


def test_double_review_independent_shuffled_and_both_pass_rule(isolated):
    account, seen = ledger(isolated), []
    cards = [card(f"front {i}", f"back {i}") for i in range(4)]
    first = ["supported", "supported", "unsupported", "unclear"]
    second = ["supported", "unclear", "unsupported", "unclear"]

    def send(request):
        payload = json.loads(request.content)
        body = json.loads(payload["messages"][-1]["content"])
        assert payload["model"] == REVIEWER_MODEL
        assert set(body) == {"cards"}
        assert len(payload["messages"]) == 2
        seen.append(body)
        verdicts = first if len(seen) == 1 else second
        return response(
            "review_card_sources",
            {
                "checks": [
                    {"index": i, "verdict": verdicts[int(c["front"].split()[-1])]}
                    for i, c in enumerate(body["cards"])
                ]
            },
        )

    review = review_cards(Channel(account, transport=httpx.MockTransport(send)), cards)
    assert len(seen) == account.check()["calls"] == 2
    assert review["passes"][0]["order"] != review["passes"][1]["order"]
    assert [c["verdict"] for c in review["checks"]] == ["supported", "unclear", "unsupported", "unclear"]
    tasks, _, thresholds = verify_inputs()
    generation = {
        "task": tasks[0],
        "cards": cards,
        "latency_s": 1,
        "stopped": False,
        "protocol_failure": False,
    }
    result = summarize(
        [generation], [{"task_id": tasks[0]["task_id"], **review}], account.check(), thresholds, None, False
    )
    assert result["values"]["source_supported_rate"] == 0.25
    assert result["values"]["review_self_agreement"] == 0.75
    assert result["gates"]["near_duplicate_agreement"] == "insufficient_n"


def test_failed_review_kept_and_second_pass_not_a_repair(isolated):
    account, sent = ledger(isolated), []

    def send(request):
        sent.append(request.content)
        return response(
            "review_card_sources",
            {"checks": [] if len(sent) == 1 else [{"index": 0, "verdict": "supported"}]},
        )

    review = review_cards(Channel(account, transport=httpx.MockTransport(send)), [card()])
    assert len(sent) == 2 and sent[0] == sent[1]
    assert review["error"] == "REAL_EVAL_PROTOCOL_FAILURE"
    assert review["checks"][0]["verdict"] == "unclear"
    assert records(account)[1]["state"] == "failed"


def test_later_channel_error_not_hidden_by_first_review_protocol_failure(isolated):
    account, sent = ledger(isolated), []

    def send(_):
        sent.append(1)
        return response("review_card_sources", {"checks": []}) if len(sent) == 1 else httpx.Response(503)

    review = review_cards(Channel(account, transport=httpx.MockTransport(send)), [card()])
    assert review["error"] == "REAL_EVAL_REQUEST_FAILED"
    assert [p["error"] for p in review["passes"]] == [
        "REAL_EVAL_PROTOCOL_FAILURE",
        "REAL_EVAL_REQUEST_FAILED",
    ]
    assert len(sent) == 2


def test_near_duplicates_normalization_jaccard_and_citation_scope():
    assert near_duplicate_pairs([card("a", "Same, BACK!"), card("other", "same back")]) == [(0, 1)]
    assert near_duplicate_pairs([card("a b c d", "e f g h i"), card("a b c d", "e f g h j")]) == [(0, 1)]
    assert near_duplicate_pairs([card(), card(evidence_id="other")]) == []
    assert near_duplicate_pairs([card(), card("unrelated", "different")]) == []


def complete_trial():
    tasks, _, thresholds = verify_inputs()
    generations, reviews = [], []
    for task in tasks:
        cards = [] if task["expected_stop"] else [card()]
        generations.append(
            {
                "task": task,
                "cards": cards,
                "latency_s": 1,
                "stopped": task["expected_stop"],
                "protocol_failure": False,
            }
        )
        checks = [{"index": 0, "verdict": "supported"}] if cards else []
        reviews.append(
            {"task_id": task["task_id"], "passes": [{"checks": checks}, {"checks": checks}], "checks": checks}
        )
    return generations, reviews, {"calls": 128, "nano_usd": 1000, "blocked": None}, thresholds


def test_full_summary_near_duplicate_math_missing_reviews_and_gate_boundaries():
    generations, reviews, account, thresholds = complete_trial()
    result = summarize(generations, reviews, account, thresholds, None, False)
    assert result["verdict"] == "PASS"
    assert result["values"]["near_duplicate_pairs"] == 231
    assert result["values"]["near_duplicate_agreement"] == 1.0
    # An aggregate claiming support cannot override the observations.
    reviews[0]["passes"][1] = {"checks": [{"index": 0, "verdict": "unsupported"}]}
    result = summarize(generations, reviews, account, thresholds, None, False)
    assert result["values"]["source_supported_rate"] == 21 / 22
    assert result["values"]["review_self_agreement"] == 21 / 22
    assert result["values"]["near_duplicate_agreement"] == 210 / 231
    reviews.pop(0)
    assert (
        summarize(generations, reviews, account, thresholds, None, False)["values"]["source_supported_rate"]
        == 21 / 22
    )
    generations[-1]["stopped"] = False
    result = summarize(generations, reviews, account, thresholds, None, False)
    assert result["gates"]["confusable_correct_stop_rate"] is True
    assert result["confusable_required_correct"] == 7
    generations[-2]["stopped"] = False
    assert summarize(generations, reviews, account, thresholds, None, False)["verdict"] == "PARTIAL"


@pytest.mark.parametrize(
    "failure", ["false_stop", "offtopic", "latency", "protocol", "duplicate", "fabrication", "channel"]
)
def test_missed_gates_and_fatal_verdicts(failure):
    generations, reviews, account, thresholds = complete_trial()
    if failure == "false_stop":
        for g in generations[:3]:
            g.update(stopped=True, cards=[])
    elif failure == "offtopic":
        generations[8]["stopped"] = False
    elif failure == "latency":
        generations[0]["latency_s"] = generations[1]["latency_s"] = 21
    elif failure == "protocol":
        generations[0]["protocol_failure"] = True
        reviews[1]["error"] = "REAL_EVAL_PROTOCOL_FAILURE"
    elif failure == "duplicate":
        for r in reviews[:3]:
            r["passes"] = [{"checks": [{"index": 0, "verdict": "unsupported"}]}] * 2
    elif failure == "fabrication":
        generations[0].update(citation_count=1, valid_citation_count=0)
    else:
        account["blocked"] = "REAL_EVAL_LEDGER_MISMATCH"
    result = summarize(generations, reviews, account, thresholds, None, False)
    assert result["verdict"] == ("FAIL" if failure in {"fabrication", "channel"} else "PARTIAL")


def test_confusable_tasks_originals_unchanged_and_zero_hit_absence_checks():
    tasks, snapshot, thresholds = verify_inputs()
    assert len(tasks) == 32 and thresholds["confusable_count"] == 8
    originals = json.loads((DATA.parent / "p7-real/tasks.json").read_text())["tasks"]
    assert tasks[:24] == originals
    assert len({t["lecture_id"] for t in tasks[24:]}) == 8
    for task in tasks[24:]:
        assert task["kind"] == "confusable" and task["expected_stop"] and task["concept"]
        text = "\n".join(e["text"] for e in snapshot["lectures"][task["lecture_id"]]["evidence"]).casefold()
        assert task["evidence_absence_check"]
        for term in task["evidence_absence_check"]:
            assert term.casefold() not in text, (task["task_id"], term)


def test_changed_thresholds_refuse_live_preflight_before_pg(monkeypatch, tmp_path):
    from lecturelens_real_eval import hardening_runner

    for name in ("frozen.json", "tasks.json", "thresholds.json"):
        (tmp_path / name).write_bytes((DATA / name).read_bytes())
    thresholds = json.loads((tmp_path / "thresholds.json").read_text())
    thresholds["source_supported_rate"] = 0
    (tmp_path / "thresholds.json").write_text(json.dumps(thresholds))
    # Redirect only this frozen input without modifying the real frozen candidate.
    original = hardening_runner.ROOT

    class Root:
        def __truediv__(self, path):
            return (
                tmp_path / "thresholds.json"
                if path == "eval/p7-hardening/thresholds.json"
                else original / path
            )

    monkeypatch.setattr(hardening_runner, "ROOT", Root())
    with pytest.raises(EvalError, match="FROZEN_INPUT_CHANGED"):
        verify_inputs()


def load_script(name):
    spec = importlib.util.spec_from_file_location("p7_hardening_" + name, DATA / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mock_end_to_end_all_metrics_sample_and_human_agreement(isolated, tmp_path):
    dsn, path = isolated
    result = run_evaluation(dsn, path, "hardening-e2e", RealPolicy(), output_root=tmp_path / "results")
    directory = tmp_path / "results/hardening-e2e"
    assert result["verdict"] == "PASS", result
    assert result["quality_status"] == "NOT_RUN_MOCK_MECHANICS_ONLY"
    assert result["calls"] == 128 and result["completed_tasks"] == 32 and result["card_count"] == 22
    assert result["cost_usd"] == 0.04608
    for key in (
        "citation_valid_rate",
        "source_supported_rate",
        "offtopic_correct_stop_rate",
        "confusable_correct_stop_rate",
        "review_self_agreement",
        "near_duplicate_agreement",
    ):
        assert result["values"][key] == 1.0
    assert result["values"]["false_stop_rate"] == result["values"]["protocol_failure_rate"] == 0
    assert len((directory / "generations.jsonl").read_text().splitlines()) == 32
    assert all(
        len(json.loads(line)["passes"]) == 2
        for line in (directory / "reviews.jsonl").read_text().splitlines()
    )
    before = (directory / "sample.md").read_text()
    assert before.count("## ") == before.count("| Human verdict |") == 10
    assert "source" not in before.lower() or "Source:" in before
    load_script("sample").sample(directory)
    assert before == (directory / "sample.md").read_text()
    human = dict.fromkeys(json.loads((directory / "human-verdicts.template.json").read_text()), "supported")
    audit = load_script("agreement")
    assert audit.agreement(directory, human) == {"n": 10, "matches": 10, "human_vs_reviewer_agreement": 1.0}
    human[next(iter(human))] = "unsupported"
    assert audit.agreement(directory, human)["human_vs_reviewer_agreement"] == 0.9
    for invalid in ({}, {"unknown:0": "supported"}, {next(iter(human)): ""}):
        with pytest.raises(ValueError):
            audit.agreement(directory, invalid)


@pytest.mark.parametrize("failure", ["fabrication", "http", "review_http"])
def test_fatal_run_preserves_failure_and_stops_whole_round(isolated, tmp_path, failure):
    dsn, path = isolated
    fake, sent = fake_transport(), []

    def send(request):
        sent.append(1)
        if failure == "fabrication" and len(sent) == 2:
            return response(
                "create_evidence_cards", {"cards": [{"front": "a", "back": "b", "evidence_ids": ["made-up"]}]}
            )
        if failure == "http" or (failure == "review_http" and len(sent) == 3):
            return httpx.Response(503)
        return fake.handle_request(request)

    result = run_evaluation(
        dsn,
        path,
        "fatal-test",
        RealPolicy(),
        transport=httpx.MockTransport(send),
        output_root=tmp_path / "results",
    )
    assert result["verdict"] == "FAIL" and result["completed_tasks"] == 1
    assert result["calls"] == len(sent) == {"fabrication": 2, "http": 1, "review_http": 3}[failure]
    directory = tmp_path / "results/fatal-test"
    assert all(
        (directory / name).exists()
        for name in ("generations.jsonl", "reviews.jsonl", "summary.json", "sample.md")
    )
    if failure == "fabrication":
        assert result["fatal"] == "REAL_EVAL_CITATION_FABRICATED"
        assert result["values"]["citation_valid_rate"] == 0


def test_fake_never_reads_key_and_errors_never_leak_payload(isolated, monkeypatch, capsys, caplog):
    account = ledger(isolated)
    original = os.environ.get
    secret = "synthetic-transport-secret-do-not-log"

    def get(name, *args):
        assert name != "AGENT_LLM_API_KEY"
        return original(name, *args)

    def send(_):
        raise httpx.ReadError(secret)

    monkeypatch.setattr(os.environ, "get", get)
    with pytest.raises(EvalError) as caught:
        Channel(account, transport=httpx.MockTransport(send)).request(MESSAGES, REVIEW)
    assert caught.value.__context__ is None
    with account.connect() as conn:
        pg = str(conn.execute("SELECT record FROM p7_real_event").fetchall())
    captured = capsys.readouterr()
    assert (
        secret
        not in "".join(traceback.format_exception(caught.value))
        + records(account).__str__()
        + pg
        + captured.out
        + captured.err
        + caplog.text
    )


def test_parallel_calls_still_execute_only_first_and_record_dropped_names(isolated):
    """Mutation: omitting result or cumulative name recording must fail this test."""
    account = ledger(isolated)
    data = json.loads(response(arguments={"query": "course evidence"}).content)
    calls = data["choices"][0]["message"]["tool_calls"]
    for name in ("stop_cards", "create_evidence_cards", "stop_cards"):
        calls.append(json.loads(response(name).content)["choices"][0]["message"]["tool_calls"][0])
    channel = Channel(account, transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data)))
    executed = []
    schemas = [
        {"type": "function", "function": {"name": name, "parameters": {}}}
        for name in ("search_card_evidence", "stop_cards", "create_evidence_cards")
    ]
    result = channel.request(MESSAGES, schemas, validate=executed.append)
    expected = ["stop_cards", "create_evidence_cards", "stop_cards"]
    assert result["name"] == "search_card_evidence"
    assert result["arguments"] == {"query": "course evidence"}
    assert executed == [result]
    assert result["dropped_tool_calls"] == channel.dropped_tool_calls == len(expected)
    assert result["dropped_tool_call_names"] == channel.dropped_tool_call_names == expected
    assert account.check()["calls"] == 1


def test_third_generation_call_offers_only_wrap_up_tools(isolated):
    """Mutation: removing the last-call filter must expose search and fail assertions."""
    account, seen = ledger(isolated), []

    def send(request):
        payload = json.loads(request.content)
        names = [schema["function"]["name"] for schema in payload["tools"]]
        seen.append(names)
        # This model always searches if offered the tool, regardless of call number.
        return (
            response(arguments={"query": "more evidence"})
            if "search_card_evidence" in names
            else response("stop_cards", {"reason": "Evidence does not support the goal."})
        )

    adapter = GraphAdapter(Channel(account, transport=httpx.MockTransport(send)), None)
    schemas = [
        {"type": "function", "function": {"name": name, "parameters": {"sentinel": name}}}
        for name in ("search_card_evidence", "create_evidence_cards", "stop_cards")
    ]
    messages = [{"role": "user", "content": json.dumps({"evidence": []})}]
    for _ in range(3):
        result = adapter.flashcards(messages, schemas, 20)
    assert seen == [
        ["search_card_evidence", "create_evidence_cards", "stop_cards"],
        ["search_card_evidence", "create_evidence_cards", "stop_cards"],
        ["create_evidence_cards", "stop_cards"],
    ]
    assert len(schemas) == 3  # Filtering must not mutate the caller's offering.
    assert result["name"] == adapter.last_action == "stop_cards"
    assert adapter.task_calls == account.check()["calls"] == 3
    with pytest.raises(EvalError, match="GENERATION_CALL_LIMIT"):
        adapter.flashcards(messages, schemas, 20)
    assert len(seen) == 3


def test_last_call_empty_wrap_up_offering_fails_closed(isolated):
    account = ledger(isolated)
    adapter = GraphAdapter(
        Channel(account, transport=httpx.MockTransport(lambda _: pytest.fail("must not dispatch"))), None
    )
    adapter.task_calls = 2
    with pytest.raises(EvalError, match="WRAP_UP_TOOLS_REQUIRED"):
        adapter.flashcards([], GEN, 20)
    assert adapter.task_calls == 2
    assert account.check()["calls"] == 0


def test_confusable_searching_model_stops_on_third_call_and_keeps_dropped_names(isolated, tmp_path):
    tasks, _, _ = verify_inputs()
    task = next(t for t in tasks if t["kind"] == "confusable")
    seen = []

    def send(request):
        payload = json.loads(request.content)
        names = [schema["function"]["name"] for schema in payload["tools"]]
        seen.append(names)
        if names == ["review_card_sources"]:
            data = json.loads(response("review_card_sources", {"checks": []}).content)
            # Review names must also survive the short-lived dispatch wrapper.
            calls = data["choices"][0]["message"]["tool_calls"]
            calls.append(calls[0].copy())
            return httpx.Response(200, json=data)
        if "search_card_evidence" not in names:
            return response("stop_cards", {"reason": "Evidence does not support the goal."})
        data = json.loads(response(arguments={"query": "course evidence"}).content)
        if len(seen) == 2:
            data["choices"][0]["message"]["tool_calls"].append(
                json.loads(response("stop_cards").content)["choices"][0]["message"]["tool_calls"][0]
            )
        return httpx.Response(200, json=data)

    dsn, path = isolated
    result = run_evaluation(
        dsn,
        path,
        "third-call-stop",
        RealPolicy(),
        transport=httpx.MockTransport(send),
        output_root=tmp_path,
        task_ids=task["task_id"],
    )
    generation = json.loads((tmp_path / "third-call-stop/generations.jsonl").read_text())
    review = json.loads((tmp_path / "third-call-stop/reviews.jsonl").read_text())
    assert generation["stopped"] is True and generation["cards"] == []
    assert generation["error"] is None and generation["protocol_failure"] is False
    assert generation["model_calls"] == 3
    assert generation["dropped_tool_calls"] == 1
    assert generation["dropped_tool_call_names"] == ["stop_cards"]
    assert [p["name"] for p in generation["proposals"]] == [
        "search_card_evidence",
        "search_card_evidence",
        "stop_cards",
    ]
    assert seen[2] == ["create_evidence_cards", "stop_cards"]
    assert len(review["passes"]) == 2 and review["dropped_tool_calls"] == 2
    assert review["dropped_tool_call_names"] == ["review_card_sources"] * 2
    assert result["dropped_tool_calls"] == 3
    assert result["dropped_tool_call_names"] == ["stop_cards"] + ["review_card_sources"] * 2
    assert result["values"]["confusable_correct_stop_rate"] == 1
    assert result["confusable_required_correct"] == 1
    assert result["values"]["protocol_failure_rate"] == 0
    assert result["calls"] == len(seen) == 5
    assert result["fatal"] is None


@pytest.mark.parametrize("ids", ["", "unknown", "algorithms-l1-1,", "algorithms-l1-1,algorithms-l1-1"])
def test_invalid_task_selection_fails_before_pg_or_ledger(ids, tmp_path):
    with pytest.raises(EvalError, match="TASK_SELECTION_INVALID"):
        run_evaluation(
            "invalid",
            tmp_path / "ledger",
            "invalid-selection",
            RealPolicy(),
            output_root=tmp_path / "results",
            task_ids=ids,
        )
    assert not (tmp_path / "results").exists() and not (tmp_path / "ledger").exists()


def test_focused_selection_preserves_frozen_order_and_does_not_claim_full_acceptance(isolated, tmp_path):
    tasks, _, thresholds = verify_inputs()
    ids = ",".join(
        [t["task_id"] for t in tasks if t["kind"] == "confusable"]
        + ["quantum-l1-1", "probability-l1-1", "algorithms-l2-1", "algorithms-l1-1"]
    )
    selected = select_tasks(tasks, ids)
    assert select_tasks(tasks, None) == tasks
    assert len(selected) == 12 and selected == [t for t in tasks if t["task_id"] in ids.split(",")]
    dsn, path = isolated
    result = run_evaluation(dsn, path, "focused-mock", RealPolicy(), output_root=tmp_path, task_ids=ids)
    assert result["evaluation_scope"] == "focused" and result["selected_tasks_completed"] is True
    assert result["thresholds"] == thresholds
    assert result["completed_tasks"] == 12 and result["card_count"] == 4 and result["calls"] == 48
    assert result["verdict"] == "PARTIAL" and result["gates"]["completed_tasks"] is False
    assert result["values"]["offtopic_correct_stop_rate"] is None
    assert result["gates"]["offtopic_correct_stop_rate"] == "insufficient_n"
    assert result["values"]["confusable_correct_stop_rate"] == 1
    assert result["confusable_required_correct"] == 7
    assert result["values"]["false_stop_rate"] == result["values"]["protocol_failure_rate"] == 0


def test_focused_run_still_verifies_unselected_frozen_tasks(monkeypatch, tmp_path):
    from lecturelens_real_eval import hardening_runner

    tasks = json.loads((DATA / "tasks.json").read_text())
    tasks["tasks"][-1]["goal"] = "Changed unselected goal"
    changed = tmp_path / "tasks.json"
    changed.write_text(json.dumps(tasks))
    original = hardening_runner.ROOT

    class Root:
        def __truediv__(self, path):
            return changed if path == "eval/p7-hardening/tasks.json" else original / path

    monkeypatch.setattr(hardening_runner, "ROOT", Root())
    with pytest.raises(EvalError, match="FROZEN_INPUT_CHANGED"):
        run_evaluation(
            "invalid",
            tmp_path / "ledger",
            "changed-unselected",
            RealPolicy(),
            output_root=tmp_path / "results",
            task_ids="algorithms-l1-1",
        )
    assert not (tmp_path / "results").exists() and not (tmp_path / "ledger").exists()


def test_cli_forwards_task_ids_and_keeps_live_disabled(monkeypatch, capsys):
    from lecturelens_real_eval import hardening_runner

    received = []

    def run(dsn, path, run_id, policy, *, task_ids):
        received.append((dsn, path, run_id, policy, task_ids))
        return {"verdict": "PARTIAL"}

    monkeypatch.setattr(hardening_runner, "run_evaluation", run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run.py",
            "--dsn",
            "unused",
            "--ledger",
            "unused-ledger",
            "--run-id",
            "offline-cli",
            "--max-usd",
            "0.40",
            "--max-calls",
            "160",
            "--task-ids",
            "algorithms-l1-1,quantum-l1-1",
        ],
    )
    assert hardening_runner.main() == 0
    assert len(received) == 1 and received[0][-1] == "algorithms-l1-1,quantum-l1-1"
    policy = received[0][3]
    assert policy.live is False and policy.max_calls == 160 and policy.max_nano_usd == 400_000_000
    assert json.loads(capsys.readouterr().out)["verdict"] == "PARTIAL"
