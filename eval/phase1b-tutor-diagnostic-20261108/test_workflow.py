"""Synthetic admissions and responses only; no native exec, database or model."""

import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import admission
import pytest
import review


@pytest.fixture(autouse=True)
def no_secret_or_transport(monkeypatch):
    class SyntheticEnvironment(dict):
        def get(self, key, *args):
            if key in {"AGENT_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"}:
                pytest.fail("no credential value access in zero-cost tests")
            return super().get(key, *args)

    # Replace the mapping before arming the read guard. pytest.setenv itself
    # reads the previous value, so it must never be used on real credentials.
    public = {
        k: os.environ[k]
        for k in ("PATH", "HOME", "USER", "LANG", "LC_ALL")
        if k in os.environ
    }
    public["AGENT_LLM_API_KEY"] = "synthetic-not-a-provider-key"
    monkeypatch.setattr(os, "environ", SyntheticEnvironment(public))
    import httpx

    monkeypatch.setattr(
        httpx, "HTTPTransport", lambda **kw: pytest.fail("no real HTTP transport")
    )


def receipt_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(admission, "inspect", lambda _: {"frozen": {"synthetic": True}})
    monkeypatch.setattr(
        admission, "preparation_head", lambda: "synthetic-preparation-head"
    )
    from lecturelens_real_eval.tutor import selection_smoke

    calls = []
    monkeypatch.setattr(
        selection_smoke, "live_admission", lambda *a: calls.append("native-admission")
    )
    monkeypatch.setattr(
        admission, "database_ready", lambda: calls.append("database-probe")
    )
    proof = tmp_path / "synthetic-evidence.txt"
    proof.write_bytes(b"SYNTHETIC ACCOUNT PROOF FOR UNIT TEST ONLY")
    assurance = {
        "kind": "VERIFIED_SUPPLIER_ACCOUNT_HARD_CAP",
        "verified": True,
        "run_id": "v19-synthetic-only",
        "execution_root": str(tmp_path),
        "model": "deepseek-flash",
        "currency": "USD",
        "maximum_additional_liability_nano_usd": 300000000,
        "inflight_and_delayed_billing_covered": True,
        "shared_account_activity_covered": True,
        "automatic_topups_and_credit_disabled": True,
        "verified_by": "SYNTHETIC TEST",
        "verified_utc": datetime.now(timezone.utc).isoformat(),
        "redacted_evidence_file": proof.name,
        "redacted_evidence_sha256": admission.digest(proof),
    }
    cost = tmp_path / "synthetic-assurance.json"
    cost.write_text(json.dumps(assurance))
    grant = {
        "preparation_git_head": "synthetic-preparation-head",
        "execution_root": str(tmp_path),
        "run_id": "v19-synthetic-only",
        "cost_assurance_sha256": admission.digest(cost),
        "review_plan_sha256": admission.digest(admission.POLICY),
        "expires_utc": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    }
    auth = tmp_path / "synthetic-grant.json"
    auth.write_text(json.dumps(grant))
    return calls, auth, cost, grant, assurance


def test_human_absent_does_not_block_structurally_valid_diagnostic(
    tmp_path, monkeypatch
):
    calls, auth, cost, _, _ = receipt_fixture(tmp_path, monkeypatch)
    admission.handoff(
        tmp_path,
        tmp_path / ".data/new",
        auth,
        auth,
        cost,
        execute=lambda *a: calls.append("exec-mocked"),
    )
    assert calls == ["native-admission", "database-probe", "exec-mocked"]
    assert "independent_reviewer" not in json.loads(auth.read_text())
    assert admission.review_plan(admission.POLICY)


