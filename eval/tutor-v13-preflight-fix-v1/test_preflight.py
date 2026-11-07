"""Pre-live source-locator repair and exact unchanged task/candidate boundaries."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import entry as repaired

C = repaired.contract
pytest_plugins = ["test_grounding"]
from test_grounding import new_transport  # noqa: E402


def test_corrected_references_bind_all_workflow_locations():
    _, scripts, _, expected, _ = C.verify()
    by = {r["turn_key"]: r for r in expected}
    required = {
        "new-sheets-validation:1": ["minimum and maximum", "try again"],
        "new-sheets-validation:2": ["Input Message", "Style", "Error Alert"],
        "new-sheets-validation:3": ["Source", "drop-downlist", "sites A, B, and C"],
        "new-sheets-validation:4": ["Data Validation"],
        "new-sheets-qc:1": ["original file with the formulas", "stored as values", "organizing principles"],
        "new-sheets-qc:2": ["Expand the selection", "bottom", 'letter "g"'],
        "new-sheets-qc:3": ["2-Color Scale", "non-numerical values are not colored", 'letter "g"'],
        "new-sheets-qc:4": ["non-numerical values are not colored"],
    }
    for key, phrases in required.items():
        text = "\n".join(q["quote"] for q in by[key]["script"]["reference"]["quotes"])
        assert all(p in text for p in phrases), key
    _, base_scripts, _, _, _ = C.candidate.verify()
    assert [[t["text"] for t in s["turns"]] for s in scripts] == [
        [t["text"] for t in s["turns"]] for s in base_scripts
    ]
    for current, old in zip(scripts, base_scripts, strict=True):
        for t, b in zip(current["turns"], old["turns"], strict=True):
            for field in ("reference_points", "allowed_answer_boundary", "rubric", "insufficiency_reason"):
                assert t["reference"][field] == b["reference"][field]
    assert C.verify_candidate() == "70b4f27471a61fb6db64e1a8318b2e4540b2d1428614f5e29f3a6166f4dd43a7"


def test_protocol_functions_exactly_unchanged():
    import ast

    before = ast.parse((C.ROOT / "eval/tutor-v13-grounding-v1/trial_run.py").read_text())
    after = ast.parse((C.HERE / "trial_run_v2.py").read_text())
    for name in ("run", "classify", "preflight", "capture", "counts", "WireEvidence", "RerunChannel"):

        def node(tree, selected=name):
            return next(
                n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == selected
            )

        assert ast.dump(node(before), include_attributes=False) == ast.dump(
            node(after), include_attributes=False
        )


@pytest.mark.parametrize(
    "fault,cap,expected", [(None, 80, (16, 0, 0, 0)), ("local", 80, (12, 1, 3, 0)), (None, 1, (0, 1, 0, 15))]
)
def test_corrected_entry_full_mock_and_stops(isolated, tmp_path, fault, cap, expected):
    entry = repaired

    args = entry.parser().parse_args(
        [
            "--mock",
            "--agent",
            C.CANDIDATE,
            "--model",
            "deepseek-flash",
            "--max-calls",
            str(cap),
            "--max-usd",
            "0.70",
            "--output",
            str(tmp_path / "corrected"),
        ]
    )
    result = entry.run(args, dsn=isolated, transport=new_transport(fault))
    assert tuple(result[k] for k in ("completed", "failed", "skipped", "missing")) == expected
    assert result["reviewer_calls"] == 0 and result["quality_status"] == "NOT_RUN"
    import json

    import psycopg

    rows = [json.loads(x) for x in (tmp_path / "corrected/turns.jsonl").read_text().splitlines()]
    events = [json.loads(x) for x in (tmp_path / "corrected/ledger.jsonl").read_text().splitlines()]
    with psycopg.connect(isolated) as conn:
        assert [
            r[0] for r in conn.execute("SELECT record FROM p8_tutor_real_event ORDER BY sequence")
        ] == events
    assert len(rows) == 16


def test_every_reference_quote_matches_original_markdown():
    _, scripts, _, expected, _ = C.verify()
    sources = {s["course_id"]: s for s in C.data.read(C.candidate.HERE / "sources.json")["sources"]}
    assert len(expected) == 16 and len(scripts) == 4
    for row in expected:
        text = (C.candidate.HERE / sources[row["course_id"]]["local_path"]).read_text().splitlines()
        for q in row["script"]["reference"]["quotes"]:
            assert 1 <= q["line_start"] <= q["line_end"] <= len(text)
            assert q["quote"] == "\n".join(text[q["line_start"] - 1 : q["line_end"]])


def test_repaired_gate_refuses_changed_test_before_execution(tmp_path, monkeypatch):
    import shutil

    for name in ("entry.py", "test_preflight.py", "fix-lock.json"):
        shutil.copyfile(repaired.HERE / name, tmp_path / name)
    (tmp_path / "test_preflight.py").write_text("changed")
    monkeypatch.setattr(repaired, "HERE", tmp_path)
    with pytest.raises(ValueError, match="V13_PREFLIGHT_FIX_CHANGED"):
        repaired.verify_fix()
