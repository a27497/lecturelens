"""Scope, no-egress, denominators and source checks; no quality oracle tests."""

import json
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import batch_run
import bridge
import data


@pytest.fixture(autouse=True)
def no_real_provider(monkeypatch):
    original = os.environ.get

    def get(key, *args):
        if key in {"AGENT_LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"}:
            pytest.fail("No provider credentials may be read")
        return original(key, *args)

    monkeypatch.setattr(os.environ, "get", get)
    monkeypatch.setattr(
        httpx, "HTTPTransport", lambda **kw: pytest.fail("Real transport forbidden")
    )


def options(*extra):
    return batch_run.parser().parse_args(
        ["--agent", bridge.repair_check.CANDIDATE, "--model", "deepseek-flash", *extra]
    )


def test_development_scope_complete_and_distinct():
    batch, scripts, snapshot = data.load()
    assert batch["counts"] == {"courses": 2, "sessions": 4, "turns": 16}
    assert set(snapshot["lectures"]) == data.COURSES
    assert sorted(len(d["turns"]) for d in scripts) == [3, 3, 5, 5]
    old = data.read(data.ROOT / "eval/tutor-public-v1/development.json")["dialogues"]
    assert not {d["dialogue_id"] for d in scripts} & {d["dialogue_id"] for d in old}
    # Exact-text exclusion complements the separately documented semantic novelty review.
    new_questions = {t["text"] for d in scripts for t in d["turns"]}
    assert not new_questions & {t["text"] for d in old for t in d["turns"]}
    assert sum(t["expected_insufficient"] for d in scripts for t in d["turns"]) == 4
    assert sum(t["context_followup"] for d in scripts for t in d["turns"]) == 10
    for part in batch["parts"]:
        plan = data.read(data.HERE / part["path"])
        assert len(plan["turn_keys"]) == 8 and len(plan["sessions"]) == 2
        assert len({s["course_id"] for s in plan["sessions"]}) == 2


def test_every_reference_is_exact_original_lines():
    _, scripts, snapshot = data.load()
    for d in scripts:
        rows = {
            e["evidence_id"]: e
            for e in snapshot["lectures"][d["course_id"]]["evidence"]
        }
        for turn in d["turns"]:
            for q in turn["reference"]["quotes"]:
                row = rows[q["evidence_id"]]
                lines = (
                    (data.ROOT / "eval/tutor-public-v1" / row["source_path"])
                    .read_text()
                    .splitlines()
                )
                assert q["quote"] == "\n".join(
                    lines[q["line_start"] - 1 : q["line_end"]]
                )
                assert q["quote"] in row["text"]
                assert q["locator"].endswith(f"#L{q['line_start']}-L{q['line_end']}")


@pytest.mark.parametrize(
    "filename",
    [
        "questions.json",
        "sources.json",
        "snapshot.json",
        "grading-rules.json",
        "part-A.json",
        "batch-plan.json",
        "candidate-freeze.json",
    ],
)
def test_frozen_changes_rejected(tmp_path, monkeypatch, filename):
    for source in data.HERE.glob("*.json"):
        shutil.copy(source, tmp_path / source.name)
    (tmp_path / filename).write_text("{}")
    monkeypatch.setattr(data, "HERE", tmp_path)
    with pytest.raises(ValueError, match="FROZEN_BATCH_INPUT_CHANGED"):
        data.load()


def test_v11_identity_and_pure_compatibility():
    assert bridge.verify_candidate() == data.CANDIDATE_SHA
    assert "author_public" not in sys.modules
    with pytest.raises(ValueError, match="OLD_SCOPE"):
        bridge.module.select("development")
    for path in [
        bridge.PUBLIC / "holdout.json",
        bridge.PUBLIC / "author_public.py",
        bridge.PUBLIC / "snapshot.json",
        bridge.PUBLIC / "materials/carpentries-sql.md",
    ]:
        with pytest.raises(PermissionError, match="NO_"):
            path.read_bytes()


def test_prepare_has_no_db_transport_or_key_lookup():
    with patch.object(
        bridge.legacy, "Ledger", side_effect=AssertionError("DB forbidden")
    ):
        result = batch_run.run(options())
    assert (
        result["mode"] == "PREPARE_ONLY_NO_EGRESS" and result["counts"]["turns"] == 16
    )
    assert (
        result["normal_requests"],
        result["second_search_path_requests"],
        result["maximum_requests"],
    ) == (32, 48, 80)