@pytest.mark.parametrize(
    "defect",
    [
        "no_grant",
        "no_cost",
        "risk_boolean",
        "missing_key",
        "wrong_head",
        "wrong_root",
        "long_expiry",
        "wrong_plan",
        "missing_database",
    ],
)
def test_admission_stops_without_native_exec(tmp_path, monkeypatch, defect):
    calls, auth, cost, grant, _ = receipt_fixture(tmp_path, monkeypatch)
    if defect == "no_grant":
        auth = None
    elif defect in {"no_cost", "risk_boolean"}:
        cost = None
        grant["supplier_cost_risk_accepted"] = defect == "risk_boolean"
    elif defect == "missing_key":
        del os.environ["AGENT_LLM_API_KEY"]
    elif defect == "wrong_head":
        grant["preparation_git_head"] = "wrong"
    elif defect == "wrong_root":
        grant["execution_root"] = "wrong"
    elif defect == "long_expiry":
        grant["expires_utc"] = (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).isoformat()
    elif defect == "wrong_plan":
        grant["review_plan_sha256"] = "wrong"
    elif defect == "missing_database":

        def no_database():
            raise ValueError("ISOLATED_DURABLE_DATABASE_REQUIRED")

        monkeypatch.setattr(admission, "database_ready", no_database)
    if auth:
        auth.write_text(json.dumps(grant))
    with pytest.raises(ValueError):
        admission.handoff(
            tmp_path,
            tmp_path / ".data/new",
            auth,
            auth,
            cost,
            execute=lambda *a: pytest.fail("must not exec"),
        )
    assert not (tmp_path / ".data").exists()
    if defect != "missing_database":
        assert not calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("verified", False),
        ("maximum_additional_liability_nano_usd", 300000001),
        ("maximum_additional_liability_nano_usd", True),
        ("currency", "CNY"),
        ("inflight_and_delayed_billing_covered", False),
        ("shared_account_activity_covered", False),
        ("automatic_topups_and_credit_disabled", False),
        ("redacted_evidence_sha256", "wrong"),
        ("verified_utc", "2000-01-01T00:00:00+00:00"),
        ("kind", "ACCOUNT_BALANCE_NOT_A_CAP"),
    ],
)
def test_balance_alert_or_stale_evidence_is_not_billing_protection(
    tmp_path, monkeypatch, field, value
):
    calls, auth, cost, grant, assurance = receipt_fixture(tmp_path, monkeypatch)
    assurance[field] = value
    cost.write_text(json.dumps(assurance))
    grant["cost_assurance_sha256"] = admission.digest(cost)
    auth.write_text(json.dumps(grant))
    with pytest.raises(ValueError, match="HARD_CAP_RECEIPT_INVALID"):
        admission.handoff(
            tmp_path,
            tmp_path / ".data/new",
            auth,
            auth,
            cost,
            execute=lambda *a: pytest.fail("must not exec"),
        )
    assert not calls


def test_missing_quality_plan_blocks_admission(tmp_path, monkeypatch):
    calls, auth, cost, _, _ = receipt_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        admission.handoff(
            tmp_path,
            tmp_path / ".data/new",
            auth,
            auth,
            cost,
            tmp_path / "missing-plan",
            execute=lambda *a: pytest.fail("must not exec"),
        )
    assert not calls


def synthetic_bundle(tmp_path):
    tmp_path.mkdir()
    outcomes = [
        {"turn_key": k, "status": "completed", "answer": "synthetic answer"}
        for k in review.TURN_KEYS
    ]
    files = {
        "course-evidence.json": review.encode(
            {"evidence": [{"evidence_id": "synthetic-e1", "text": "synthetic source"}]}
        ),
        "outcomes.json": review.encode(outcomes),
        "deterministic.json": review.encode({"mechanical": "PASS"}),
    }
    manifest = {
        "candidate_sha256": review.CANDIDATE,
        "packet_sha256": review.PACKET,
        "generation": "REAL_OUTPUTS_PRESENT",
        "files": {k: review.sha(v) for k, v in files.items()},
    }
    manifest["bundle_id"] = review.sha(review.encode(manifest))
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    (tmp_path / "manifest.json").write_bytes(review.encode(manifest))
    item = {
        "status": "PASS",
        "reason": "synthetic test only",
        "confidence": "HIGH",
        "evidence": [
            {
                "answer_field": "answer",
                "answer_quote": "synthetic answer",
                "evidence_id": "synthetic-e1",
                "source_quote": "synthetic source",
            }
        ],
    }
    response = {
        "bundle_id": manifest["bundle_id"],
        "candidate_sha256": review.CANDIDATE,
        "packet_sha256": review.PACKET,
        "outcomes_sha256": review.sha(files["outcomes.json"]),
        "reviewer": {
            "kind": "EXTERNAL_AI",
            "provider": "synthetic",
            "model": "synthetic",
            "separate_context": True,
            "implementation_session": False,
            "reviewed_utc": datetime.now(timezone.utc).isoformat(),
        },
        "turns": [
            {
                "turn_key": k,
                "points": [{"id": p, **copy.deepcopy(item)} for p in review.POINTS[k]],
                "claims": [copy.deepcopy(item)],
                "all_substantive_claims_reviewed": True,
            }
            for k in review.TURN_KEYS
        ],
    }
    return response


