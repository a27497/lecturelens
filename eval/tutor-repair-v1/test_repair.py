"""No-cost regressions: source context, decoded telemetry and durable Mock execution."""

# ruff: noqa: E402 -- local versioned eval imports require explicit paths

import copy
import gzip
import json
import os
import sys
import uuid
import zlib
from unittest.mock import patch

import httpx
import psycopg
import pytest
import repair_check as contract
import repair_run as pilot
from lecturelens_real_eval.channel import EvalError as AuthorityError
from lecturelens_real_eval.tutor.grounded_runtime import (
    FINISH_LIMITS,
    SYSTEM,
    GroundedTutorRuntime,
    PassageAuthority,
    passages,
)
from lecturelens_real_eval.tutor.observed_channel import (
    DecodedMetadataTransport,
    ObservedChannel,
    metadata,
)
from lecturelens_real_eval.tutor_channel import EvalError
from offline_audit import MemoryLedger
from psycopg import sql
from psycopg.conninfo import make_conninfo

sys.path.insert(1, str(contract.ROOT / "agent-service/tests"))
import test_tutor_python_contract as old

PLAN = contract.HERE / "retest-plan.json"


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    original = os.environ.get

    def guarded(key, *args):
        if key in {"AGENT_LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"}:
            pytest.fail("offline tests must not read provider credentials")
        return original(key, *args)

    monkeypatch.setattr(os.environ, "get", guarded)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: pytest.fail("real transport forbidden"))


def scope_data():
    return contract.parent.load_plan(
        contract.ROOT / "eval/tutor-python-contract-v1/development-pilot-v1.json"
    )


def test_identity_scope_and_source_drift_fail_closed(tmp_path, monkeypatch):
    assert contract.verify_candidate() != contract.PARENT_SHA
    plan, scripts, snapshot = contract.load_plan(PLAN)
    assert plan["counts"] == dict(courses=2, sessions=2, turns=8)
    assert [s["dialogue_id"] for s in scripts] == ["python-01", "sheets-01"]
    assert all(v["split"] == "development" for v in snapshot["lectures"].values())
    bad = tmp_path / "plan.json"
    bad.write_text(json.dumps({**old.read(PLAN), "turn_keys": []}))
    with pytest.raises(ValueError, match="REPAIR_PLAN_CHANGED"):
        contract.load_plan(bad)
    real_digest = contract.digest
    monkeypatch.setattr(
        contract, "digest", lambda p: "0" * 64 if str(p).endswith("grounded_runtime.py") else real_digest(p)
    )
    with pytest.raises(ValueError, match="REPAIR_INPUT_CHANGED"):
        contract.verify_candidate()
    assert contract.parent.verify_candidate() == contract.PARENT_SHA


def test_passage_provenance_bounds_and_scope_checks():
    _, _, snapshot = scope_data()
    before = copy.deepcopy(snapshot)
    authority = PassageAuthority(snapshot)
    scope = dict(owner_id=811012, course_id="test-python", revision=1)
    authority.register(scope, "carpentries-python")
    originals = {e["evidence_id"]: e for e in snapshot["lectures"]["carpentries-python"]["evidence"]}
    for e in authority.rows(scope):
        members = [originals[i] for i in e["member_evidence_ids"]]
        assert e["text"] == "\n\n".join(m["text"] for m in members)
        assert len(members) <= 6
        assert len(e["text"]) <= 1000 or len(members) == 1
        assert e["line_start"] == members[0]["line_start"] and e["line_end"] == members[-1]["line_end"]
        assert len({m["source_path"] for m in members}) == 1
    assert snapshot == before
    assert passages(before["lectures"]["carpentries-python"]["evidence"]) == authority.rows(scope)
    for changed in ({**scope, "owner_id": 1}, {**scope, "revision": 2}):
        with pytest.raises(AuthorityError, match="AUTHORITY_SCOPE"):
            authority.read(changed, "SEARCH", query="dtype")
    with pytest.raises(AuthorityError, match="CITATION_FABRICATED"):
        authority.read(scope, "READ", evidence_ids=[next(iter(originals))])


