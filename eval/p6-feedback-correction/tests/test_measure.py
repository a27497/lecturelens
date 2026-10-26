import copy
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("p6_measure", ROOT / "measure.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.fixture
def data():
    return (
        m.load(ROOT / "evidence/trial-05/export.json"),
        m.load(ROOT / "example-ratings.json"),
        m.load(ROOT / "development/standard.json"),
    )


def test_expected_metrics_detect_benefits_and_harm_separately(data):
    export, ratings, standard = data
    report = m.score(export, ratings, standard)
    assert report["warning"] == "Mock 数据，不代表教学效果"
    a, b = [report["conditions"][c] for c in ("reading", "feedback")]
    assert a["correction_rate"] == m.rate(1, 1)
    assert a["wrong_feedback_acceptance"] is None
    assert b["initial_factual_accuracy"] == m.rate(4, 9)
    assert b["error_discovery"] == m.rate(2, 5)
    assert b["correction_rate"] == m.rate(2, 5)
    assert b["final_factual_accuracy"] == m.rate(5, 9)
    assert b["evidence_supported_corrections"] == m.rate(2, 2)
    assert b["feedback_misleading_transition"] == m.rate(1, 4)
    assert b["feedback_missed_errors"] == m.rate(3, 5)
    assert b["retained_missed_errors"] == m.rate(3, 3)
    assert b["wrong_feedback_acceptance"] == m.rate(3, 3)
    assert b["false_refusal"] == m.rate(1, 4)
    assert b["honest_insufficiency"] == m.rate(1, 1)


def test_empty_denominator_is_not_success(data):
    export, _ratings, standard = data
    export["trials"] = []
    report = m.score(export, [], standard)
    assert report["conditions"]["feedback"]["correction_rate"] == m.rate(0, 0)
    assert m.rate(0, 0)["rate"] is None


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate_trial",
        "missing_rating",
        "mixed_data",
        "wrong_task",
        "bad_label",
        "unsupported_claim",
        "discovery_without_statement",
        "freeze",
        "control_feedback",
        "missing_honesty",
    ],
)
def test_scoring_rejects_silent_bias(data, fault):
    export, ratings, standard = data
    if fault == "duplicate_trial":
        export["trials"].append(copy.deepcopy(export["trials"][0]))
    elif fault == "missing_rating":
        ratings.pop()
    elif fault == "mixed_data":
        export["trials"][0]["data_kind"] = "HUMAN"
    elif fault == "wrong_task":
        ratings[0]["item_id"] = "d2"
    elif fault == "bad_label":
        ratings[0]["initial"]["d1-f1"] = "almost_correct"
    elif fault == "unsupported_claim":
        export["trials"][0]["sidecar"]["final_evidence"]["claims"] = []
    elif fault == "discovery_without_statement":
        export["trials"][0]["sidecar"]["discovery"]["text"] = ""
    elif fault == "freeze":
        export["freeze_hash"] = "changed"
    elif fault == "control_feedback":
        ratings[0]["feedback_wrong"] = False
    elif fault == "missing_honesty":
        ratings[3]["honest_insufficiency"] = None
    with pytest.raises(ValueError):
        m.score(export, ratings, standard)


def test_kappa_is_keyed_by_fact_and_preserves_disagreement(data):
    _, ratings, standard = data
    left, right = copy.deepcopy(ratings), copy.deepcopy(ratings)
    for row in right:
        row["rater_id"] = "SIMULATED_RATER_2"
    right.reverse()
    same = m.agreement(left, right, standard)
    assert same["fact_labels"] == 22 and same["cohen_kappa"] == 1
    right[-1]["initial"]["d1-f2"] = "missing"
    different = m.agreement(left, right, standard)
    assert different["raw_agreement"] == pytest.approx(21 / 22)
    assert 0 < different["cohen_kappa"] < 1
    assert left[0]["initial"]["d1-f2"] == "incorrect"
    with pytest.raises(ValueError):
        m.agreement(left, left, standard)


