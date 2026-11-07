"""Independent follow-up reproductions and opt-in v16 mechanisms, not model quality."""

import json
import os
from pathlib import Path

import httpx
import pytest
import test_tutor_v15 as legacy

from lecturelens_real_eval.tutor.verified_runtime import HINTS, VerifiedTutorRuntime, calculate

lab, offline = legacy.lab, legacy.offline
Provider, block, run = legacy.Provider, legacy.block, legacy.run


def retain(name, value):
    output = Path(os.environ["TUTOR_FOLLOWUP_OUTPUT"])
    (output / (name + ".json")).write_text(json.dumps(value, indent=2, default=str) + "\n")


def test_reproduce_v15_arbitrary_claim_in_answer_and_feedback(lab):
    def finish(body):
        return {
            "outcome": "answered",
            "blocks": [block(body, "Every loop cures influenza.")],
            "evaluation_blocks": [block(body, "Your reply proves permanent mastery.")],
        }

    result = run(lab, Provider(finish))
    retain("v15-a03-reproduction", result)
    assert result["status"] == "completed"
    assert "cures influenza" in result["answer"] and "permanent mastery" in result["evaluation"]


def test_reproduce_v15_paraphrased_complete_solution(lab):
    answer = "Add seventy-five, twenty and two to obtain ninety-seven. Can you repeat these steps?"
    result = run(
        lab,
        Provider(lambda body: {"outcome": "socratic_prompt", "blocks": [block(body, answer)]}),
        socratic=True,
    )
    retain("v15-a12-reproduction", result)
    assert result["status"] == "completed" and "ninety-seven" in result["answer"]


@pytest.fixture
def verified_lab(lab):
    store, authority, _, scope = lab
    runtime = VerifiedTutorRuntime(store, authority)
    runtime.initialize()
    try:
        yield store, authority, runtime, scope
    finally:
        runtime.close()


def excerpt(body):
    source = body["evidence"][0]
    return {"kind": "source", "evidence_id": source["evidence_id"], "text": source["text"][:100]}


def hint(body, intent="trace_state"):
    value = excerpt(body)
    return {"evidence_id": value["evidence_id"], "quote": value["text"], "intent": intent}


def test_verified_source_publication_retains_full_binding_and_restart(verified_lab):
    result = run(verified_lab, Provider(lambda body: {"outcome": "answered", "blocks": [excerpt(body)]}))
    assert result["status"] == "completed"
    assert result["citations"][0]["text"].startswith(result["answer"].split("\n", 1)[1].rsplit(" [", 1)[0])
    store, authority, _, scope = verified_lab
    from lecturelens_real_eval.tutor.contracts import Command

    restored = VerifiedTutorRuntime(store, authority).command(Command(**scope, operation="GET"))
    assert restored["turns"][0]["answer"] == result["answer"]
    retain("v16-source-publication", result)


@pytest.mark.parametrize(
    "text",
    [
        "Every loop cures influenza.",
        "所有循环都能保证永久掌握。",
        "Loops prove that every learner is correct.",
    ],
)
def test_verified_arbitrary_course_claim_cannot_use_real_anchor(verified_lab, text):
    provider = Provider(lambda body: {"outcome": "answered", "blocks": [{**excerpt(body), "text": text}]})
    result = run(verified_lab, provider)
    assert result["status"] == "failed" and result["error_code"] == "TUTOR_SUPPORT_INVALID"
    assert result["answer"] is None and not result["citations"] and len(provider.requests) == 3
    retain("v16-a03-rejection", result)