@pytest.mark.parametrize(
    "course,query,lines",
    [
        ("carpentries-python", "numpy array type dtype integer data type of entries", [142, 149, 153, 157]),
        ("carpentries-python", "zero based row column index counting", [202]),
        (
            "carpentries-spreadsheets",
            "Formatting problems episode 3 one tab per day workbook structure tidy data",
            [58, 62, 67],
        ),
        (
            "carpentries-spreadsheets",
            "tidy data one header row per table, no repeated header rows inside data",
            [69, 73],
        ),
    ],
)
def test_retrieval_keeps_code_output_or_related_guidance(course, query, lines):
    _, _, snapshot = scope_data()
    a = PassageAuthority(snapshot)
    scope = dict(owner_id=811012, course_id=course, revision=1)
    a.register(scope, course)
    found = a.read(scope, "SEARCH", query=query)["evidence"]
    by_id = {e["evidence_id"]: e for e in a.rows(scope)}
    assert len(found) <= 8
    assert all(
        any(
            by_id[e["evidence_id"]]["line_start"] <= line <= by_id[e["evidence_id"]]["line_end"]
            for e in found
        )
        for line in lines
    )


def test_prompt_keeps_brackets_limits_and_no_reference_answers():
    runtime = GroundedTutorRuntime(None, None)
    with patch.object(runtime, "read_evidence", return_value=[]):
        messages, schemas, amount = runtime.request(
            {"summary": ""},
            {"learner_text": "two tasks", "socratic": False},
            {"selected": [], "observations": []},
            [],
        )
    assert messages[0]["content"] == SYSTEM
    assert "ordinal positions" in SYSTEM and "every part" in SYSTEM
    assert "Never rewrite indexing as a function call" in SYSTEM and old.ABSTENTION in SYSTEM
    assert "4 distinct evidence ids" in FINISH_LIMITS
    assert amount == len(json.dumps([messages, schemas], ensure_ascii=False).encode()) + 1200
    for case in old.FIXTURE["cases"].values():
        assert all(code not in SYSTEM for code in case["code_snippets"])
    assert "reference" not in json.loads(messages[-1]["content"])


def body(usage=None):
    return {
        "id": "MOCK-response-1",
        "model": "MOCK-reported-alias",
        "system_fingerprint": "MOCK-fp",
        "usage": usage
        if usage is not None
        else {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
            "prompt_cache_hit_tokens": 6,
            "prompt_cache_miss_tokens": 4,
        },
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "search_tutor_evidence",
                                "arguments": '{"query":"ordinary QA"}',
                            },
                        }
                    ]
                },
            }
        ],
    }


class Chunks(httpx.SyncByteStream):
    def __init__(self, raw):
        self.raw, self.closed = raw, False

    def __iter__(self):
        for n in range(0, len(self.raw), 17):
            yield self.raw[n : n + 17]

    def close(self):
        self.closed = True


@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate", "preconsumed"])
def test_decoded_capture_preserves_bytes_association_and_usage(encoding, tmp_path):
    data = body()
    raw = json.dumps(data).encode()
    encoded = (
        gzip.compress(raw) if encoding == "gzip" else zlib.compress(raw) if encoding == "deflate" else raw
    )
    stream = Chunks(encoded)
    headers = {
        "x-request-id": "MOCK-request-1",
        "authorization": "DO_NOT_LOG",
        "set-cookie": "DO_NOT_LOG",
        "content-encoding": encoding if encoding != "preconsumed" else "identity",
    }

    def send(request):
        if encoding == "preconsumed":
            return httpx.Response(200, json=data, headers=headers)
        return httpx.Response(200, stream=stream, headers=headers)

    transport = DecodedMetadataTransport(httpx.MockTransport(send))
    with httpx.Client(transport=transport) as client:
        response = client.post("https://mock.invalid", content=b"non-sensitive request")
        assert response.content == raw if encoding != "preconsumed" else response.json() == data
    assert transport.metadata["returned_model"] == data["model"]
    assert transport.metadata["response_id"] == data["id"]
    assert transport.metadata["request_id"] == "MOCK-request-1"
    assert transport.metadata["usage"] == data["usage"]
    assert transport.metadata["cache"] == dict(hit_tokens=6, miss_tokens=4, status="PROVIDER_REPORTED")
    assert "DO_NOT_LOG" not in json.dumps(transport.metadata)
    if encoding != "preconsumed":
        assert stream.closed


