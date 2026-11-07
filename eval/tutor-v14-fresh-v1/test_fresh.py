"""Single-use new v14 entry preflight and full-position protocol checks; Mock only."""

import ast
import json
import os
import sys
from pathlib import Path

import httpx
import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_fresh as E
from lecturelens_real_eval.tutor.draft_repair_runtime import ENTAILMENT
from lecturelens_real_eval.tutor.runtime import MockTutor

pytest_plugins = ["test_v14"]
C = E.contract


def lines(path):
    return [json.loads(x) for x in path.read_text().splitlines()]


def options(output, cap=80, money="0.70"):
    return E.parser().parse_args(
        [
            "--mock",
            "--agent",
            C.CANDIDATE,
            "--model",
            "deepseek-flash",
            "--max-calls",
            str(cap),
            "--max-usd",
            money,
            "--output",
            str(output),
        ]
    )


def transport(fault=None):
    model = MockTutor()
    first = C.verify()[1][0]["turns"][0]["text"]

    def send(request):
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-flash" and payload["max_tokens"] == 1200
        assert payload["temperature"] == 0 and payload["thinking"] == {"type": "disabled"}
        assert ENTAILMENT in payload["messages"][0]["content"]
        body = json.loads(payload["messages"][-1]["content"])
        assert not {"reference", "rubric", "reference_points", "grading_rules"} & set(body)
        if fault == "auth":
            return httpx.Response(401)
        decision = model.decide(payload["messages"], payload["tools"], 20)
        if fault == "local" and body["learner_text"] == first and body["observations"]:
            decision = dict(name="finish_tutor_turn", arguments=dict(outcome="answered", text="x" * 1601))
        value = dict(
            id="SYNTHETIC_V14_ONLY",
            model="MOCK_ONLY",
            usage=dict(
                prompt_tokens=10,
                completion_tokens=10,
                total_tokens=20,
                prompt_cache_hit_tokens=0,
                prompt_cache_miss_tokens=10,
            ),
            choices=[
                dict(
                    finish_reason="tool_calls",
                    message=dict(
                        tool_calls=[
                            dict(
                                type="function",
                                function=dict(
                                    name=decision["name"], arguments=json.dumps(decision["arguments"])
                                ),
                            )
                        ]
                    ),
                )
            ],
        )
        if fault == "usage":
            value.pop("usage")
        return httpx.Response(200, json=value)

    return httpx.MockTransport(send)


@pytest.mark.parametrize(
    "fault,cap,money,expected",
    [
        (None, 80, "0.70", (16, 0, 0, 0, 32)),
        ("local", 80, "0.70", (12, 1, 3, 0, 27)),
        ("auth", 80, "0.70", (0, 1, 0, 15, 1)),
        ("usage", 80, "0.70", (0, 1, 0, 15, 1)),
        (None, 1, "0.70", (0, 1, 0, 15, 1)),
        (None, 80, "0.000000001", (0, 1, 0, 15, 0)),
    ],
)
def test_complete16_and_frozen_faults(isolated, tmp_path, fault, cap, money, expected):
    out = tmp_path / "fresh-mock"
    summary = E.run(options(out, cap, money), dsn=isolated, transport=transport(fault))
    assert (
        tuple(summary[k] for k in ("completed", "failed", "skipped", "missing", "wire_requests")) == expected
    )
    assert summary["reviewer_calls"] == 0 and summary["quality_status"] == "NOT_RUN"
    assert summary["candidate"] == C.CANDIDATE
    rows = lines(out / "turns.jsonl")
    assert len(rows) == 16
    if fault == "local":
        assert rows[1]["skip_code"] == "DEPENDENCY_FAILED_OR_SKIPPED"
        assert rows[2]["skip_code"] == "SESSION_CLOSED_AFTER_LOCAL_FAILURE"
        assert all(r["status"] == "completed" for r in rows[4:])
    with psycopg.connect(isolated) as conn:
        assert [
            r[0] for r in conn.execute("SELECT record FROM p8_tutor_real_event ORDER BY sequence")
        ] == lines(out / "ledger.jsonl")
    output = Path(os.environ["V14_FRESH_CHECK_OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    with (output / (str(fault) + "-" + str(cap) + "-" + money + ".json")).open("x") as f:
        json.dump(summary, f, indent=2)


def test_same_failure_protocol_and_source_review():
    old = ast.parse((C.ROOT / "eval/tutor-v13-grounding-v2/trial_run_v2.py").read_text())
    new = ast.parse((C.HERE / "run_fresh.py").read_text())
    for name in ("accounting_safe", "classify", "counts", "capture", "RerunChannel", "WireEvidence"):
        a = next(n for n in old.body if getattr(n, "name", None) == name)
        b = next(n for n in new.body if getattr(n, "name", None) == name)
        assert ast.dump(a, include_attributes=False) == ast.dump(b, include_attributes=False)
    plan, scripts, snapshot, expected, _ = C.verify()
    assert len(expected) == 16 and plan["candidate_sha256"] == C.verify_candidate()
    assert len(snapshot["lectures"]) == 2
    assert sum(t["context_followup"] for s in scripts for t in s["turns"]) == 10
    assert len(C.data.read(C.HERE / "CONTENT_REVIEW.json")["positions"]) == 16
    old_questions = set()
    for folder in ("tutor-fresh-dev-v1", "tutor-v13-grounding-v1"):
        old_questions.update(
            t["text"]
            for s in C.data.read(C.ROOT / "eval" / folder / "questions.json")["dialogues"]
            for t in s["turns"]
        )
    assert not old_questions & {
        t["text"] for s in C.data.read(C.HERE / "questions.json")["dialogues"] for t in s["turns"]
    }


@pytest.mark.parametrize(
    "filename", ["run-plan.json", "grading-rules.json", "development.json", "snapshot.json"]
)
def test_modified_asset_rejected_before_db(tmp_path, monkeypatch, filename):
    lock = C.data.read(C.HERE / "freeze-lock.json")
    for name in lock["files"]:
        (tmp_path / name).write_bytes((C.HERE / name).read_bytes())
    (tmp_path / "freeze-lock.json").write_text(json.dumps(lock))
    (tmp_path / filename).write_text("{}")
    monkeypatch.setattr(C, "HERE", tmp_path)
    with pytest.raises(ValueError, match="V14_FRESH_FREEZE_CHANGED"):
        E.preflight(options(tmp_path / "refused"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("agent", "p8-tutor-claim-grounding-v13-development"),
        ("max_calls", 81),
        ("max_usd", "0.71"),
        ("reviewer", "on"),
        ("concurrency", 2),
    ],
)
def test_wrong_settings_refused(tmp_path, field, value):
    args = options(tmp_path / "refused")
    setattr(args, field, value)
    with pytest.raises((ValueError, E.bridge.legacy.EvalError)):
        E.preflight(args)


def test_preparation_and_live_socket_fence_before_credential(tmp_path):
    args = E.parser().parse_args(["--agent", C.CANDIDATE, "--model", "deepseek-flash"])
    assert E.run(args)["mode"] == "PREPARE_ONLY_NO_EGRESS"
    args = options(tmp_path / "refused")
    args.mock, args.live = False, True
    with pytest.raises(ValueError, match="LIVE_FORBIDDEN_INSIDE_OFFLINE_FENCE"):
        E.preflight(args)