@pytest.mark.parametrize(
    "condition,expected",
    [
        ("valid", "AI_REVIEW_PASS"),
        ("absent", "UNRESOLVED"),
        ("same_session", "UNRESOLVED"),
        ("human_label", "UNRESOLVED"),
        ("low_confidence", "UNRESOLVED"),
        ("empty_claims", "UNRESOLVED"),
        ("unsupported_claim", "FAIL"),
        ("partial_claim_review", "UNRESOLVED"),
        ("invalid_review_time", "UNRESOLVED"),
    ],
)
def test_ai_cross_review_never_becomes_human_expert_pass(tmp_path, condition, expected):
    bundle = tmp_path / "bundle"
    response = synthetic_bundle(bundle)
    if condition == "same_session":
        response["reviewer"]["implementation_session"] = True
    elif condition == "human_label":
        response["reviewer"]["kind"] = "HUMAN"
    elif condition == "low_confidence":
        response["turns"][0]["points"][0]["confidence"] = "LOW"
    elif condition == "empty_claims":
        response["turns"][0]["claims"] = []
    elif condition == "unsupported_claim":
        response["turns"][0]["claims"][0]["status"] = "FAIL"
    elif condition == "partial_claim_review":
        response["turns"][0]["all_substantive_claims_reviewed"] = False
    elif condition == "invalid_review_time":
        response["reviewer"]["reviewed_utc"] = "unknown"
    path = tmp_path / "synthetic-review.json"
    path.write_bytes(review.encode(response))
    result = review.aggregate(bundle, None if condition == "absent" else path)
    assert result["quality"] == expected
    assert (
        result["human_review"] == "HUMAN_NOT_RUN" and result["expert_verified"] is False
    )
    assert not result["release_or_expansion_authorized"]


@pytest.mark.parametrize(
    "defect",
    [
        "packet",
        "outcomes",
        "missing_point",
        "missing_evidence",
        "bundle",
        "invented_answer_quote",
        "invented_source_quote",
        "invented_source_id",
    ],
)
def test_review_tamper_or_missing_required_point_cannot_pass(tmp_path, defect):
    bundle = tmp_path / "bundle"
    response = synthetic_bundle(bundle)
    if defect == "packet":
        response["packet_sha256"] = "wrong"
    elif defect == "outcomes":
        response["outcomes_sha256"] = "wrong"
    elif defect == "missing_point":
        response["turns"][0]["points"].pop()
    elif defect == "missing_evidence":
        response["turns"][0]["points"][0]["evidence"] = []
    elif defect.startswith("invented_"):
        key = {
            "invented_answer_quote": "answer_quote",
            "invented_source_quote": "source_quote",
            "invented_source_id": "evidence_id",
        }[defect]
        response["turns"][0]["points"][0]["evidence"][0][key] = "invented"
    else:
        (bundle / "deterministic.json").write_bytes(b"changed")
    path = tmp_path / "synthetic-review.json"
    path.write_bytes(review.encode(response))
    with pytest.raises(ValueError):
        review.aggregate(bundle, path)