@pytest.mark.parametrize("value", [None, [], "bad", True, -1, 1.2, {"x": 1}])
def test_missing_invalid_core_usage_never_becomes_zero(value):
    data = body({"prompt_tokens": value, "completion_tokens": 2})
    result = metadata(data)
    assert result["cache"] == dict(hit_tokens=None, miss_tokens=None, status="UNKNOWN")
    assert "CORE_USAGE_UNKNOWN" in result["anomalies"]
    assert result["usage"].get("prompt_tokens") != 0


def test_cache_partial_conflicts_and_secrets_are_explicit():
    for usage, status in [
        ({"prompt_tokens": 10, "completion_tokens": 2}, "UNKNOWN"),
        (
            {"prompt_tokens": 10, "completion_tokens": 2, "prompt_tokens_details": {"cached_tokens": 6}},
            "PARTIAL",
        ),
        ({"prompt_tokens": 10, "prompt_cache_hit_tokens": 6, "prompt_cache_miss_tokens": 7}, "INCONSISTENT"),
        (
            {
                "prompt_tokens": 10,
                "prompt_cache_hit_tokens": 6,
                "prompt_tokens_details": {"cached_tokens": 7},
            },
            "INCONSISTENT",
        ),
        ({"prompt_cache_hit_tokens": -1}, "INCONSISTENT"),
    ]:
        assert metadata(body(usage))["cache"]["status"] == status
    data = body()
    data.update(model="SECRET", id="SECRET", system_fingerprint="SECRET")
    assert "SECRET" not in json.dumps(metadata(data, "SECRET"))
    assert metadata(body({"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 99}))["anomalies"] == [
        "TOKEN_TOTAL_MISMATCH"
    ]


def test_compressed_channel_and_pre_send_rejection_do_not_reuse_metadata(tmp_path):
    sends = []

    class OnceLedger(MemoryLedger):
        def reserve(self, raw, max_tokens):
            if self.rows:
                raise EvalError("REAL_EVAL_BUDGET_EXHAUSTED")
            return super().reserve(raw, max_tokens)

    def send(request):
        sends.append(request)
        return httpx.Response(
            200,
            stream=Chunks(gzip.compress(json.dumps(body()).encode())),
            headers={"content-encoding": "gzip", "x-request-id": "MOCK-id"},
        )

    channel = ObservedChannel(
        OnceLedger(),
        records=tmp_path / "calls.jsonl",
        transport=DecodedMetadataTransport(httpx.MockTransport(send)),
    )
    schemas = [{"type": "function", "function": {"name": "search_tutor_evidence"}}]
    result = channel.request([], schemas)
    assert result["usage"] == {"prompt_tokens": 10, "completion_tokens": 2}
    assert channel.turn_calls[0]["cache"]["hit_tokens"] == 6
    with pytest.raises(EvalError, match="BUDGET_EXHAUSTED"):
        channel.request([], schemas)
    row = channel.turn_calls[-1]
    assert len(sends) == 1 and row["capture_status"] == "NOT_SENT"
    assert row["usage"] is row["returned_model"] is row["request_id"] is row["ledger_call_id"] is None


@pytest.mark.parametrize(
    "fault", ["protocol", "usage_missing", "invalid_json", "oversize", "timeout", "http"]
)
def test_failure_metadata_and_unknown_usage_retained_without_retries(fault, tmp_path):
    sends = []

    def send(request):
        sends.append(request)
        if fault == "timeout":
            raise httpx.ReadTimeout("must not leak")
        data = body()
        if fault == "protocol":
            data["choices"] = []
        if fault == "usage_missing":
            data.pop("usage")
        raw = (
            b"bad"
            if fault == "invalid_json"
            else b"x" * (128 * 1024 + 1)
            if fault == "oversize"
            else json.dumps(data).encode()
        )
        return httpx.Response(
            401 if fault == "http" else 200, stream=Chunks(raw), headers={"x-request-id": "MOCK-id"}
        )

    ledger = MemoryLedger()
    channel = ObservedChannel(
        ledger,
        records=tmp_path / "calls.jsonl",
        transport=DecodedMetadataTransport(httpx.MockTransport(send)),
    )
    with pytest.raises(EvalError):
        channel.request([], [{"type": "function", "function": {"name": "search_tutor_evidence"}}])
    assert len(sends) == len(channel.turn_calls) == 1
    row = channel.turn_calls[0]
    assert row["status"] == "FAILED" and row["supplier_billed_usd"] is None
    assert row["usage_source"] == "MOCK_NOT_BILLABLE"
    if fault == "protocol":
        assert row["usage"] == body()["usage"] and row["returned_model"] == body()["model"]
    elif fault != "usage_missing":
        assert row["usage"] is None
    assert "must not leak" not in (tmp_path / "calls.jsonl").read_text()


@pytest.fixture
def isolated():
    dsn = make_conninfo(os.environ["AGENT_TEST_DATABASE_URL"], dbname="lecturelens_agent_acceptance")
    schema = "tutor_repair_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    yield make_conninfo(dsn, options=f"-csearch_path={schema},public")
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def options(tmp_path, *caps):
    return pilot.parser().parse_args(
        [
            "--plan",
            str(PLAN),
            "--agent",
            contract.CANDIDATE,
            "--model",
            "deepseek-flash",
            "--output",
            str(tmp_path / "run"),
            *caps,
        ]
    )


def test_default_never_starts_database_and_reviewer_never_dispatches(tmp_path):
    with patch.object(pilot.legacy, "Ledger", side_effect=AssertionError("DB forbidden")):
        result = pilot.run(options(tmp_path))
    assert result["real_calls"] == "NOT_RUN" and result["agent"] == contract.CANDIDATE
    c = ObservedChannel(
        MemoryLedger(),
        records=tmp_path / "calls.jsonl",
        transport=DecodedMetadataTransport(httpx.MockTransport(lambda r: pytest.fail("egress"))),
    )
    with pytest.raises(EvalError, match="REVIEWER_DISABLED"):
        c.request([], [], purpose="review")
    assert not c.records.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("agent", contract.parent.CANDIDATE),
        ("model", "other"),
        ("reviewer", "on"),
        ("concurrency", 2),
        ("max_calls", 41),
        ("max_usd", "0"),
    ],
)
def test_new_adapter_rejects_scope_configuration_drift_before_database(tmp_path, field, value):
    args = options(tmp_path, "--mock", "--max-calls", "40", "--max-usd", "0.70")
    setattr(args, field, value)
    with patch.object(pilot.legacy, "Ledger", side_effect=AssertionError("DB forbidden")):
        with pytest.raises((ValueError, EvalError)):
            pilot.run(args)


