"""Scope/failure/denominator tests; labels are hand-constructed Mock fixtures only."""

import json
import subprocess
import sys

import pytest
from plan import expected_rows, load_queue, validate_queue
from records import execution_counts, failure_items, read_run
from review import export, import_annotations, score
from shared import BASE, HERE, ROOT, digest, load, object_hash, read, write
from task_scores import summarize

QUEUE = HERE / "development-queue-v1.json"


def make_run(directory, rows=True):
    queue, scripts, _, identity = load_queue(QUEUE)
    directory.mkdir()
    planned = expected_rows(scripts)
    write(directory / "expected-turns.json", dict(queue_sha256=digest(QUEUE), turns=planned))
    write(
        directory / "config.json",
        dict(
            schema="tutor-scale-v2",
            candidate_sha256=identity,
            queue_sha256=digest(QUEUE),
            dataset_version=queue["dataset_version"],
            dataset_lock_sha256=queue["dataset_lock_sha256"],
            expected_turns_sha256=object_hash(planned),
            selected_dialogue_ids=[d["dialogue_id"] for d in scripts],
            scope="frozen_development_queue",
            data_kind="MOCK",
            fault=None,
        ),
    )
    if rows:
        with (directory / "turns.jsonl").open("w") as f:
            for p in planned:
                r = dict(
                    **p,
                    status="completed",
                    outcome="insufficient_evidence" if p["script"]["expected_insufficient"] else "answered",
                    answer="I cannot answer from these sources."
                    if p["script"]["expected_insufficient"]
                    else "A claim.",
                    evaluation="",
                    citations=[],
                    review={"answer_supported": True},
                    calls=[],
                    error_code=None,
                )
                f.write(json.dumps(r) + "\n")
    return read_run(QUEUE, directory)


def test_queue_is_exact_and_has_no_holdout():
    queue, scripts, snapshot, _ = load_queue(QUEUE)
    assert [d["dialogue_id"] for d in scripts] == ["queue-03", "queue-09", "ecology-02", "ecology-08"]
    assert len(expected_rows(scripts)) == 20 and set(snapshot["lectures"]) == {"queue", "ecology"}
    assert all(d["course_id"] != "energy" and len(d["turns"]) == 5 for d in scripts)
    assert queue["dataset_version"] == "tutor-scale-synthetic-v2"


def test_queue_hash_rejected_before_runtime(tmp_path):
    q = read(QUEUE)
    q["sessions"].pop()
    write(tmp_path / "queue.json", q)
    with pytest.raises(ValueError, match="QUEUE_HASH"):
        load_queue(tmp_path / "queue.json")


