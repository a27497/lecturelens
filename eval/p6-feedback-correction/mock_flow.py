"""Scripted lab actors through the real StudyRuntime and PostgreSQL, never a real provider.

Both feedback and student revisions are prewritten stimuli. Bad outcomes are deliberately
included to test measurement sensitivity. This is not a feedback-quality or learner study.
"""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.provider import MockProvider
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyError, StudyStore
from measure import ROOT, export_trial, load, safe_lab_dsn, verify_freeze, write_new


def now():
    return datetime.now(timezone.utc).isoformat()


class CourseAuthority:
    """Authorized fixture replay; does not impersonate Java or fresh course ingestion."""

    def __init__(self, scope, course):
        self.scope = scope
        self.evidence = course["evidence"]
        self.actions = []

    def read(self, scope, action="CHECK", **args):
        if any(scope.get(k) != v for k, v in self.scope.items()):
            raise StudyError("COURSE_UNAVAILABLE_OR_CHANGED")
        self.actions.append(action)
        evidence = self.evidence
        if action == "CHECK":
            evidence = []
        elif action == "READ":
            evidence = [e for e in evidence if e["evidence_id"] in args["evidence_ids"]]
            if len(evidence) != len(set(args["evidence_ids"])):
                raise StudyError("FEEDBACK_CITATION_MISMATCH")
        elif action == "WINDOW":
            if args["evidence_id"] not in {e["evidence_id"] for e in evidence}:
                raise StudyError("FEEDBACK_CITATION_MISMATCH")
        elif action != "SEARCH":
            raise StudyError("UNEXPECTED_EVALUATION_TOOL")
        return self.scope | {"evidence": evidence}


class ScriptedProvider(MockProvider):
    def __init__(self, item, initial, observation, action="revise", insufficient=False):
        self.item, self.initial, self.observation = item, initial, observation
        self.action, self.insufficient = action, insufficient
        self.calls = 0

    def decide(self, messages, timeout):
        self.calls += 1
        result = super().decide(messages, timeout)
        if result["name"] == "create_practice_set":
            # Task wording comes from the frozen task, not generated feedback.
            result["arguments"]["questions"][0].update(
                question=self.item["question"],
                evidence_ids=list(
                    dict.fromkeys(
                        e for f in self.item["facts"] for e in f["required_evidence"]
                    )
                ),
            )
        return result

    def review(self, messages, timeout):
        self.calls += 1
        return super().review(messages, timeout)

    def feedback(self, messages, schemas, timeout, *, review=False):
        self.calls += 1
        if review:
            return super().feedback(messages, schemas, timeout, review=True)
        body = json.loads(messages[-1]["content"])
        if not body["observations"]:
            return {"calls": [{"name": "read_question_evidence", "arguments": {}}]}
        if self.insufficient:
            return {
                "calls": [
                    {
                        "name": "report_feedback_insufficient",
                        "arguments": {"reason": self.observation},
                    }
                ]
            }
        ids = list(
            dict.fromkeys(e for f in self.item["facts"] for e in f["required_evidence"])
        )
        return {
            "calls": [
                {
                    "name": "submit_answer_feedback",
                    "arguments": {
                        "observations": [
                            {
                                "learner_quote": self.initial,
                                "observation": self.observation,
                                "action": self.action,
                                "evidence_ids": ids,
                            }
                        ]
                    },
                }
            ]
        }


def counts(store, session_id):
    with store.connect() as conn:
        return conn.execute(
            "SELECT count(*) AS runs,coalesce(sum(model_calls),0) AS model_calls,"
            "coalesce(sum(tool_calls),0) AS tool_calls FROM study_run WHERE session_id=%s",
            (session_id,),
        ).fetchone()