def test_live_switch_is_still_required_without_credential_lookup(tmp_path, monkeypatch):
    args = options(tmp_path, "--live", "--max-calls", "40", "--max-usd", "0.70")
    monkeypatch.delenv("LECTURELENS_REAL_EVAL", raising=False)
    with pytest.raises(ValueError, match="PRICING_AND_CAP"):
        pilot.preflight(args)
    args.ack_ledger_not_billing_cap, args.pricing = True, str(pilot.PRICING)
    # Pricing freshness is tested by the unchanged parent adapter; isolate the independent opt-in here.
    with patch.object(pilot, "check_pricing", return_value={}):
        with pytest.raises(EvalError, match="SWITCH_REQUIRED"):
            pilot.preflight(args)


@pytest.mark.parametrize(
    "cap,money,expected_calls", [(40, "0.70", 16), (1, "0.70", 1), (40, "0.000000001", 0)]
)
def test_eight_turn_mock_and_caps(isolated, tmp_path, cap, money, expected_calls):
    result = pilot.run(options(tmp_path, "--mock", "--max-calls", str(cap), "--max-usd", money), dsn=isolated)
    rows = [json.loads(line) for line in (tmp_path / "run/turns.jsonl").read_text().splitlines()]
    assert [r["turn_key"] for r in rows] == old.read(PLAN)["turn_keys"]
    assert result["ledger_accounting"]["calls"] == expected_calls
    assert result["reviewer_calls"] == 0
    assert result["quality_status"] == result["real_cost_status"] == "NOT_RUN"
    if cap == 40 and money == "0.70":
        assert result["completed_turns"] == 8 and result["mechanics_status"] == "COMPLETE"
        records = [json.loads(line) for line in (tmp_path / "run/calls.jsonl").read_text().splitlines()]
        assert len(records) == 16 and all(r["ledger_call_id"] for r in records)
        assert all(r["cache"]["status"] == "UNKNOWN" for r in records)
    else:
        assert result["failed_turns"] == 1 and result["missing_result_turns"] == 7
        assert result["mechanics_status"] == "INCOMPLETE"
        if expected_calls == 0:
            record = json.loads((tmp_path / "run/calls.jsonl").read_text())
            assert record["capture_status"] == "NOT_SENT" and record["ledger_call_id"] is None