@pytest.mark.parametrize(
    "change", ["holdout", "duplicate", "course", "incomplete", "version", "data_hash", "turn_hash"]
)
def test_queue_semantic_validation(change):
    snapshot, groups, _ = load()
    q = read(QUEUE)
    if change == "holdout":
        q["sessions"][0]["dialogue_id"] = "energy-01"
    if change == "duplicate":
        q["sessions"][1] = q["sessions"][0]
    if change == "course":
        q["sessions"][0]["course_id"] = "energy"
    if change == "incomplete":
        q["sessions"][0]["turns"] = 4
    if change == "version":
        q["dataset_version"] = "changed"
    if change == "data_hash":
        q["dataset_lock_sha256"] = "0" * 64
    if change == "turn_hash":
        q["sessions"][0]["turns_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="QUEUE_"):
        validate_queue(q, snapshot, groups, digest(BASE / "dataset-lock.json"))


def test_completely_absent_results_are_twenty_missing(tmp_path):
    run = make_run(tmp_path / "run", rows=False)
    report = failure_items(run)
    assert report["counts"]["expected_turns"] == 20
    assert report["counts"]["executed_result_turns"] == 0
    assert report["counts"]["missing_result_turns"] == 20 and len(report["items"]) == 20
    assert all("MISSING_RESULT" in i["reasons"] for i in report["items"])
    result = summarize(run, {})
    assert result["quality_status"] == "NOT_RUN"
    assert result["task_correctness"]["applicable_planned"] == 20
    assert result["task_correctness"]["execution_unscorable"] == 20
    assert result["task_correctness"]["confirmed_positive_over_planned"] is None


def test_absent_metadata_is_diagnostic_only(tmp_path):
    (tmp_path / "empty").mkdir()
    report = failure_items(read_run(QUEUE, tmp_path / "empty"))
    assert len(report["items"]) == 20 and not report["metadata_complete"]
    with pytest.raises(ValueError, match="BOUND_RUN"):
        export(QUEUE, tmp_path / "empty", tmp_path / "review")


def test_partial_missing_and_recovered_call_failure_are_diagnostic(tmp_path):
    run = make_run(tmp_path / "run")
    rows = run["rows"]
    rows[0].update(status="failed", error_code="TUTOR_DEADLINE", answer=None)
    rows[1]["calls"] = [{"status": "FAILED", "error": "REAL_EVAL_PROTOCOL_FAILURE", "purpose": "review"}]
    rows[2].update(status="MISSING", error_code="RESULT_MISSING")
    report = failure_items(run)
    assert len(report["items"]) == 3
    assert "TIMEOUT_OR_DEADLINE" in report["items"][0]["reasons"]
    assert "CALL_FAILED" in report["items"][1]["reasons"]
    assert report["counts"]["completed_turns"] == 18 and report["counts"]["failed_turns"] == 1
    assert report["counts"]["missing_result_turns"] == 1
    assert report["purpose"] == "DIAGNOSTIC_ONLY_NEVER_POOL_WITH_RANDOM_SAMPLE"


def test_duplicate_and_wrong_scope_results_are_rejected(tmp_path):
    make_run(tmp_path / "run")
    p = tmp_path / "run/turns.jsonl"
    original = p.read_text()
    p.write_text(original + original.splitlines()[0] + "\n")
    with pytest.raises(ValueError, match="DUPLICATE"):
        read_run(QUEUE, p.parent)
    p.write_text(original.replace("queue-03:1", "energy-01:1", 1))
    with pytest.raises(ValueError, match="UNEXPECTED"):
        read_run(QUEUE, p.parent)


def test_shard_recovery_without_aggregate(tmp_path):
    run = make_run(tmp_path / "run")
    q = tmp_path / "run/queue"
    q.mkdir()
    (q / "turns.jsonl").write_text(json.dumps(run["rows"][0]) + "\n")
    (tmp_path / "run/turns.jsonl").unlink()
    recovered = read_run(QUEUE, tmp_path / "run")
    assert recovered["result_origin"] == "shards"
    assert execution_counts(recovered["rows"])["missing_result_turns"] == 19


def test_empty_census_import_and_scores_are_not_run(tmp_path):
    make_run(tmp_path / "run")
    info = export(QUEUE, tmp_path / "run", tmp_path / "review")
    assert info["primary"] == 20 and info["overlap"] == 5
    key = tmp_path / "review/private-key.json"
    for r in "AB":
        info = import_annotations(
            key,
            tmp_path / f"review/packet-{r}.json",
            tmp_path / f"review/annotation-{r}.json",
            tmp_path / f"import-{r}.json",
        )
        assert info["complete"] == 0
    result = score(
        QUEUE, key, [tmp_path / "import-A.json", tmp_path / "import-B.json"], tmp_path / "score.json"
    )
    assert result["quality_status"] == "NOT_RUN" and result["human_scores_status"] == "NOT_RUN"
    assert result["execution"]["expected_turns"] == 20 and result["execution"]["task_assessed_turns"] == 0
    for metric in (
        "task_correctness",
        "refusal_correctness",
        "cross_turn_consistency",
        "expected_answer_supported_citation_coverage",
    ):
        assert result[metric]["rate_assessed"] is None
    assert result["expected_answer_supported_citation_coverage"]["applicable_planned"] == 12
    assert result["expected_abstention_correctness"]["applicable_planned"] == 8
    assert result["cross_turn_consistency"]["applicable_planned"] == 8
    assert result["model_human_support_agreement"]["cohen_kappa"] is None
    packet = json.dumps(read(tmp_path / "review/packet-A.json"))
    assert "deepseek" not in packet and "code_sha" not in packet and "candidate_sha" not in packet


def test_hand_constructed_full_denominators_and_no_citation_inflation(tmp_path):
    run = make_run(tmp_path / "run")
    rows = run["rows"]
    # Two labeled answers, one wrong abstention, one valid expected abstention,
    # one failed output and one wholly missing output. Other labels stay missing.
    rows[2]["outcome"] = "insufficient_evidence"
    rows[5].update(status="failed", error_code="SYNTHETIC_FAILURE")
    rows[6].update(status="MISSING", error_code="RESULT_MISSING")

    def label(task, context=None, refusal=None, ids=None):
        return dict(
            complete=True,
            task_correct=task,
            context_consistent=context,
            abstention_correct=refusal,
            overall_supported="supported" if task else "unsupported",
            claims=[dict(claim_id="c", requires_citation=True, citation_ids=ids or [])]
            if ids is not None
            else [],
            citation_checks=[dict(claim_id="c", label="supported")] if ids else [],
        )

    labels = {
        rows[0]["turn_key"]: label(True, ids=["e1"]),
        rows[1]["turn_key"]: label(False, False, ids=[]),
        rows[2]["turn_key"]: label(False, True, False),
        rows[3]["turn_key"]: label(True, refusal=True),
    }
    result = summarize(run, labels)
    assert result["execution"]["expected_turns"] == 20
    assert result["execution"]["executed_result_turns"] == 19
    assert result["execution"]["completed_turns"] == 18
    assert result["execution"]["failed_turns"] == 1 and result["execution"]["missing_result_turns"] == 1
    task = result["task_correctness"]
    assert task["assessed"] == 4 and task["missing_annotations"] == 14 and task["execution_unscorable"] == 2
    assert task["rate_assessed"] == 0.5 and task["confirmed_positive_over_planned"] == 0.1
    assert (
        result["refusal_correctness"]["assessed"] == 2
        and result["refusal_correctness"]["rate_assessed"] == 0.5
    )
    assert (
        result["cross_turn_consistency"]["assessed"] == 2
        and result["cross_turn_consistency"]["rate_assessed"] == 0.5
    )
    assert result["citation_metrics"]["citation_support_accuracy"]["value"] == 1
    assert result["citation_metrics"]["supported_citation_coverage"]["value"] == 0.5
    cov = result["expected_answer_supported_citation_coverage"]
    assert cov["applicable_planned"] == 12 and cov["assessed"] == 3 and cov["positive"] == 1
    assert cov["confirmed_positive_over_planned"] == 1 / 12
    assert result["outcome_counts"]["abstentions_on_expected_answer"] == 1
    # Fake reviewer cannot generate a real model/human agreement even with fixture labels.
    assert result["model_human_support_agreement"]["comparable"] == 0
    assert result["quality_status"] == "MOCK_NOT_QUALITY"


def test_context_judgment_not_string_equality(tmp_path):
    run = make_run(tmp_path / "run")
    key = run["rows"][1]["turn_key"]
    run["rows"][1]["answer"] = "same string"
    base = dict(
        complete=True,
        task_correct=None,
        context_consistent=False,
        abstention_correct=None,
        overall_supported="uncertain",
        claims=[],
        citation_checks=[],
    )
    one = summarize(run, {key: base})
    two = summarize(run, {key: {**base, "context_consistent": True}})
    assert one["cross_turn_consistency"]["rate_assessed"] == 0
    assert two["cross_turn_consistency"]["rate_assessed"] == 1


def test_no_silent_partial_annotation_or_changed_source(tmp_path):
    make_run(tmp_path / "run")
    export(QUEUE, tmp_path / "run", tmp_path / "review")
    ratings = read(tmp_path / "review/annotation-A.json")
    ratings["ratings"][0]["task_correct"] = True
    write(tmp_path / "partial.json", ratings)
    with pytest.raises(ValueError, match="INCOMPLETE"):
        import_annotations(
            tmp_path / "review/private-key.json",
            tmp_path / "review/packet-A.json",
            tmp_path / "partial.json",
            tmp_path / "bad.json",
        )
    import_annotations(
        tmp_path / "review/private-key.json",
        tmp_path / "review/packet-A.json",
        tmp_path / "review/annotation-A.json",
        tmp_path / "import.json",
    )
    p = tmp_path / "run/turns.jsonl"
    p.write_text(p.read_text() + "\n")
    with pytest.raises(ValueError, match="SOURCE_RUN_CHANGED"):
        score(QUEUE, tmp_path / "review/private-key.json", [tmp_path / "import.json"], tmp_path / "bad.json")


def test_live_requires_explicit_caps_and_queue_before_any_io(tmp_path):
    for args, fragment in [(["--live"], "explicit call and USD"), ([], "--queue")]:
        cmd = [sys.executable, str(HERE / "pilot.py"), "--output", str(tmp_path / "absent"), *args]
        if args:
            cmd += ["--queue", str(QUEUE)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=ROOT)
        assert result.returncode == 2 and fragment in result.stderr
        assert not (tmp_path / "absent").exists()


def test_empty_and_degenerate_agreement_stays_null():
    from shared import agreement

    assert agreement([(None, "supported"), ("unsupported", None)])["agreement"] is None
    assert agreement([("supported", "supported")] * 2)["cohen_kappa"] is None
    pairs = (
        [("supported", "supported")] * 2
        + [("supported", "unsupported"), ("unsupported", "supported")]
        + [("unsupported", "unsupported")] * 2
    )
    a = agreement(pairs)
    assert a["agreement"] == pytest.approx(2 / 3) and a["cohen_kappa"] == pytest.approx(1 / 3)


def test_hand_constructed_annotation_import_reaches_task_scores(tmp_path):
    make_run(tmp_path / "run")
    export(QUEUE, tmp_path / "run", tmp_path / "review")
    packet = read(tmp_path / "review/packet-A.json")
    ratings = read(tmp_path / "review/annotation-A.json")
    item = next(i for i in packet["items"] if i["context_followup"] and i["outcome"] == "answered")
    row = next(r for r in ratings["ratings"] if r["item_id"] == item["item_id"])
    ratings["annotation_source"] = "HAND_CONSTRUCTED_FIXTURE"
    row.update(
        complete=True,
        overall_supported="unsupported",
        task_correct=False,
        context_consistent=False,
        reason="Hand-constructed test only",
        claims=[dict(claim_id="c", text="A claim.", requires_citation=True, citation_ids=[])],
    )
    write(tmp_path / "fixture-ratings.json", ratings)
    import_annotations(
        tmp_path / "review/private-key.json",
        tmp_path / "review/packet-A.json",
        tmp_path / "fixture-ratings.json",
        tmp_path / "import.json",
    )
    result = score(
        QUEUE, tmp_path / "review/private-key.json", [tmp_path / "import.json"], tmp_path / "scores.json"
    )
    assert result["task_correctness"]["assessed"] == 1 and result["task_correctness"]["rate_assessed"] == 0
    assert (
        result["cross_turn_consistency"]["assessed"] == 1
        and result["cross_turn_consistency"]["rate_assessed"] == 0
    )
    assert result["human_scores_status"] == "NOT_RUN"
    assert result["model_human_support_agreement"]["status"] == "NOT_RUN"


def test_original_random_sample_selection_is_unchanged(tmp_path):
    import random
    from collections import defaultdict

    from blind import export as original_export

    _, groups, _ = load()
    directory = tmp_path / "v1-full-fixture"
    directory.mkdir()
    write(
        directory / "config.json",
        dict(data_kind="MOCK", smoke=False, dataset_lock_sha256=digest(BASE / "dataset-lock.json")),
    )
    strata = defaultdict(list)
    with (directory / "turns.jsonl").open("w") as f:
        for split, ds in groups.items():
            for d in ds:
                for ordinal, t in enumerate(d["turns"], 1):
                    key = f"{d['dialogue_id']}:{ordinal}"
                    strata[(d["course_id"], t["category"])].append(key)
                    f.write(
                        json.dumps(
                            dict(
                                turn_key=key,
                                course_id=d["course_id"],
                                split=split,
                                script=t,
                                answer="Fixture only",
                                evaluation="",
                                status="completed",
                                outcome="answered",
                                citations=[],
                                review=None,
                            )
                        )
                        + "\n"
                    )
    original_export([directory], tmp_path / "v1-review")
    key = read(tmp_path / "v1-review/private-key.json")
    a = read(tmp_path / "v1-review/packet-A.json")
    b = read(tmp_path / "v1-review/packet-B.json")
    rng = random.Random(20261107)
    expected = set()
    overlap = set()
    for stratum in sorted(strata):
        values = sorted(strata[stratum])
        rng.shuffle(values)
        expected.update(values[:5])
        overlap.add(values[0])
    assert {key["mappings"][i["item_id"]]["turn_key"] for i in a["items"]} == expected
    assert {key["mappings"][i["item_id"]]["turn_key"] for i in b["items"]} == overlap
    assert len(a["items"]) == 100 and len(b["items"]) == 20
    assert sum(key["mappings"][i["item_id"]]["split"] == "holdout" for i in a["items"]) == 25


def test_v2_verifier_is_not_shadowed_by_legacy_module():
    from pathlib import Path

    import verify
    from shared import legacy

    assert Path(verify.__file__).resolve() == HERE / "verify.py"
    assert Path(legacy.__file__).resolve() == BASE / "run.py"