def test_frozen_packet_export_before_generation_is_complete_and_not_quality_pass(
    tmp_path,
):
    root = Path("/home/dev/.codex/worktrees/phase1a-v19-runner-20261108")
    bundle = tmp_path / "export"
    manifest = review.export(root, bundle)
    assert manifest["generation"] == "NOT_RUN"
    assert review.sha((bundle / "original-packet.json").read_bytes()) == review.PACKET
    assert review.sha((bundle / "candidate.json").read_bytes()) == review.CANDIDATE
    expected_course = (
        root / "eval/tutor-v14-fresh-v1/materials/carpentries-python-new.md"
    )
    assert (bundle / "course.md").read_bytes() == expected_course.read_bytes()
    assert (
        json.loads((bundle / "course-evidence.json").read_bytes())["split"]
        == "development"
    )
    assert len(json.loads((bundle / "outcomes.json").read_bytes())) == 3
    assert review.aggregate(bundle)["quality"] == "NOT_RUN"
    assert review.oracle()["trace"] == [2, 3, 4]
    with pytest.raises(FileExistsError):
        review.export(root, bundle)
    assert (bundle / "course.md").stat().st_mode & 0o777 == 0o600


def test_mock_prior_output_cannot_be_packaged_as_real_quality(tmp_path):
    root = Path("/home/dev/.codex/worktrees/phase1a-v19-runner-20261108")
    with pytest.raises(ValueError, match="MOCK_OUTPUT_CANNOT"):
        review.export(
            root,
            tmp_path / "not-created",
            root / ".data/phase1a/acceptance-final/teaching-http-None-None",
        )
    assert not (tmp_path / "not-created").exists()


def test_deterministic_checks_do_not_judge_citation_semantics_or_execute_model_code():
    result = review.deterministic([], {"mode": "mock"}, [], [], [], [])
    assert result["mechanical"] == "FAIL"
    assert result["citation_semantics"].startswith("UNRESOLVED")
    assert result["generated_code_semantics"].startswith("UNRESOLVED")
    assert result["reference_oracle"]["final_value"] == 4


def test_source_mapping_uses_frozen_grouping_and_preserves_original_snapshot():
    from lecturelens_real_eval.tutor.claim_grounding_runtime import LessonAuthority

    root = Path("/home/dev/.codex/worktrees/phase1a-v19-runner-20261108")
    snapshot = json.loads((root / "eval/tutor-v14-fresh-v1/snapshot.json").read_bytes())
    packet = json.loads(
        (root / "eval/tutor-selection-v19-v1/sample-candidate.json").read_bytes()
    )
    course = packet["sessions"][0]["course_id"]
    before = copy.deepcopy(snapshot)
    canonical = review.canonical_course(snapshot, course)
    assert canonical == LessonAuthority(snapshot).snapshot["lectures"][course]
    assert snapshot == before
    originals = {e["evidence_id"] for e in snapshot["lectures"][course]["evidence"]}
    assert {e["evidence_id"] for e in canonical["evidence"]} != originals
    assert all(
        set(e["member_evidence_ids"]) <= originals for e in canonical["evidence"]
    )
    snapshot["lectures"][course]["split"] = "holdout"
    with pytest.raises(ValueError, match="ONLY_ORIGINAL_EXPOSED"):
        review.canonical_course(snapshot, course)


@pytest.mark.parametrize("alteration", [None, "foreign_id", "changed_text"])
def test_source_binding_still_requires_exact_id_and_text(alteration):
    citation = {"evidence_id": "canonical", "text": "Frozen canonical source."}
    if alteration == "foreign_id":
        citation["evidence_id"] = "foreign"
    elif alteration == "changed_text":
        citation["text"] += " Added model claim."
    outcomes = [
        {
            "turn_key": review.TURN_KEYS[0],
            "status": "completed",
            "answer": "draft",
            "citations": [citation],
        }
    ]
    result = review.deterministic(
        outcomes,
        {},
        [{"evidence_id": "canonical", "text": "Frozen canonical source."}],
        [],
        [],
        [],
    )
    assert result["checks"]["source_binding"] is (alteration is None)
    assert result["mechanical"] == "FAIL"  # Mapping cannot erase incomplete execution.