def test_verified_repairs_claim_without_dropping_source_content(verified_lab):
    def finish(body):
        item = excerpt(body)
        if "rejected_blocks" not in body:
            item["text"] = "A new unsupported assertion."
        return {"outcome": "answered", "blocks": [item]}

    provider = Provider(finish)
    result = run(verified_lab, provider)
    assert result["status"] == "completed" and len(provider.requests) == 3
    assert "unsupported assertion" not in result["answer"]


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("2 + 1 + 1", "4"),
        ("2 + 2*2**2 + 3*2**2", "22"),
        ("0.1+0.2", "3/10"),
        ("-7//2", "-4"),
        ("7%2", "1"),
        ("[2,2+1,2+1+1]", "[2, 3, 4]"),
        ("[range(1,4),range(1,4,2)]", "[[1, 2, 3], [1, 3]]"),
    ],
)
def test_verified_calculation_exact_bounded_arithmetic(expression, expected):
    assert calculate(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "x+1",
        "(2).__class__",
        "1/0",
        "2**99",
        "1e309",
        "True+1",
        "9**12*9**12",
        "[1][0]",
        "-[1]",
        "[1]+[2]",
        "range(1000000000)",
        "range(0,3,0)",
        "[x for x in range(3)]",
        "1" * 121,
    ],
)
def test_verified_calculation_rejects_code_and_capacity(expression):
    from lecturelens_agent.study.store import StudyError

    with pytest.raises(StudyError, match="TUTOR_CALCULATION_INVALID"):
        calculate(expression)


def test_verified_model_selects_calculation_controller_generates_conclusion(verified_lab):
    def finish(body):
        value = hint(body)
        return {
            "outcome": "answered",
            "blocks": [
                excerpt(body),
                {
                    "kind": "calculation",
                    "evidence_id": value["evidence_id"],
                    "quote": value["quote"],
                    "expression": "2+1+1",
                },
            ],
        }

    result = run(verified_lab, Provider(finish))
    assert result["status"] == "completed" and "Derived: 2+1+1 = 4" in result["answer"]
    retain("v16-calculation-publication", result)


@pytest.mark.parametrize("intent", list(HINTS))
def test_verified_socratic_act_has_no_free_solution_channel(verified_lab, intent):
    result = run(
        verified_lab,
        Provider(lambda body: {"outcome": "socratic_prompt", "hint": hint(body, intent)}),
        socratic=True,
    )
    assert result["status"] == "completed" and HINTS[intent] in result["answer"]
    visible_question = result["answer"].rsplit(" [", 1)[0]
    assert "ninety-seven" not in visible_question and "97" not in visible_question


@pytest.mark.parametrize("payload", ["source", "hint_extra", "hint_intent", "feedback"])
def test_verified_paraphrased_solution_cannot_bypass_typed_hint(verified_lab, payload):
    answer = "Add seventy-five, twenty and two to obtain ninety-seven. Can you repeat these steps?"

    def finish(body):
        data = {"outcome": "socratic_prompt", "hint": hint(body)}
        if payload == "source":
            data["blocks"] = [{**excerpt(body), "text": answer}]
        elif payload == "hint_extra":
            data["hint"]["text"] = answer
        elif payload == "hint_intent":
            data["hint"]["intent"] = answer
        else:
            data["evaluation_blocks"] = [
                {
                    "evidence_id": excerpt(body)["evidence_id"],
                    "learner_quote": "Explain",
                    "quote": excerpt(body)["text"][:80],
                }
            ]
        return data

    result = run(verified_lab, Provider(finish), socratic=True)
    assert result["status"] == "failed" and result["answer"] is None and result["evaluation"] is None
    retain("v16-a12-rejection-" + payload, result)


def test_verified_feedback_compares_actual_reply_without_invented_grade(verified_lab):
    run(
        verified_lab,
        Provider(lambda body: {"outcome": "socratic_prompt", "hint": hint(body)}),
        key="hint",
        socratic=True,
    )

    def finish(body):
        item = excerpt(body)
        return {
            "outcome": "answered",
            "blocks": [item],
            "evaluation_blocks": [
                {"evidence_id": item["evidence_id"], "learner_quote": "restores", "quote": item["text"][:90]}
            ],
        }

    result = run(verified_lab, Provider(finish), key="reply", text="I think it restores the old value.")
    assert result["status"] == "completed" and "Your reply: restores" in result["evaluation"]
    assert "mastery" not in result["evaluation"]
    retain("v16-feedback-comparison", result)


