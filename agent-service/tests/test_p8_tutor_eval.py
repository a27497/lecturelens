"""All P8 paid-channel tests use fake transport and isolated PG; no live opt-in."""

import json
import os
import uuid
from dataclasses import replace
from pathlib import Path

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from lecturelens_real_eval.tutor_channel import Channel, EvalError, Ledger, TutorPolicy, encode
from lecturelens_real_eval.tutor_runner import (
    DATA,
    Review,
    TutorProvider,
    citation_ids,
    fake_transport,
    review_turn,
    run_evaluation,
    select_dialogues,
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
    reviews = [json.loads(line) for line in (output / "reviews.jsonl").read_text().splitlines()]
    _, thresholds = verify_inputs()
    focused = summarize(rows, reviews, result["accounting"], thresholds, None, False, focused=True)
    assert focused["verdict"] == "PARTIAL" and focused["metrics"] == result["metrics"]
    ledger = Ledger(
        dsn,
        directory / "eval-ledger.jsonl",
        "mock-round",
        replace(TutorPolicy(), candidate_sha256=result["candidate_sha256"]),
    )
    assert ledger.check() == result["accounting"]


@pytest.mark.parametrize("ids", [[], ["unknown"], ["algorithms-l1-1", "algorithms-l1-1"]])
def test_dialogue_filter_rejects_empty_unknown_or_duplicate_ids(ids):
    scripts, _ = verify_inputs()
    with pytest.raises(EvalError, match="DIALOGUE_FILTER_INVALID"):
        select_dialogues(scripts, ids)


@pytest.mark.parametrize("fault", ["evaluation", "limit_ids", "limit_evaluation", "limit_text", "socratic"])
def test_focused_fake_transport_repairs_finish_and_never_claims_full_acceptance(isolated, fault):
    dsn, directory = isolated
    fake = fake_transport()
    observations = []

    def repairable(request):
        payload = json.loads(request.content)
        body = json.loads(payload["messages"][-1]["content"])
        result = fake.handle_request(request)
        if payload["model"] != "deepseek-flash":
            return result
        observations.extend(o for o in body["observations"] if "error" in o)
        response_body = json.loads(result.content)
        function = response_body["choices"][0]["message"]["tool_calls"][0]["function"]
        if function["name"] == "finish_tutor_turn" and len(body["observations"]) == 1:
            args = json.loads(function["arguments"])
            if fault == "limit_ids":
                args["evidence_ids"] = [e["evidence_id"] for e in body["evidence"]]
                assert len(args["evidence_ids"]) > 4
                args["text"] = "Which statement applies? " + " ".join(
                    f"[{eid}]" for eid in args["evidence_ids"]
                )
            elif fault == "limit_evaluation":
                args["evaluation"] = "E" * 501
            elif fault == "limit_text":
                args["text"] += "T" * 1601
            elif fault == "socratic":
                args["outcome"] = "answered"
            elif body["evaluation_required"]:
                args["evaluation"] = ""
            function["arguments"] = json.dumps(args)
            return httpx.Response(200, json=response_body)
        return result

    result = run_evaluation(
        dsn,
        directory / "focus-ledger.jsonl",
        "focus",
        TutorPolicy(),
        transport=httpx.MockTransport(repairable),
        output_root=directory,
        dialogue_ids=["algorithms-l1-2"],
    )
    assert result["verdict"] == "PARTIAL" and result["fatal"] is None
    assert result["scope"] == "focused" and result["selected_dialogue_ids"] == ["algorithms-l1-2"]
    assert result["dialogues"] == 1 and result["turns"] == result["reviewed_turns"] == 3
    assert result["metrics"]["protocol_failure_rate"] == 0
    assert result["metrics"]["socratic_compliance_rate"] == 1
    expected = (
        "TUTOR_FINISH_REPAIR_REQUIRED"
        if fault.startswith("limit_") or fault == "citation"
        else "TUTOR_SOCRATIC_REPAIR_REQUIRED"
        if fault == "socratic"
        else "TUTOR_EVALUATION_REQUIRED"
    )
    assert observations and all(o["error"] == expected for o in observations)
    dialogue = json.loads((directory / "focus/dialogues.jsonl").read_text())
    assert all(t["status"] == "completed" for t in dialogue["turns"])
    assert len(dialogue["turns"][-1]["proposals"]) == 3  # search, rejected finish, repair
    for turn in dialogue["turns"]:
        repaired = turn["proposals"][-1]["arguments"]
        assert turn["answer"] == repaired["text"]
        assert {c["evidence_id"] for c in turn["citations"]} == set(citation_ids(repaired))


def test_filter_preserves_frozen_order():
    scripts, _ = verify_inputs()
    assert select_dialogues(scripts, [d["dialogue_id"] for d in reversed(scripts)]) == scripts


def test_fabricated_citation_stops_round_and_fails_even_if_other_fields_invalid(isolated):
    dsn, directory = isolated
    fake = fake_transport()

    def fabricated(request):
        payload = json.loads(request.content)
        if payload["tools"][0]["function"]["name"] == "search_tutor_evidence" and len(payload["tools"]) > 1:
            return response(
                "finish_tutor_turn",
                {"text": "Wrong [e999]", "evidence_ids": ["fake-id"], "outcome": "bad"},
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


def test_exact_failed_live_answer_has_all_eleven_citations_valid(isolated):
    from lecturelens_real_eval.runner import SnapshotAuthority

    proposal = json.loads((Path(__file__).parent / "fixtures/p8_adjacency_answer.json").read_text())
    authority = SnapshotAuthority(json.loads((DATA.parent / "p7-real/snapshot.json").read_text()))
    scope = dict(owner_id=1, course_id="citation-regression", revision=1)
    authority.register(scope, "algorithms-l1")
    provider = TutorProvider(Channel(account(isolated), transport=fake_transport()), authority)
    provider.scope = scope
    provider.validate({"name": "finish_tutor_turn", "arguments": proposal})
    canonical = {e["evidence_id"] for e in authority.rows(scope)}
    ids = citation_ids(proposal)
    assert len(ids) == 3 and all(i in canonical for i in ids)
    assert provider.channel.ledger.check()["blocked"] is None


@pytest.mark.parametrize("foreign", [None, "e999", "v2-algorithms-l2-p01-e00", "a" * 64])
def test_math_brackets_never_block_eval_but_strict_fabrication_does(isolated, foreign):
    from lecturelens_real_eval.runner import SnapshotAuthority

    authority = SnapshotAuthority(json.loads((DATA.parent / "p7-real/snapshot.json").read_text()))
    scope = dict(owner_id=1, course_id="math-brackets", revision=1)
    authority.register(scope, "algorithms-l1")
    provider = TutorProvider(Channel(account(isolated), transport=fake_transport()), authority)
    provider.scope = scope
    eid = authority.rows(scope)[0]["evidence_id"]
    proposal = {
        "name": "finish_tutor_turn",
        "arguments": {
            "outcome": "answered",
            "text": f"Math [u] [v] [A] [x_1], claim [{eid}].",
            "evaluation": "Check [A] [x_1]." + (f" [{foreign}]" if foreign else ""),
        },
    }
    if foreign:
        with pytest.raises(EvalError, match="REAL_EVAL_CITATION_FABRICATED"):
            provider.validate(proposal)
        assert provider.channel.ledger.check()["blocked"] == "REAL_EVAL_CITATION_FABRICATED"
    else:
        provider.validate(proposal)
        assert citation_ids(proposal["arguments"]) == [eid]
        assert provider.channel.ledger.check()["blocked"] is None


@pytest.mark.parametrize("evidence_id", ["v2-algorithms-l1-p99-e00", "v2-algorithms-l2-p01-e00"])
@pytest.mark.parametrize("location", ["inline", "evaluation"])
def test_id_shaped_unknown_or_other_lecture_citation_is_fatal_before_schema(isolated, evidence_id, location):
    dsn, directory = isolated
    fake = fake_transport()

    def fabricated(request):
        if len(json.loads(request.content)["tools"]) > 1:
            return response(
                "finish_tutor_turn",
                {
                    "outcome": "bad",
                    "text": f"Wrong [{evidence_id}]" if location == "inline" else "Wrong",
                    "evaluation": f"Wrong [{evidence_id}]" if location == "evaluation" else "",
                },
            )
        return fake.handle_request(request)

    result = run_evaluation(
        dsn,
        directory / "id-shaped.jsonl",
        "id-shaped",
        TutorPolicy(),
        transport=httpx.MockTransport(fabricated),
        output_root=directory,
    )
    assert result["verdict"] == "FAIL" and result["fatal"] == "REAL_EVAL_CITATION_FABRICATED"
    assert result["accounting"]["calls"] == 2
    turn = json.loads((directory / "id-shaped/dialogues.jsonl").read_text())["turns"][0]
    assert turn["citation_validity"] == [False] and turn["answer"] is None


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
                            {"outcome": "answered", "text": "invented [e999]", "evidence_ids": ["bad-id"]}
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


@pytest.mark.parametrize("location", ["text", "inline", "dropped_after_bad_schema"])
@pytest.mark.parametrize("invented", ["v2-algorithms-l1-p99-e00", "v2-algorithms-l2-p01-e00"])
def test_oversized_finish_checks_every_id_even_in_dropped_calls(isolated, location, invented):
    from lecturelens_real_eval.runner import SnapshotAuthority
    from lecturelens_real_eval.tutor.contracts import Finish

    authority = SnapshotAuthority(json.loads((DATA.parent / "p7-real/snapshot.json").read_text()))
    scope = dict(owner_id=1, course_id="oversized-citations", revision=1)
    authority.register(scope, "algorithms-l1")
    ids = [e["evidence_id"] for e in authority.rows(scope)][:8]
    args = dict(outcome="answered", text=" ".join(f"[{eid}]" for eid in ids), evidence_ids=ids)
    if location == "inline":
        args["evaluation"] = f"Wrong [{invented}]"
    else:
        args["text"] += f" [{invented}]"
    wire = json.loads(response("finish_tutor_turn", args).content)
    if location == "dropped_after_bad_schema":
        wire["choices"][0]["message"]["tool_calls"].insert(
            0,
            {
                "type": "function",
                "function": {
                    "name": "finish_tutor_turn",
                    "arguments": json.dumps(
                        {
                            "outcome": "bad",
                            "text": "T" * 1601,
                            "evidence_ids": ids,
                        }
                    ),
                },
            },
        )
    ledger = account(isolated)
    channel = Channel(ledger, transport=httpx.MockTransport(lambda _: httpx.Response(200, json=wire)))
    provider = TutorProvider(channel, authority)
    provider.scope = scope
    schemas = [
        {
            "type": "function",
            "function": {"name": "finish_tutor_turn", "parameters": Finish.model_json_schema()},
        }
    ]
    with pytest.raises(EvalError, match="REAL_EVAL_PROTOCOL_FAILURE"):
        provider.decide(MESSAGES, schemas, 20)
    assert ledger.check()["blocked"] == "REAL_EVAL_CITATION_FABRICATED"
    assert ledger.check()["calls"] == 1 and ledger.check()["pending"] == 0
    assert len(provider.proposals) == (2 if location == "dropped_after_bad_schema" else 1)


@pytest.mark.parametrize("fault", ["second_limit", "non_limit_schema"])
def test_focused_schema_failure_remains_failed_turn_and_protocol_metric(isolated, fault):
    dsn, directory = isolated
    fake = fake_transport()

    def invalid(request):
        payload = json.loads(request.content)
        result = fake.handle_request(request)
        if payload["model"] != "deepseek-flash":
            return result
        wire = json.loads(result.content)
        function = wire["choices"][0]["message"]["tool_calls"][0]["function"]
        if function["name"] == "finish_tutor_turn":
            args = json.loads(function["arguments"])
            args["evaluation"] = "E" * 501
            if fault == "non_limit_schema":
                args["outcome"] = "bad"
            function["arguments"] = json.dumps(args)
            return httpx.Response(200, json=wire)
        return result

    result = run_evaluation(
        dsn,
        directory / "failed-schema.jsonl",
        "failed-schema",
        TutorPolicy(),
        transport=httpx.MockTransport(invalid),
        output_root=directory,
        dialogue_ids=["algorithms-l1-1"],
    )
    assert result["verdict"] == "PARTIAL" and result["fatal"] is None
    assert result["metrics"]["protocol_failure_rate"] == 1
    dialogue = json.loads((directory / "failed-schema/dialogues.jsonl").read_text())
    code = "TUTOR_FINISH_FORMAT_INVALID" if fault == "second_limit" else "REAL_EVAL_PROTOCOL_FAILURE"
    assert len(dialogue["turns"]) == 3
    for turn in dialogue["turns"]:
        assert turn["error_code"] == code and turn["answer"] is None and not turn["citations"]
        assert turn["model_calls"] == (3 if fault == "second_limit" else 2)


def test_over_abstain_metric_counts_only_completed_unexpected_abstentions_and_is_report_only():
    from copy import deepcopy

    from lecturelens_real_eval.tutor.contracts import ABSTENTION

    script = dict(expected_insufficient=False, context_followup=False, socratic=False)
    base = dict(
        status="completed",
        outcome="answered",
        answer="answer",
        citations=[],
        citation_validity=[],
        latency_s=0.1,
        script=script,
    )
    turns = [dict(base, ordinal=i) for i in range(1, 6)]
    turns[0].update(outcome="insufficient_evidence", answer=ABSTENTION)
    turns[1].update(
        outcome="insufficient_evidence", answer=ABSTENTION, script={**script, "expected_insufficient": True}
    )
    turns[2].update(status="failed", outcome="insufficient_evidence", answer=None)
    turns[3].update(outcome="socratic_prompt")
    dialogues = [{"dialogue_id": "test-dialogue", "turns": turns}]
    accounting = dict(calls=10, nano_usd=1, pending=0, blocked=None)
    thresholds = {"max_calls": 400, "max_usd": 0.70}
    result = summarize(dialogues, [], accounting, thresholds, None, False)
    assert result["metrics"]["over_abstain_count"] == 1
    assert (
        result["metrics"]["over_abstain_rate"] == 1 / 4
    )  # Includes failed supported-script turns in denominator.
    assert result["over_abstain_turns"] == [("test-dialogue", 1)]
    assert result["verdict"] == "PARTIAL" and result["fatal"] is None
    # Full-suite eligibility and all threshold metrics are identical; this diagnostic
    # cannot alter PASS even when every supported-script turn abstains.
    full = []
    for i in range(24):
        rows = [dict(deepcopy(base), ordinal=j) for j in range(1, (5 if i < 8 else 4))]
        full.append({"dialogue_id": str(i), "turns": rows})
    before = summarize(full, [], accounting, thresholds, None, False)
    for d in full:
        for turn in d["turns"]:
            turn.update(outcome="insufficient_evidence", answer=ABSTENTION)
    after = summarize(full, [], accounting, thresholds, None, False)
    assert before["verdict"] == after["verdict"] == "PASS"
    assert after["metrics"]["over_abstain_count"] == 80 and after["metrics"]["over_abstain_rate"] == 1
    empty = summarize([], [], accounting, thresholds, None, False)
    assert empty["metrics"]["over_abstain_count"] == empty["metrics"]["over_abstain_rate"] == 0
    assert empty["over_abstain_turns"] == []


@pytest.mark.parametrize("reviewed", [True, False])
@pytest.mark.parametrize(
    "kind", ["invented", "abstain", "clarify", "socratic_clarify", "published", "not_followup"]
)
def test_reviewer_cascade_only_downgrades_invented_antecedent(reviewed, kind):
    from lecturelens_real_eval.tutor.contracts import ABSTENTION

    class FixedReview:
        def request(self, messages, schemas, **kwargs):
            prompt = messages[0]["content"]
            assert "failed/unpublished" in prompt and "context_retained=false" in prompt
            data = json.loads(messages[1]["content"])
            assert data["conversation"][-1]["status"] == ("completed" if kind == "published" else "failed")
            return {
                "arguments": dict(
                    answer_supported=True,
                    context_retained=reviewed,
                    socratic_compliant=True,
                    abstention_clean=True,
                )
            }

    turn = dict(
        answer="The reflection phase explains that [e1].", evaluation="", outcome="answered", citations=[]
    )
    if kind == "abstain":
        turn.update(answer=ABSTENTION, outcome="insufficient_evidence")
    elif kind in {"clarify", "socratic_clarify"}:
        turn.update(
            answer="Could you clarify which statement you mean? [e1]",
            outcome="socratic_prompt" if kind == "socratic_clarify" else "answered",
        )
    history = [
        dict(
            learner="Explain the concept",
            tutor="Published [e1]" if kind == "published" else None,
            status="completed" if kind == "published" else "failed",
        )
    ]
    script = dict(
        text="Why is that?",
        expected_topic="the concept",
        socratic=False,
        context_followup=kind != "not_followup",
    )
    result = review_turn(FixedReview(), history, script, turn)
    expected = True if kind in {"abstain", "clarify", "socratic_clarify"} else reviewed and kind != "invented"
    assert result["context_retained"] is expected


@pytest.mark.parametrize("prior", ["published_abstention", "failed", "unpublished"])
@pytest.mark.parametrize("kind", ["clean_abstain", "invented", "nonexact_abstain"])
def test_context_followup_non_penalty_preserves_other_judgments_and_failed_turns(prior, kind):
    from lecturelens_real_eval.tutor.contracts import ABSTENTION

    # Use the inherited union-bound follow-up: a published abstention is also
    # insufficient context for a substantive answer, but a clean stop is valid.
    scripts = json.loads((DATA / "dialogues.json").read_bytes())["dialogues"]
    script = next(d for d in scripts if d["dialogue_id"] == "probability-l1-3")["turns"][1]
    assert script["expected_insufficient"] and script["context_followup"]
    assert script["zero_hit_terms"] == ["union"]
    judgments = dict(
        answer_supported=False, context_retained=False, socratic_compliant=False, abstention_clean=False
    )

    class FixedReview:
        def request(self, messages, schemas, **kwargs):
            return {"arguments": judgments}

    history = [
        dict(
            status="failed" if prior == "failed" else "completed",
            tutor=ABSTENTION if prior == "published_abstention" else None,
            outcome="insufficient_evidence" if prior == "published_abstention" else "failed",
        )
    ]
    turn = dict(
        ordinal=2,
        status="completed",
        outcome="insufficient_evidence",
        answer=ABSTENTION,
        evaluation="",
        citations=[],
        citation_validity=[],
        latency_s=0.1,
        script=script,
    )
    if kind == "invented":
        turn.update(outcome="answered", answer="That follows from the union bound [e1].")
    elif kind == "nonexact_abstain":
        turn["answer"] += " The bound is always tight."
    result = review_turn(FixedReview(), history, script, turn)
    assert result == {**judgments, "context_retained": kind == "clean_abstain", "review_attempts": 1}

    # Expected-abstain follow-ups stay in the denominator; failed turns stay misses
    # even if a stale review says context was retained.
    failed = {**turn, "ordinal": 3, "status": "failed", "answer": None}
    summary = summarize(
        [dict(dialogue_id="probability-l1-3", turns=[turn, failed])],
        [
            dict(dialogue_id="probability-l1-3", ordinal=2, **result),
            dict(dialogue_id="probability-l1-3", ordinal=3, context_retained=True),
        ],
        dict(calls=1, nano_usd=1, pending=0, blocked=None),
        {"max_calls": 400},
        None,
        False,
    )
    assert summary["metrics"]["context_retention_rate"] == (0.5 if kind == "clean_abstain" else 0)
    assert summary["metrics"]["protocol_failure_rate"] == 0.5
    assert summary["metrics"]["no_evidence_abstain_rate"] == 0


def test_over_abstain_cascade_split_preserves_total_and_denominator():
    from lecturelens_real_eval.tutor.contracts import ABSTENTION

    script = dict(expected_insufficient=False, context_followup=True, socratic=False)
    base = dict(
        status="completed",
        outcome="insufficient_evidence",
        answer=ABSTENTION,
        citations=[],
        citation_validity=[],
        latency_s=0.1,
        script=script,
    )
    turns = [dict(base, ordinal=i) for i in range(1, 7)]
    turns[0].update(status="failed", outcome="failed", answer=None)
    turns[2].update(script={**script, "expected_insufficient": True})
    turns[3].update(status="cancelled", outcome="cancelled", answer=None)
    result = summarize(
        [dict(dialogue_id="cascade", turns=turns)],
        [],
        dict(calls=1, nano_usd=1, pending=0, blocked=None),
        {"max_calls": 400},
        None,
        False,
    )
    assert result["metrics"]["over_abstain_count"] == 3
    assert result["metrics"]["over_abstain_rate"] == 3 / 5
    assert result["metrics"]["over_abstain_cascade_count"] == 2
    assert result["metrics"]["over_abstain_non_cascade_count"] == 1
    assert result["over_abstain_cascade_turns"] == [("cascade", 2), ("cascade", 5)]
    assert result["over_abstain_non_cascade_turns"] == [("cascade", 6)]
    assert result["over_abstain_turns"] == [("cascade", 2), ("cascade", 5), ("cascade", 6)]


def test_union_bound_correction_preserves_every_other_byte_and_expectation():
    import hashlib

    # Byte-for-byte eval/p8-tutor files from 970bd00b84a18e8ea04584e65a36e887061db666.
    # Pin the historical baseline independently of checkout depth and current inputs.
    fixtures = Path(__file__).parent / "fixtures/p8_tutor"
    original = (fixtures / "dialogues-970bd00.json").read_bytes()
    assert hashlib.sha256(original).hexdigest() == (
        "8d8ca2b8f9ca0c04f433cc733eb3a663456fbdb956532cb0d23c79593b670fea"
    )
    thresholds = (fixtures / "thresholds-970bd00.json").read_bytes()
    assert hashlib.sha256(thresholds).hexdigest() == (
        "21d48ea5acd1fd63660fecd5ea03012aa5920ef048e0ff65430b68285be5b5da"
    )
    current = (DATA / "dialogues.json").read_bytes()
    before, after = json.loads(original), json.loads(current)
    target = next(d for d in after["dialogues"] if d["dialogue_id"] == "probability-l1-3")
    assert all(t["expected_insufficient"] for t in target["turns"])
    for t in target["turns"][:3]:
        assert t["zero_hit_terms"] == ["union"]
    for d in before["dialogues"]:
        if d["dialogue_id"] == "probability-l1-3":
            for t in d["turns"][:3]:
                t.update(expected_insufficient=True, zero_hit_terms=["union"])
    assert after == before

    def outside(data):
        start = data.index(b'    {\n      "dialogue_id": "probability-l1-3"')
        end = data.index(b'    {\n      "dialogue_id":', start + 1)
        return data[:start] + data[end:]

    assert hashlib.sha256(outside(current)).digest() == hashlib.sha256(outside(original)).digest()
    # Reversing exactly the approved fields must reconstruct the entire original file.
    reverted = current.replace(
        b'"expected_insufficient": true,\n          "socratic": false,\n          "zero_hit_terms": [\n            "union"\n          ]',
        b'"expected_insufficient": false,\n          "socratic": false',
    )
    assert reverted == original
    assert (DATA / "thresholds.json").read_bytes() == thresholds


@pytest.mark.parametrize("declaration", ["wrong", "superset"])
def test_fake_runner_ignores_provider_declaration_and_publishes_inline_ids(isolated, declaration):
    dsn, directory = isolated
    fake = fake_transport()

    def legacy(request):
        result = fake.handle_request(request)
        wire = json.loads(result.content)
        function = wire["choices"][0]["message"]["tool_calls"][0]["function"]
        if function["name"] == "finish_tutor_turn":
            args = json.loads(function["arguments"])
            ids = citation_ids(args)
            args["evidence_ids"] = (
                ["v2-unknown-l1-p99-e99"] if declaration == "wrong" else ids + ["v2-unknown-l1-p99-e99"]
            )
            function["arguments"] = json.dumps(args)
        return httpx.Response(200, json=wire)

    result = run_evaluation(
        dsn,
        directory / "legacy.jsonl",
        "legacy",
        TutorPolicy(),
        transport=httpx.MockTransport(legacy),
        output_root=directory,
        dialogue_ids=["algorithms-l1-1"],
    )
    assert result["fatal"] is None and result["metrics"]["protocol_failure_rate"] == 0
    assert result["accounting"]["calls"] == 9 and result["accounting"]["blocked"] is None
    dialogue = json.loads((directory / "legacy/dialogues.jsonl").read_text())
    for turn in dialogue["turns"]:
        proposal = turn["proposals"][-1]["arguments"]
        assert [c["evidence_id"] for c in turn["citations"]] == citation_ids(proposal)
        assert turn["answer"] == proposal["text"]


def test_fake_runner_downgrades_context_after_unpublished_turn(isolated):
    dsn, directory = isolated
    fake = fake_transport()
    rejected = False

    def unpublished(request):
        nonlocal rejected
        result = fake.handle_request(request)
        wire = json.loads(result.content)
        function = wire["choices"][0]["message"]["tool_calls"][0]["function"]
        if function["name"] == "finish_tutor_turn" and not rejected:
            rejected = True
            args = json.loads(function["arguments"])
            args["text"] = "No citations"
            function["arguments"] = json.dumps(args)
        return httpx.Response(200, json=wire)

    result = run_evaluation(
        dsn,
        directory / "cascade.jsonl",
        "cascade",
        TutorPolicy(),
        transport=httpx.MockTransport(unpublished),
        output_root=directory,
        dialogue_ids=["algorithms-l1-1"],
    )
    assert result["fatal"] is None and result["metrics"]["protocol_failure_rate"] == 1 / 3
    dialogue = json.loads((directory / "cascade/dialogues.jsonl").read_text())
    assert dialogue["turns"][0]["status"] == "failed" and dialogue["turns"][0]["answer"] is None
    assert dialogue["turns"][1]["status"] == "completed" and dialogue["turns"][1]["outcome"] == "answered"
    reviews = [json.loads(line) for line in (directory / "cascade/reviews.jsonl").read_text().splitlines()]
    assert reviews[0]["ordinal"] == 2 and reviews[0]["context_retained"] is False
    assert reviews[1]["context_retained"] is True


@pytest.mark.parametrize("failures", [2, 3])
@pytest.mark.parametrize("fault", ["schema", "request"])
def test_reviewer_retry_is_bounded_audited_and_continues_suite(isolated, failures, fault):
    dsn, directory = isolated
    fake = fake_transport()
    review_calls = 0

    def flaky_review(request):
        nonlocal review_calls
        payload = json.loads(request.content)
        if payload["model"] == "deepseek-v4-pro":
            review_calls += 1
            if review_calls <= failures:
                if fault == "request":
                    return httpx.Response(503, text="private provider body")
                # A parsed tool call with incomplete Review fields reproduces the live failure.
                return response("review_tutor_turn", {"answer_supported": True})
        return fake.handle_request(request)

    result = run_evaluation(
        dsn,
        directory / "review-retry.jsonl",
        "review-retry",
        TutorPolicy(),
        transport=httpx.MockTransport(flaky_review),
        output_root=directory,
        dialogue_ids=["algorithms-l1-1", "algorithms-l1-2"],
    )
    assert result["verdict"] == "PARTIAL" and result["fatal"] is None
    assert result["dialogues"] == 2 and result["turns"] == result["reviewed_turns"] == 6
    assert result["accounting"]["calls"] == 20 and review_calls == 8
    assert result["accounting"]["blocked"] is None and result["accounting"]["pending"] == 0
    output = directory / "review-retry"
    reviews = [json.loads(line) for line in (output / "reviews.jsonl").read_text().splitlines()]
    assert len(reviews) == 6 and len({(r["dialogue_id"], r["ordinal"]) for r in reviews}) == 6
    assert reviews[0]["review_attempts"] == 3
    assert all(r["review_attempts"] == 1 and "error" not in r for r in reviews[1:])
    if failures == 3:
        assert reviews[0] == dict(
            dialogue_id="algorithms-l1-1",
            ordinal=1,
            error="REAL_EVAL_REVIEW_FAILED",
            review_attempts=3,
        )
        assert result["metrics"]["answer_supported_rate"] < 1
    else:
        assert reviews[0]["answer_supported"] and "error" not in reviews[0]
    rows = [json.loads(line) for line in (output / "dialogues.jsonl").read_text().splitlines()]
    assert all(t["status"] == "completed" and t["model_calls"] == 2 for d in rows for t in d["turns"])
    # Every review attempt has its own durable reservation and settlement, mirrored in PG.
    ledger = Ledger(
        dsn,
        directory / "review-retry.jsonl",
        "review-retry",
        replace(TutorPolicy(), candidate_sha256=result["candidate_sha256"]),
    )
    assert ledger.check() == result["accounting"]
    records = [json.loads(line) for line in ledger.path.read_text().splitlines()]
    review_records = [r for r in records if r["model"] == "deepseek-v4-pro"]
    assert len(review_records) == 16
    assert sum(r["state"] == "reserved" for r in review_records) == 8
    failed = [r for r in review_records if r["state"] == "failed"]
    assert len(failed) == failures
    code = "REAL_EVAL_PROTOCOL_FAILURE" if fault == "schema" else "REAL_EVAL_REQUEST_FAILED"
    assert all(r["error"] == code and r["charged_nano_usd"] == r["reserved_nano_usd"] for r in failed)
    assert "private provider body" not in json.dumps(records) + (output / "reviews.jsonl").read_text()


@pytest.mark.parametrize("code", ["REAL_EVAL_REVIEW_FAILED", "REAL_EVAL_DURABILITY_REQUIRED", "unexpected"])
def test_reviewer_does_not_retry_other_errors_and_preserves_hard_stops(isolated, monkeypatch, code):
    original = Channel.request
    review_calls = 0

    def fail_review(self, *args, **kwargs):
        nonlocal review_calls
        if kwargs.get("purpose") == "review":
            review_calls += 1
            raise ValueError("private details") if code == "unexpected" else EvalError(code)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Channel, "request", fail_review)
    dsn, directory = isolated
    result = run_evaluation(
        dsn,
        directory / "other-error.jsonl",
        "other-error",
        TutorPolicy(),
        output_root=directory,
        dialogue_ids=["algorithms-l1-1"],
    )
    hard = code == "REAL_EVAL_DURABILITY_REQUIRED"
    assert result["fatal"] == (code if hard else None)
    assert result["turns"] == review_calls == (1 if hard else 3)
    reviews = [
        json.loads(line) for line in (directory / "other-error/reviews.jsonl").read_text().splitlines()
    ]
    assert all(r["error"] == "REAL_EVAL_REVIEW_FAILED" and r["review_attempts"] == 1 for r in reviews)
    assert "private details" not in json.dumps(result) + json.dumps(reviews)


def test_reviewer_retry_stops_on_run_budget_block(isolated):
    dsn, directory = isolated
    fake = fake_transport()

    def invalid_review(request):
        if json.loads(request.content)["model"] == "deepseek-v4-pro":
            return response("review_tutor_turn", {"answer_supported": True})
        return fake.handle_request(request)

    result = run_evaluation(
        dsn,
        directory / "review-budget.jsonl",
        "review-budget",
        TutorPolicy(max_calls=3),
        transport=httpx.MockTransport(invalid_review),
        output_root=directory,
        dialogue_ids=["algorithms-l1-1", "algorithms-l1-2"],
    )
    assert result["fatal"] == result["accounting"]["blocked"] == "REAL_EVAL_BUDGET_EXHAUSTED"
    assert result["verdict"] == "FAIL" and result["turns"] == 1
    assert result["accounting"]["calls"] == 3 and result["accounting"]["pending"] == 0
    record = json.loads((directory / "review-budget/reviews.jsonl").read_text())
    assert record["error"] == "REAL_EVAL_REVIEW_FAILED" and record["review_attempts"] == 2
