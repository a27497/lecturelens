"""Stage-specific retained v14 replay; no paid sender or product mutation."""

import json
import os
import sys
import uuid
from pathlib import Path

import httpx
import psycopg
import pytest
import v14_delivery_diagnosis as D
from psycopg import sql
from psycopg.conninfo import make_conninfo
from pydantic import ValidationError

sys.path.insert(0, str(D.BASE))
import run_fresh as E
from lecturelens_real_eval.tutor.contracts import Finish, validate_proposal


@pytest.fixture(autouse=True)
def no_real_provider(monkeypatch):
    assert os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") == "1"
    original = os.environ.get

    def guarded_get(key, *args):
        if key in {"AGENT_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"}:
            pytest.fail("Credential access forbidden in diagnosis")
        return original(key, *args)

    monkeypatch.setattr(os.environ, "get", guarded_get)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kw: pytest.fail("Real transport forbidden"))


@pytest.fixture
def isolated():
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    schema = "v14_diagnosis_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        yield make_conninfo(dsn, options=f"-csearch_path={schema},public")
    finally:
        with psycopg.connect(dsn) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def output():
    return Path(os.environ["V14_DIAGNOSIS_OUTPUT"])


def test_exact32_frame_replay_and_dependency_propagation(isolated):
    frames = D.retained_frames()
    sent = []

    def send(request):
        n = len(sent)
        assert request.content == (D.RUN / f"wire/{n + 1:03d}-request.json").read_bytes()
        frame = frames[n]
        sent.append(n)
        call = frame["call"]
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
                                for p in frame["proposals"]
                            ]
                        ),
                    )
                ],
            ),
        )

    out = output() / "retained32-replay"
    args = E.parser().parse_args(
        [
            "--mock",
            "--agent",
            E.contract.CANDIDATE,
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
    result = E.run(args, dsn=isolated, transport=httpx.MockTransport(send))
    replay, original = D.lines(out / "turns.jsonl"), D.lines(D.RUN / "turns.jsonl")
    assert len(sent) == 32
    assert tuple(result[k] for k in ("completed", "failed", "skipped", "missing")) == (10, 2, 4, 0)
    for new, old in zip(replay, original, strict=True):
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
        ):
            assert new.get(key) == old.get(key), (old["turn_key"], key)
    assert replay[8]["error_code"] == replay[14]["error_code"] == "TUTOR_FINISH_FORMAT_INVALID"
    assert all(replay[n]["root_failure"] == "v14-sheets-portability:1" for n in (9, 10, 11))
    assert replay[15]["root_failure"] == "v14-sheets-lineends:3"
    _, independent = D.context(26)
    assert independent["history"] == [] and independent["summary"] == ""
    assert replay[12]["status"] == "completed"
    assert result["reviewer_calls"] == 0 and result["ledger"]["pending"] == 0
    assert result["ledger"]["nano_usd"] == 46152000
    with psycopg.connect(isolated) as conn:
        events = [r[0] for r in conn.execute("SELECT record FROM p8_tutor_real_event ORDER BY sequence")]
        counts = [
            conn.execute("SELECT count(*) FROM " + table).fetchone()[0]
            for table in ("tutor_turn", "tutor_session")
        ]
    assert events == D.lines(out / "ledger.jsonl") and len(events) == 64 and counts == [12, 4]
    (output() / "replay-result.json").write_text(
        json.dumps(
            dict(
                result=result,
                exact_original_wire_requests=32,
                retained_answers_unchanged=10,
                PostgreSQL_event_agreement=True,
                PostgreSQL_turns=12,
                PostgreSQL_sessions=4,
                real_requests=0,
                cost_usd="0",
                ledger_amounts="SIMULATED_RETAINED_USAGE_NOT_NEW_CHARGES",
                quality_improvement="NOT_RUN",
                reconstructed_response_envelopes=True,
                raw_response_bytes_replayed=False,
            ),
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("index,initial,repaired,proxy", [(0, 1982, 1799, 39463), (1, 1818, 1633, 48534)])
def test_original_size_failures_and_complete_repair_inputs(index, initial, repaired, proxy):
    details = D.analyze()["failures"][index]
    assert details["initial"]["chars"] == initial
    assert details["repair"]["chars"] == repaired
    assert details["turn_reserved_proxy"] == proxy < 64000
    assert details["exact_rejected_finish"] and details["exact_kept_evidence"]
    assert details["published_answer"] is None
    assert details["initial"]["completion_tokens"] < 1200
    assert details["repair"]["completion_tokens"] < 1200


@pytest.mark.parametrize(
    "char,count,valid",
    [
        ("a", 1599, True),
        ("a", 1600, True),
        ("a", 1601, False),
        ("中", 1600, True),
        ("😀", 1600, True),
        ("\n", 1600, True),
        ("\n", 1601, False),
    ],
)
def test_character_boundary_is_decoded_codepoints(char, count, valid):
    proposal = validate_proposal("finish_tutor_turn", dict(outcome="answered", text=char * count))
    assert len(proposal.text) == count
    # Schema accepts proposals for the existing one-shot repair; publication differs.
    args = {**proposal.model_dump(), "evidence_ids": []}
    if valid:
        assert Finish.model_validate(args).text == char * count
    else:
        with pytest.raises(ValidationError):
            Finish.model_validate(args)


def test_excel_and_scheduled_vs_observed_metric_evidence():
    analysis = D.analyze()
    assert analysis["excel"]["evidence_in_context"] and analysis["excel"]["evidence_cited"]
    assert analysis["excel"]["unused_hard_char_capacity"] == 315
    refusals, contextual = analysis["refusal_positions"], analysis["context_positions"]
    assert len(refusals) == 4 and len(contextual) == 10
    assert [r["status"] for r in refusals] == ["completed", "completed", "SKIPPED", "SKIPPED"]
    assert sum(r["status"] == "completed" for r in contextual) == 6
    assert sum(r["status"] == "SKIPPED" for r in contextual) == 4
    assert all(
        r["answer"] == "I don't know from this course. Try asking about a topic covered in this lecture."
        for r in refusals
        if r["status"] == "completed"
    )
    assert analysis["citation_annotation_arithmetic"] == dict(
        explicit_pairs=36, supported_pairs=36, requiring_claims=42, direct_supported=35, frozen_supported=42
    )


def test_every_request_contains_only_actual_completed_session_history():
    checks = D.analyze()["actual_history_checks"]
    assert len(checks) == 32 and all(c["exact_actual_history"] for c in checks)


def test_manual_feasibility_is_not_a_model_result():
    samples = D.read(output() / "manual-feasibility.json")
    assert samples["kind"] == "HUMAN_AUTHORED_SOURCE_AUDITED_FEASIBILITY_ONLY"
    for sample in samples["samples"]:
        assert len(sample["text"]) <= 1600
        assert (
            D.citation_cost(sample["text"])["citation_occurrences"] == sample["original_marker_occurrences"]
        )
        assert len(sample["required_point_checks"]) == 4
        assert all(p["source_audited"] for p in sample["required_point_checks"])
    assert samples["model_quality_improvement"] == "NOT_RUN"