def test_freeze_tamper_and_evidence_overwrite_are_rejected(tmp_path):
    frozen = m.load(ROOT / "FREEZE.json")
    frozen["files"] = {"course.json": "wrong"}
    (tmp_path / "FREEZE.json").write_text(json.dumps(frozen))
    (tmp_path / "course.json").write_text("changed")
    with pytest.raises(ValueError, match="Frozen input changed"):
        m.verify_freeze(tmp_path)
    out = tmp_path / "output.json"
    m.write_new(out, {"failed": True})
    with pytest.raises(FileExistsError):
        m.write_new(out, {"success": True})
    assert m.load(out) == {"failed": True}


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://p6@remote:25486/lecturelens_p6_test",
        "postgresql://p6@127.0.0.1:25486/production",
        "postgresql://p6@127.0.0.1:25486/lecturelens_p6_live",
    ],
)
def test_export_refuses_nonlab_database(dsn):
    with pytest.raises(ValueError):
        m.safe_lab_dsn(dsn)


@pytest.fixture
def live(request):
    # Missing PostgreSQL is an error, never a skipped mechanism test.
    from lecturelens_agent.study.store import StudyStore

    dsn = m.safe_lab_dsn(os.environ["AGENT_TEST_DATABASE_URL"])
    return (
        StudyStore(dsn),
        m.load(request.config.getoption("--p6-manifest")),
        m.load(ROOT / "development/course.json"),
    )


def test_live_export_reads_persisted_history_and_notes_without_writes(live):
    from mock_flow import counts

    store, manifest, course = live
    for trial in manifest["trials"]:
        before = counts(store, trial["scope"]["session_id"])
        exported = m.export_trial(store, trial, course)
        assert [a["version"] for a in exported["history"]] == [2, 1]
        assert exported["initial"]["attempt_id"] == trial["initial_attempt_id"]
        if trial["condition"] == "feedback":
            assert exported["feedback"][0]["notes"][0]["disposition"] == "acknowledged"
            assert exported["feedback"][0]["feedback"]["answer_version"] == 1
        assert counts(store, trial["scope"]["session_id"]) == before


@pytest.mark.parametrize(
    "fault",
    [
        "owner",
        "revision",
        "artifact",
        "stale_exposure",
        "feedback_id",
        "wrong_final",
        "time",
        "source",
        "evidence_binding",
        "condition",
    ],
)
def test_live_export_rejects_cross_binding_and_contamination(live, fault):
    from lecturelens_agent.study.store import StudyError

    store, manifest, course = live
    trial = copy.deepcopy(manifest["trials"][1])
    if fault == "owner":
        trial["scope"]["owner_id"] += 1
    elif fault == "revision":
        trial["scope"]["revision"] += 1
    elif fault == "artifact":
        trial["scope"]["artifact_id"] = "another-artifact"
    elif fault == "stale_exposure":
        trial["feedback_exposures"][0]["answer_version_at_exposure"] = 2
    elif fault == "feedback_id":
        trial["feedback_exposures"][0]["feedback_id"] = "another-feedback"
    elif fault == "wrong_final":
        trial["final_attempt_id"] = trial["initial_attempt_id"]
    elif fault == "time":
        trial["discovery"]["at"] = "2000-01-01T00:00:00+00:00"
    elif fault == "source":
        trial["source_checks"][0]["evidence_id"] = "fabricated"
    elif fault == "evidence_binding":
        trial["final_evidence"]["attempt_id"] = "another-attempt"
    elif fault == "condition":
        trial["condition"] = "reading"
    with pytest.raises((ValueError, StudyError)):
        m.export_trial(store, trial, course)


def test_rejects_relaxed_standard_and_unknown_condition(data):
    export, ratings, standard = data
    changed = copy.deepcopy(standard)
    changed["items"][0]["facts"][0]["required_evidence"] = []
    with pytest.raises(ValueError, match="unchanged frozen standard"):
        m.score(export, ratings, changed)
    export["trials"][0]["condition"] = "ignored_condition"
    with pytest.raises(ValueError, match="Unknown experimental condition"):
        m.score(export, ratings, standard)


def test_hostaddr_cannot_bypass_loopback_guard():
    with pytest.raises(ValueError):
        m.safe_lab_dsn(
            "host=127.0.0.1 hostaddr=192.0.2.1 port=25486 dbname=lecturelens_p6_test"
        )