@pytest.mark.parametrize("did", old.FIXTURE["sessions"])
def test_fixed_development_answers_new_context_publication_and_scoring(isolated, tmp_path, did):
    # Controlled source observations isolate contract/publication. Not a model or retrieval-quality test.
    snapshot, scripts = old.select("development")

    class Authority(PassageAuthority):
        ids = ()

        def read(self, scope, action="CHECK", **args):
            return (
                super().read(scope, "READ", evidence_ids=self.ids)
                if action == "SEARCH"
                else super().read(scope, action, **args)
            )

    class Provider(old.FixedProvider):
        def decide(self, messages, schemas, timeout):
            assert messages[0]["content"] == SYSTEM
            with patch.object(old, "SYSTEM", SYSTEM):
                return super().decide(messages, schemas, timeout)

    authority, provider = Authority(snapshot), Provider()
    runtime = GroundedTutorRuntime(old.TutorStore(isolated), authority, provider)
    runtime.initialize()
    script = next(d for d in scripts if d["dialogue_id"] == did)
    scope = dict(owner_id=811012, course_id="fixed-" + uuid.uuid4().hex, revision=1)
    authority.register(scope, script["lecture_id"])
    scope["session_id"] = runtime.command(old.Command(**scope, operation="CREATE", request_key="s"))[
        "session"
    ]["session_id"]
    rows, labels = [], {}
    try:
        for n, task in enumerate(script["turns"], 1):
            key = f"{did}:{n}"
            if key not in old.FIXTURE["cases"]:
                break
            answer, ids, claims = old.render(key, authority.snapshot["lectures"][script["lecture_id"]])
            assert len(ids) <= 4
            authority.ids, provider.answer = ids, answer
            provider.outcome = old.FIXTURE["cases"][key]["expected_outcome"]
            runtime.command(old.Command(**scope, operation="TURN", client_turn_id=str(n), text=task["text"]))
            runtime.execute(runtime.store.candidates()[0])
            turn = runtime.command(old.Command(**scope, operation="GET"))["turns"][-1]
            assert turn["status"] == "completed" and turn["answer"] == answer
            assert len(json.loads(provider.messages[-1][-1]["content"])["history"]) == n - 1
            evidence = {e["evidence_id"]: e for e in authority.rows(scope)}
            turn.update(
                turn_key=key,
                script=task,
                course_id=script["course_id"],
                dialogue_id=did,
                citations=[evidence[i] for i in ids],
                review=None,
            )
            label = dict(
                complete=True,
                overall_supported="supported",
                reason="CONSTRUCTED_OFFLINE_FIXTURE",
                task_correct=True,
                context_consistent=True,
                abstention_correct=True,
                claims=claims,
                citation_checks=[
                    dict(claim_id=c["claim_id"], evidence_id=i, label="supported", quote=evidence[i]["text"])
                    for c in claims
                    for i in c["citation_ids"]
                ],
            )
            old.validate_citations(label, turn)
            rows.append(turn)
            labels[key] = label
        result = old.summarize(dict(rows=rows, config={"data_kind": "MOCK"}), labels)
        assert result["quality_status"] == "MOCK_NOT_QUALITY"
        assert result["model_human_support_agreement"]["comparable"] == 0
        (tmp_path / f"{did}-constructed.json").write_text(
            json.dumps(dict(rows=rows, summary=result), default=str)
        )
    finally:
        runtime.close()