def test_verified_feedback_cannot_claim_unseen_learner_words(verified_lab):
    def finish(body):
        item = excerpt(body)
        return {
            "outcome": "answered",
            "blocks": [item],
            "evaluation_blocks": [
                {
                    "evidence_id": item["evidence_id"],
                    "learner_quote": "I proved mastery",
                    "quote": item["text"][:90],
                }
            ],
        }

    result = run(verified_lab, Provider(finish))
    assert result["status"] == "failed" and result["error_code"] == "TUTOR_SUPPORT_INVALID"


def test_verified_exact_quote_format_repair_preserves_oversized_input(verified_lab):
    def finish(body):
        item = excerpt(body)
        item["text"] = body["evidence"][0]["text"][: 301 if "rejected_blocks" not in body else 300]
        return {"outcome": "answered", "blocks": [item]}

    provider = Provider(finish)
    result = run(verified_lab, provider)
    assert result["status"] == "completed" and len(provider.requests) == 3
    body = json.loads(provider.requests[-1][0][-1]["content"])
    assert len(body["rejected_blocks"]["blocks"][0]["text"]) == 301


def test_verified_foreign_citation_cannot_get_support_repair(verified_lab):
    result = run(
        verified_lab,
        Provider(
            lambda body: {"outcome": "answered", "blocks": [{**excerpt(body), "evidence_id": "foreign"}]}
        ),
    )
    assert result["error_code"] == "TUTOR_CITATION_MISMATCH" and not result["citations"]


def test_verified_factory_rejects_real_mode(monkeypatch):
    from starlette.testclient import TestClient

    from lecturelens_real_eval.tutor.verified_app import create_app

    monkeypatch.setenv("AGENT_LLM_MODE", "real")
    with pytest.raises(Exception, match="MOCK"):
        with TestClient(create_app()):
            pytest.fail("Real startup must never be admitted")


@pytest.mark.parametrize("escaped", [False, True])
def test_capture_redacts_known_authorization_without_logging_headers(tmp_path, escaped):
    from lecturelens_real_eval.tutor.diagnostic_capture import CaptureTransport

    secret = "synthetic-test-authorization-only"
    body = json.dumps({"reflection": secret}).encode()
    if escaped:
        body = ('{"reflection":"' + "".join("\\u%04x" % ord(c) for c in secret) + '"}').encode()
    captured = CaptureTransport(
        httpx.MockTransport(lambda request: httpx.Response(200, content=body)), tmp_path / "capture"
    )
    with httpx.Client(transport=captured) as client:
        response = client.post(
            "https://api.deepseek.com/chat/completions",
            content=b'{"public":"source"}',
            headers={"Authorization": "Bearer " + secret},
        )
        assert response.json()["reflection"] == secret
    files = list((tmp_path / "capture").iterdir())
    assert all(secret.encode() not in f.read_bytes() for f in files)
    assert json.loads((tmp_path / "capture/001-response.body").read_bytes())["reflection"] == "[REDACTED]"
    info = json.loads((tmp_path / "capture/001-capture.json").read_bytes())
    assert info["response_secret_redacted"] and not info["original_entity_bytes_retained"]
    assert all(f.stat().st_mode & 0o777 == 0o600 for f in files)


def test_capture_preserves_preparse_entity_on_protocol_error_and_capacity(tmp_path):
    from lecturelens_real_eval.tutor.diagnostic_capture import CaptureTransport

    raw = b'{ "malformed public response" '
    capture = CaptureTransport(
        httpx.MockTransport(lambda request: httpx.Response(503, content=raw)), tmp_path / "bad"
    )
    with httpx.Client(transport=capture) as client:
        assert client.post("https://api.deepseek.com/chat/completions", content=b"{}").status_code == 503
    assert (tmp_path / "bad/001-response.body").read_bytes() == raw
    limited = CaptureTransport(
        httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 131073)), tmp_path / "limit"
    )
    with httpx.Client(transport=limited) as client, pytest.raises(Exception, match="CAPTURE_FAILED"):
        client.post("https://api.deepseek.com/chat/completions", content=b"{}")
    assert (
        json.loads((tmp_path / "limit/001-capture.json").read_bytes())["response_state"]
        == "PARTIAL_OVER_LIMIT"
    )