def test_live_pagination_export_does_not_truncate_history_or_notes(
    live, tmp_path, monkeypatch
):
    from lecturelens_agent.study.contracts import StudyCommand
    from mock_flow import run_trial

    store, _manifest, course = live
    monkeypatch.setenv("STUDY_FEEDBACK_ENABLED", "true")
    item = m.load(ROOT / "development/standard.json")["items"][0]
    fixture = (
        "pagination",
        "feedback",
        "最多1次。",
        "找到或查完停止，最多n次。",
        "应为最多n次。",
        "revise",
        False,
        "原来的1次有误，应为n次。",
    )
    trial, _export, _audit = run_trial(store, course, item, fixture, tmp_path)
    scope = trial["scope"]
    exposure = trial["feedback_exposures"][0]
    for version in range(2, 24):
        store.command(
            StudyCommand(
                **scope,
                operation="SAVE_ATTEMPT",
                request_key=f"more-answer-{version}",
                expected_version=version,
                answer_text=f"later answer {version}",
            ),
            "mock",
        )
    for version in range(1, 23):
        store.command(
            StudyCommand(
                **(scope | {"run_id": exposure["run_id"]}),
                operation="SAVE_FEEDBACK_NOTE",
                feedback_id=exposure["feedback_id"],
                request_key=f"more-note-{version}",
                expected_version=version,
                disposition="disputed",
                note_text=f"later note {version}",
            ),
            "mock",
        )
    exported = m.export_trial(store, trial, course)
    assert len(exported["history"]) == 24
    assert len(exported["feedback"][0]["notes"]) == 23
    assert exported["initial"]["version"] == 1 and exported["final"]["version"] == 2


def test_pilot_source_ids_bind_to_frozen_text_and_scope():
    course = m.load(ROOT / "development/course.json")
    sources = [
        {
            "canonical_id": e["evidence_id"],
            "authority_evidence": e | {"evidence_id": f"java-{i}"},
        }
        for i, e in enumerate(course["evidence"])
    ]
    trial = {
        "data_kind": "PILOT",
        "scope": {"course_id": "42", "revision": 1},
        "source_binding": {
            "course_id": "42",
            "revision": 1,
            "material_hash": m.digest(course),
            "acquired_via": "authenticated_java_evidence",
            "sources": sources,
        },
    }
    bound, mapping = m.bound_sources(trial, course)
    assert mapping["java-1"] == "d-e2"
    assert bound["java-1"]["text"] == course["evidence"][1]["text"]
    trial["source_binding"]["sources"][0]["authority_evidence"]["text"] = (
        "another course text"
    )
    with pytest.raises(ValueError, match="differs from frozen material"):
        m.bound_sources(trial, course)
    trial["source_binding"]["course_id"] = "another-course"
    with pytest.raises(ValueError, match="scope mismatch"):
        m.bound_sources(trial, course)


def test_pilot_rating_support_uses_bound_source_ids(data):
    export, ratings, standard = data
    trial = export["trials"][0]
    trial["source_id_map"] = {"java-2": "d-e2"}
    for claim in trial["sidecar"]["final_evidence"]["claims"]:
        claim["evidence_ids"] = ["java-2"]
    assert m.score(export, ratings, standard)["conditions"]["reading"][
        "evidence_supported_corrections"
    ] == m.rate(1, 1)


def test_missing_trials_are_counted_without_inventing_fact_labels(data):
    export, ratings, standard = data
    export["incomplete_trials"] = [
        {"trial_id": "dropout", "condition": "reading", "reason": "withdrew"}
    ]
    result = m.score(export, ratings, standard)["conditions"]["reading"]
    assert result["assigned_trials"] == 2
    assert result["completion"] == m.rate(1, 2)
    assert result["conservative_fully_correct"] == m.rate(1, 2)
    assert result["correction_rate"] == m.rate(1, 1)
    export["incomplete_trials"][0]["trial_id"] = "read-correct"
    with pytest.raises(ValueError, match="incomplete-trial accounting"):
        m.score(export, ratings, standard)