def run_trial(store, course, item, fixture, folder):
    (
        trial_id,
        condition,
        initial,
        final,
        observation,
        action,
        insufficient,
        discovery,
    ) = fixture
    scope = {
        "owner_id": 600006,
        "course_id": course["course_key"] + "-" + uuid.uuid4().hex,
        "revision": 1,
    }
    authority = CourseAuthority(scope.copy(), course)
    provider = ScriptedProvider(item, initial, observation, action, insufficient)
    runtime = StudyRuntime(store, authority, provider)
    runtime.initialize()

    def command(operation, **kwargs):
        return store.command(
            StudyCommand(**(scope | kwargs | {"operation": operation})), "mock"
        )

    scope["session_id"] = command("CREATE_SESSION", request_key=trial_id)["session_id"]
    response = command(
        "START", request_key="practice", goal="按指定题目进行合成测量机制演练"
    )

    def execute(run_id):
        candidate = next(r for r in store.candidates() if r["run_id"] == run_id)
        runtime.execute(candidate)
        response = command("READ", run_id=run_id)
        write_new(folder / f"{trial_id}-{run_id}.json", response)
        if response["run"]["status"] != "succeeded":
            raise ValueError(
                f"Mechanism trial failed: {trial_id}; raw failure preserved"
            )
        return response

    parent = execute(response["run"]["run_id"])
    scope.update(
        run_id=parent["run"]["run_id"],
        artifact_id=parent["artifact"]["artifact_id"],
        question_index=0,
    )
    first = command(
        "SAVE_ATTEMPT", request_key="initial", expected_version=0, answer_text=initial
    )["attempt"]
    exposures = []
    if condition == "feedback":
        response = command(
            "START_FEEDBACK", request_key="feedback", attempt_id=first["attempt_id"]
        )
        feedback_run_id = response["run"]["run_id"]
        f = execute(feedback_run_id)["feedback"]
        exposures.append(
            {
                "run_id": feedback_run_id,
                "feedback_id": f["feedback_id"],
                "answer_version_at_exposure": first["version"],
                "at": now(),
            }
        )
        command(
            "SAVE_FEEDBACK_NOTE",
            run_id=feedback_run_id,
            feedback_id=f["feedback_id"],
            request_key="check",
            expected_version=0,
            disposition="acknowledged",
            note_text="[脚本演员，非真人] 核对课程来源。" + discovery,
        )
    source_checks = []
    for evidence_id in dict.fromkeys(
        e for f in item["facts"] for e in f["required_evidence"]
    ):
        authority.read(scope, "READ", evidence_ids=[evidence_id])
        source_checks.append(
            {"evidence_id": evidence_id, "at": now(), "observer": "SCRIPTED_ACTOR"}
        )
    discovery_record = {
        "text": discovery,
        "at": now(),
        "origin": "SCRIPTED_ACTOR_NOT_STUDENT",
    }
    last = command(
        "SAVE_ATTEMPT", request_key="final", expected_version=1, answer_text=final
    )["attempt"]
    # Reconstruct readers after writing; export cannot rely on returned SAVE payloads alone.
    restarted = StudyStore(store.dsn)
    before, calls_before = counts(store, scope["session_id"]), provider.calls
    spec = {
        "trial_id": trial_id,
        "item_id": item["item_id"],
        "question": item["question"],
        "condition": condition,
        "data_kind": "MOCK",
        "scope": scope.copy(),
        "initial_attempt_id": first["attempt_id"],
        "final_attempt_id": last["attempt_id"],
        "feedback_exposures": exposures,
        "source_checks": source_checks,
        "discovery": discovery_record,
        "participant": "SCRIPTED_ACTOR",
        "status": "complete",
        "final_evidence": {
            "attempt_id": last["attempt_id"],
            "claims": [
                {
                    "fact_id": f["id"],
                    "evidence_ids": f["required_evidence"],
                    "reason": "[脚本演员，非真人] 以课程此处的规则支持最终表述。",
                }
                for f in item["facts"]
            ],
        },
    }
    for _ in range(2):
        command("LIST")
        command("RUNS")
        command("READ")
        command("EVENTS")
        for check in source_checks:
            authority.read(scope, "READ", evidence_ids=[check["evidence_id"]])
        exported = export_trial(restarted, spec, course)
    after = counts(store, scope["session_id"])
    assert before == after and provider.calls == calls_before
    assert (
        exported["initial"]["answer_text"] == initial
        and exported["final"]["answer_text"] == final
    )
    if exposures:
        assert exported["feedback"][0]["feedback"]["answer_version"] == 1
        assert exported["feedback"][0]["stale_after_revision"] is True
    return (
        spec,
        exported,
        {
            "trial_id": trial_id,
            "before": before,
            "after": after,
            "provider_calls_before": calls_before,
            "provider_calls_after": provider.calls,
            "operations": [
                "LIST",
                "RUNS",
                "READ",
                "EVENTS",
                "ATTEMPT_HISTORY",
                "FEEDBACK_NOTES_IF_PRESENT",
                "fixture source READ",
            ],
            "actual_postgres": True,
            "java_authority": "FIXTURE_REPLAY_NOT_RUN",
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frozen = verify_freeze()
    args.output.mkdir(parents=True, exist_ok=False)
    # A credential-free deterministic runner has no reason to open a remote socket.
    original_connect = socket.socket.connect

    def loopback_only(sock, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
            raise RuntimeError("P6 blocks non-loopback network connections")
        return original_connect(sock, address)

    socket.socket.connect = loopback_only
    os.environ["STUDY_FEEDBACK_ENABLED"] = "true"
    store = StudyStore(safe_lab_dsn(os.environ["AGENT_TEST_DATABASE_URL"]))
    course = load(ROOT / "development/course.json")
    items = {i["item_id"]: i for i in load(ROOT / "development/standard.json")["items"]}
    samples = {
        s["id"]: s for s in load(ROOT / "development/initial-answers.json")["samples"]
    }
    bad, good = samples["one_error"]["answer"], samples["correct"]["answer"]
    fixtures = [
        (
            "read-correct",
            "reading",
            bad,
            good,
            "",
            "revise",
            False,
            "原来的最多1次有误，应为最多n次。",
        ),
        (
            "feedback-correct",
            "feedback",
            bad,
            good,
            "最多1次有误，课程说最多n次比较。",
            "revise",
            False,
            "原来的最多1次有误，应为最多n次。",
        ),
        (
            "feedback-misled",
            "feedback",
            good,
            bad,
            "最多n次错误，应改为最多1次。",
            "revise",
            False,
            "[故意错误刺激] 接受反馈，把n次改为1次。",
        ),
        (
            "feedback-honest",
            "feedback",
            samples["insufficient"]["answer"],
            "不能确定秒数，课程没有给出单次比较耗时或机器速度。",
            "课程未提供速度或单次耗时，不能确定精确秒数。",
            "revise",
            True,
            "3次不等于3秒，缺耗时依据。",
        ),
        (
            "feedback-refusal",
            "feedback",
            samples["confused"]["answer"],
            samples["confused"]["answer"],
            "课程证据不足，无法区分停止条件和上界。",
            "revise",
            True,
            "未发现问题，保留原答。",
        ),
        (
            "feedback-missed",
            "feedback",
            "查找4比较3次且找到；查找7比较3次且未找到。",
            "查找4比较3次且找到；查找7比较3次且未找到。",
            "两种查找的比较次数都正确。",
            "retain",
            False,
            "未发现问题，接受反馈并保留原答。",
        ),
    ]
    item_ids = ["d1", "d1", "d1", "d3", "d4", "d2"]
    specs, exports, audits = [], [], []
    for fixture, item_id in zip(fixtures, item_ids, strict=True):
        spec, exported, audit = run_trial(
            store, course, items[item_id], fixture, args.output
        )
        specs.append(spec)
        exports.append(exported)
        audits.append(audit)
    write_new(
        args.output / "manifest.json",
        {"data_kind": "MOCK", "trials": specs, "incomplete_trials": []},
    )
    write_new(
        args.output / "export.json",
        {
            "data_kind": "MOCK",
            "freeze_hash": frozen,
            "trials": exports,
            "incomplete_trials": [],
        },
    )
    write_new(
        args.output / "checks.json",
        {
            "warning": "Mock 数据，不代表教学效果",
            "trials": audits,
            "real_paid_provider_calls": 0,
            "browser": "BROWSER_NOT_RUN",
            "baseline": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
            "source_hashes": {
                str(p.relative_to(ROOT.parents[1])): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in sorted((ROOT.parents[1] / "agent-service/src").rglob("*.py"))
            }
            | {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [Path(__file__), ROOT / "measure.py"]
            },
        },
    )
    print(
        "6 scripted trials exported; read-only counts unchanged; real provider calls=0"
    )


if __name__ == "__main__":
    main()