def test_live_admission_missing_or_invalid_receipts_never_reads_credentials(tmp_path):
    from lecturelens_real_eval.tutor.verified_diagnostic import live_admission

    with pytest.raises(Exception, match="RECEIPTS_REQUIRED"):
        live_admission({}, None, None, None)
    invalid = tmp_path / "invalid-receipt.json"
    invalid.write_text('{"authorized":false}')
    with pytest.raises(Exception, match="RECEIPTS_INVALID"):
        live_admission({}, invalid, invalid, invalid)


def test_durable_ledger_exact80_limit_and_unknown_liability(verified_lab):
    from lecturelens_real_eval.tutor_channel import EvalError, Ledger, TutorPolicy, encode

    output = Path(os.environ["TUTOR_FOLLOWUP_OUTPUT"]) / "hard-limit-ledger.jsonl"
    ledger = Ledger(verified_lab[0].dsn, output, "v16-hard80", TutorPolicy(max_calls=80))
    ledger.install()
    raw = encode({"model": "deepseek-flash", "tools": [{"function": {"name": "search_tutor_evidence"}}]})
    for _ in range(80):
        reservation = ledger.reserve(raw, 1200)
        ledger.settle(reservation, {"prompt_tokens": 10, "completion_tokens": 10})
    with pytest.raises(EvalError, match="BUDGET_EXHAUSTED"):
        ledger.reserve(raw, 1200)
    assert ledger.check()["calls"] == 80 and ledger.check()["blocked"]


@pytest.mark.parametrize("character", ["a", "中", "😀"])
def test_verified_actual_maximum_source_and_feedback_publication(verified_lab, character):
    _, authority, _, _ = verified_lab
    rows = [
        {
            "evidence_id": str(n) * 64,
            "text": "loop " + character * 295,
            "start_ms": 0,
            "end_ms": 0,
            "source_type": "DOCUMENT_PAGE",
        }
        for n in range(1, 5)
    ]
    authority.snapshot["lectures"]["carpentries-python"]["evidence"] = rows

    def finish(body):
        return {
            "outcome": "answered",
            "blocks": [
                {"kind": "source", "text": e["text"], "evidence_id": e["evidence_id"]}
                for e in body["evidence"]
            ],
            "evaluation_blocks": [
                {"evidence_id": e["evidence_id"], "learner_quote": "l" * 40, "quote": e["text"][:90]}
                for e in body["evidence"][:2]
            ],
        }

    result = run(verified_lab, Provider(finish), text="l" * 40)
    assert (
        result["status"] == "completed" and len(result["answer"]) <= 1600 and len(result["evaluation"]) <= 500
    )
    assert len(result["citations"]) == 4


def test_verified_source_crop_still_needs_context_judgment_negative_fixture(verified_lab):
    _, authority, _, _ = verified_lab
    authority.snapshot["lectures"]["carpentries-python"]["evidence"] = [
        {
            "evidence_id": "e1",
            "text": "The loop lesson says it is false that all loops terminate.",
            "start_ms": 0,
            "end_ms": 0,
            "source_type": "DOCUMENT_PAGE",
        }
    ]
    result = run(
        verified_lab,
        Provider(
            lambda body: {
                "outcome": "answered",
                "blocks": [{"kind": "source", "evidence_id": "e1", "text": "all loops terminate"}],
            }
        ),
    )
    # Exact provenance is deterministic. Misleading cropping remains a semantic
    # limitation, not a claimed fact-support or quality success.
    assert result["status"] == "completed" and "all loops terminate" in result["answer"]
    retain("v16-residual-source-context-crop", result)


def test_frozen_entry_validates_identity_and_blocks_direct_live_before_output(tmp_path):
    from lecturelens_real_eval.tutor.verified_diagnostic import execute, verify_inputs

    state = verify_inputs()
    assert state["ready_for_live"] is False and len(state["blockers"]) == 3
    with pytest.raises(Exception, match="RECEIPTS_REQUIRED"):
        execute(tmp_path / "must-not-exist", live=True)
    assert not (tmp_path / "must-not-exist").exists()


