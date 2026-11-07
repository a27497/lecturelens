"""Public text contract and bounded Mock adapter checks; no semantic gold claims."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import public_dataset as data
import pytest
from public_bridge import execution_counts, failure_items, legacy
from public_mock import reconcile, run
from public_review import export, read_run, score


def test_counts_and_varied_session_shapes():
    snapshot, groups = data.load()
    assert len(snapshot["lectures"]) == 3
    assert [(len(ds), sum(len(d["turns"]) for d in ds)) for ds in groups.values()] == [
        (8, 40),
        (4, 20),
    ]
    ds = [d for dialogues in groups.values() for d in dialogues]
    assert {len(d["turns"]) for d in ds} == {4, 5, 6}
    assert all(
        sum(len(d["turns"]) for d in ds if d["course_id"] == c) == 20
        for c in snapshot["lectures"]
    )
    assert len({tuple(t["category"] for t in d["turns"]) for d in ds}) == 12


def test_course_and_complete_session_selection():
    snap, ds = data.select("development", ["carpentries-python"], ["python-02"])
    assert list(snap["lectures"]) == ["carpentries-python"]
    assert [d["dialogue_id"] for d in ds] == ["python-02"] and len(ds[0]["turns"]) == 6
    for split, courses, sessions in [
        ("development", None, ["sql-01"]),
        ("holdout", None, None),
        ("all", None, None),
        ("development", [], None),
        ("development", ["carpentries-sql"], None),
        ("development", None, ["python-01", "python-01"]),
    ]:
        with pytest.raises(ValueError):
            data.select(split, courses, sessions)
    held, ds = data.select("holdout", allow_holdout=True)
    assert list(held["lectures"]) == ["carpentries-sql"] and len(ds) == 4


def test_all_reference_quotes_resolve_to_original_line_bytes():
    snapshot, groups = data.load()
    for dialogues in groups.values():
        for d in dialogues:
            evidence = {
                e["evidence_id"]: e
                for e in snapshot["lectures"][d["course_id"]]["evidence"]
            }
            for t in d["turns"]:
                ref = t["reference"]
                assert (
                    ref["reference_points"]
                    and ref["allowed_answer_boundary"]
                    and ref["rubric"]
                )
                assert bool(ref["insufficiency_reason"]) == t["expected_insufficient"]
                for q in ref["quotes"]:
                    e = evidence[q["evidence_id"]]
                    lines = (
                        (data.HERE / e["source_path"])
                        .read_text()
                        .splitlines(keepends=True)
                    )
                    assert q["quote"] == "".join(
                        lines[q["line_start"] - 1 : q["line_end"]]
                    ).rstrip("\n")
                    assert q["quote"] in e["text"] and e["start_ms"] == e["end_ms"] == 0


def test_modified_source_rejected_without_touching_assets(tmp_path):
    scratch = tmp_path / "copy"
    shutil.copytree(data.HERE, scratch)
    with (scratch / "materials/carpentries-python.md").open("a") as f:
        f.write("\nCORRUPTED\n")
    with (
        patch.object(data, "HERE", scratch),
        pytest.raises(ValueError, match="FROZEN_INPUT_CHANGED"),
    ):
        data.load()


def test_split_and_version_tampering_rejected(tmp_path):
    scratch = tmp_path / "copy"
    shutil.copytree(data.HERE, scratch)
    (scratch / "course-split.json").write_text("{}")
    with (
        patch.object(data, "HERE", scratch),
        pytest.raises(ValueError, match="SPLIT_CHANGED"),
    ):
        data.project()
    lock = data.read(data.HERE / "dataset-lock.json")
    lock["version"] = "other"
    (scratch / "dataset-lock.json").write_text(json.dumps(lock))
    with (
        patch.object(data, "HERE", scratch),
        pytest.raises(ValueError, match="FROZEN_INPUT_CHANGED"),
    ):
        data.load()


def test_projection_is_reproducible_and_exclusive(tmp_path):
    for filename in (
        "course-split.json",
        "course-split.sha256",
        "sources.json",
        "author_public.py",
    ):
        shutil.copyfile(data.HERE / filename, tmp_path / filename)
    shutil.copytree(data.HERE / "materials", tmp_path / "materials")
    with patch.object(data, "HERE", tmp_path):
        data.build()
        for name in (
            "development.json",
            "holdout.json",
            "snapshot.json",
            "holdout-manifest.json",
            "dataset-lock.json",
        ):
            assert (tmp_path / name).read_bytes() == (
                Path(__file__).parent / name
            ).read_bytes()
        with pytest.raises(FileExistsError):
            data.build()


def test_tutor_wire_contains_no_evaluation_reference_fields():
    snapshot, scripts = data.select("all", allow_holdout=True)
    runtime = legacy.TutorRuntime(None, None)
    with patch.object(runtime, "read_evidence", return_value=[]):
        for task in [t for d in scripts for t in d["turns"]]:
            turn = legacy.Command(
                owner_id=811009,
                course_id="test",
                revision=1,
                operation="TURN",
                session_id="session",
                client_turn_id="turn",
                text=task["text"],
                socratic=task["socratic"],
            )
            messages, _, _ = runtime.request(
                {"summary": ""},
                {"learner_text": turn.text, "socratic": turn.socratic},
                {"selected": [], "observations": []},
                [],
            )
            body = json.loads(messages[-1]["content"])
            assert body["learner_text"] == task["text"]
            assert not set(body) & {
                "reference",
                "expected_topic",
                "expected_insufficient",
                "rubric",
                "reference_points",
                "answerability",
                "split",
                "depends_on_turns",
            }
    assert all("reference" not in lecture for lecture in snapshot["lectures"].values())


def test_no_live_entry_and_fence_required(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(data.HERE / "public_mock.py"),
            "--split",
            "development",
            "--output",
            str(tmp_path / "forbidden"),
            "--live",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(data.ROOT / "agent-service/src")},
    )
    assert result.returncode != 0 and "unrecognized arguments: --live" in result.stderr
    with (
        patch.dict(os.environ, {"LECTURELENS_PREFLIGHT_GUARDED": "0"}),
        pytest.raises(ValueError, match="FENCED"),
    ):
        run(None)


def test_missing_and_failed_remain_in_planned_denominator():
    snapshot, scripts = data.select("development", sessions=["python-01"])
    planned = data.expected_rows(snapshot, scripts)
    rows = reconcile(planned, [])
    assert execution_counts(rows)["missing_result_turns"] == 4
    rows[0].update(status="failed", error_code="TUTOR_DEADLINE")
    run_data = {
        "rows": rows,
        "config": {"data_kind": "MOCK"},
        "directory": "fixture",
        "queue_sha256": "fixture",
        "result_origin": "HAND_CONSTRUCTED_FIXTURE",
        "input_hashes": {},
    }
    failed = failure_items(run_data)
    assert len(failed["items"]) == 4
    assert "TIMEOUT_OR_DEADLINE" in failed["items"][0]["reasons"]
    assert (
        failed["counts"]["expected_turns"] == 4
        and failed["counts"]["failed_turns"] == 1
    )
    with pytest.raises(ValueError, match="DUPLICATE"):
        reconcile(planned, [rows[0], rows[0]])


def fixture_run(directory):
    directory.mkdir()
    snapshot, scripts = data.select("all", allow_holdout=True)
    planned = data.expected_rows(snapshot, scripts)
    config = {
        "scope": "all",
        "selected_dialogue_ids": [d["dialogue_id"] for d in scripts],
        "data_kind": "MOCK",
        "live": False,
        "dataset_lock_sha256": data.digest(data.HERE / "dataset-lock.json"),
        "expected_turns_sha256": data.object_hash(planned),
    }
    data.write(directory / "config.json", config)
    data.write(
        directory / "expected-turns.json",
        {"dataset_lock_sha256": config["dataset_lock_sha256"], "turns": planned},
    )
    rows = reconcile(planned, [])
    with (directory / "turns.jsonl").open("x") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_census_blinding_overlap_reproducibility_and_empty_scores(tmp_path):
    directory = tmp_path / "fixture"
    fixture_run(directory)
    first, second = tmp_path / "review1", tmp_path / "review2"
    assert export(directory, first) == {
        "primary": 60,
        "independent_overlap": 12,
        "human_scores_status": "NOT_RUN",
    }
    export(directory, second)
    key = data.read(first / "private-key.json")
    assert (first / "private-key.json").stat().st_mode & 0o777 == 0o600
    imports = []
    from public_bridge import import_annotations

    for rater in ("A", "B"):
        packet_path = first / f"packet-{rater}.json"
        assert (
            packet_path.read_bytes() == (second / f"packet-{rater}.json").read_bytes()
        )
        packet = data.read(packet_path)
        assert len(packet["items"]) == (60 if rater == "A" else 12)
        assert all(i["status"] == "MISSING" for i in packet["items"])
        for item in packet["items"]:
            assert not set(item) & {
                "model",
                "code_sha",
                "version",
                "candidate_sha256",
                "review",
                "turn_key",
            }
        if rater == "B":
            assert all(
                key["mappings"][i["item_id"]].endswith(":2") for i in packet["items"]
            )
        imported = tmp_path / f"import-{rater}.json"
        import_annotations(
            first / "private-key.json",
            packet_path,
            first / f"annotation-{rater}.json",
            imported,
        )
        imports.append(imported)
    result = score(first / "private-key.json", imports, tmp_path / "score.json")
    assert result["human_scores_status"] == result["quality_status"] == "NOT_RUN"
    assert result["execution"]["missing_result_turns"] == 60
    assert result["task_correctness"]["rate_assessed"] is None
    assert result["model_human_support_agreement"]["comparable"] == 0
    overlap = result["independent_human_overlap_support_agreement"]
    assert overlap["eligible"] == overlap["excluded"] == 12
    assert overlap["comparable"] == 0 and overlap["status"] == "NOT_RUN"
    assert len(read_run(directory)["rows"]) == 60