@pytest.mark.parametrize(
    "extra",
    [
        ["--max-calls", "81", "--max-usd", "0.1"],
        ["--max-calls", "1", "--max-usd", "0.1"],
        ["--max-calls", "40", "--max-usd", "0"],
        ["--max-calls", "40", "--max-usd", "0.71"],
    ],
)
def test_invalid_caps_fail_before_db(tmp_path, monkeypatch, extra):
    monkeypatch.setenv("LECTURELENS_PREFLIGHT_GUARDED", "1")
    with (
        patch.object(
            bridge.legacy, "Ledger", side_effect=AssertionError("DB forbidden")
        ),
        pytest.raises(ValueError),
    ):
        batch_run.run(
            options("--mock", "--output", str(tmp_path / "must-not-exist"), *extra)
        )
    assert not (tmp_path / "must-not-exist").exists()


def test_mock_requires_socket_fence(tmp_path, monkeypatch):
    monkeypatch.delenv("LECTURELENS_PREFLIGHT_GUARDED", raising=False)
    with pytest.raises(ValueError, match="SOCKET_FENCE"):
        batch_run.run(
            options(
                "--mock",
                "--max-calls",
                "80",
                "--max-usd",
                "0.7",
                "--output",
                str(tmp_path / "no"),
            )
        )


def test_live_has_no_inherited_authority(tmp_path, monkeypatch):
    monkeypatch.delenv("LECTURELENS_REAL_EVAL", raising=False)
    with (
        patch.object(
            bridge.legacy, "Ledger", side_effect=AssertionError("DB forbidden")
        ),
        pytest.raises(bridge.legacy.EvalError),
    ):
        batch_run.run(
            options(
                "--live",
                "--max-calls",
                "80",
                "--max-usd",
                "0.1",
                "--output",
                str(tmp_path / "no"),
            )
        )


def test_missing_and_failed_keep_all_denominators():
    _, scripts, snapshot = data.load()
    planned = bridge.module.expected_rows(snapshot, scripts)
    missing = bridge.reconcile(planned, [])
    assert bridge.execution_counts(missing)["missing_result_turns"] == 16
    failed = dict(missing[0], status="failed", error_code="SYNTHETIC_TIMEOUT")
    rows = bridge.reconcile(planned, [failed])
    counts = bridge.execution_counts(rows)
    assert (
        counts["expected_turns"],
        counts["failed_turns"],
        counts["missing_result_turns"],
    ) == (16, 1, 15)
    score = bridge.summarize(
        {"rows": rows, "planned": planned, "config": {"data_kind": "MOCK"}}, {}
    )
    assert score["task_correctness"]["status"] == "NOT_RUN"


def test_question_reference_boundary_and_fixed_candidate_request():
    _, scripts, snapshot = data.load()
    from lecturelens_real_eval.tutor.grounded_runtime import (
        SYSTEM,
        GroundedTutorRuntime,
        PassageAuthority,
    )

    a = PassageAuthority(snapshot)
    runtime = GroundedTutorRuntime(None, a)
    for d in scripts:
        scope = {"owner_id": 811012, "course_id": d["dialogue_id"], "revision": 1}
        a.register(scope, d["course_id"])
        for t in d["turns"]:
            messages, _schemas, _ = runtime.request(
                {**scope, "summary": ""},
                {"learner_text": t["text"], "socratic": False},
                {"selected": [], "observations": []},
                [],
            )
            payload = json.loads(messages[-1]["content"])
            assert (
                payload["learner_text"] == t["text"]
                and messages[0]["content"] == SYSTEM
            )
            assert set(payload).isdisjoint(
                {
                    "reference",
                    "rubric",
                    "expected_insufficient",
                    "answerability",
                    "tags",
                    "depends_on_turns",
                }
            )
    # Source-defined examples may legitimately equal references; references are not an input channel.
    assert "xyge" not in SYSTEM and "North America" not in SYSTEM


def test_independent_string_reference_arithmetic():
    e = "oxygen"
    assert (e[-1], e[-2], e[1:-1]) == ("n", "e", "xyge")
    assert "carpentry"[-3:] == "try" and "hi"[-3:] == "hi"