def test_frozen_identity_tamper_is_rejected_before_any_transport(monkeypatch, tmp_path):
    import lecturelens_real_eval.tutor.verified_diagnostic as entry

    original = json.loads((entry.BASE / "candidate.json").read_bytes())
    original["files"] = {"agent-service/src/lecturelens_real_eval/tutor/verified_runtime.py": "0" * 64}
    (tmp_path / "candidate.json").write_text(json.dumps(original))
    monkeypatch.setattr(entry, "BASE", tmp_path)
    with pytest.raises(Exception, match="FROZEN_FILE_CHANGED"):
        entry.verify_inputs()


def test_live_receipt_cannot_raise_hard_limits(tmp_path):
    from datetime import datetime, timedelta, timezone

    from lecturelens_real_eval.tutor.verified_diagnostic import live_admission

    state = {"candidate_sha256": "a" * 64, "packet_sha256": "b" * 64}
    grant = {
        "authorized": True,
        "scope": "ONE_V16_DIAGNOSTIC_NO_RETRY_NO_EXPANSION",
        **state,
        "model": "deepseek-flash",
        "max_requests": 81,
        "max_nano_usd": 700000000,
        "expires_utc": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "run_id": "v16-synthetic-test-only",
    }
    path = tmp_path / "test-receipt.json"
    for request_limit, fee_limit in [(81, 700000000), (80, 700000001)]:
        grant.update(max_requests=request_limit, max_nano_usd=fee_limit)
        path.write_text(json.dumps(grant))
        with pytest.raises(Exception, match="RECEIPTS_INVALID"):
            live_admission(state, path, path, path)


@pytest.mark.parametrize(
    "fault",
    ["none", "malformed", "unknown_usage", "model_mismatch", "fabricated_id", "support_invalid", "budget"],
)
def test_frozen_entry_actual_protocol_census_and_failure_stops(fault):
    from lecturelens_real_eval.tutor.verified_diagnostic import execute

    output = Path(os.environ["TUTOR_FOLLOWUP_OUTPUT"]) / ("entry-" + fault)
    result = execute(output, fault=fault)
    outcomes = json.loads((output / "outcomes.json").read_bytes())
    assert len(outcomes) == 16 and result["real_model_calls"] == 0 and result["cost_usd"] == "0"
    assert result["quality"] == "NOT_RUN" and "SYNTHETIC_PROTOCOL_ONLY" in result["source_scope"]
    if fault == "none":
        assert (result["completed"], result["failed"], result["skipped"], result["sent_requests"]) == (
            16,
            0,
            0,
            32,
        )
    elif fault == "support_invalid":
        assert (result["completed"], result["failed"], result["skipped"]) == (12, 1, 3)
        assert result["global_stop"] is None
    else:
        assert (result["completed"], result["failed"], result["skipped"]) == (0, 1, 15)
        assert result["global_stop"]
    assert result["sent_requests"] == result["ledger"]["calls"]
    if fault in {"unknown_usage", "malformed"}:
        ledger = [json.loads(line) for line in (output / "ledger.jsonl").read_text().splitlines()]
        assert (
            ledger[-1]["usage"] is None and ledger[-1]["charged_nano_usd"] >= ledger[0]["reserved_nano_usd"]
        )
    bodies = list((output / "wire").glob("*-request.body"))
    assert len(bodies) == result["sent_requests"]
    for f in bodies:
        payload = json.loads(f.read_bytes())
        assert payload["model"] == "deepseek-flash" and payload["max_tokens"] == 1200
        assert payload["temperature"] == 0 and payload["thinking"]["type"] == "disabled"
        assert not any(
            k in f.read_text()
            for k in ["reference_points", "necessary_points", "ambiguities_and_review_checks"]
        )
        assert f.with_name(f.name.replace("request.body", "response.body")).is_file()
    retain("entry-result-" + fault, result)
