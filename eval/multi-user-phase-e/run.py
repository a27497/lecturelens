"""Virtual users over real Java login/Authority/Session/Run, with bounded eval workers.

No direct database writes: state changes use Java or the unchanged StudyRuntime.
Only model responses are fixed in deterministic mode. Raw output must stay in .data.
"""

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import httpx
from serve import ROOT, configure

from lecturelens_agent.study.authority import (  # noqa: E402
    AUTHORITY_PATH,
    EvidenceAuthority,
    request_body,
    signature,
)
from lecturelens_agent.study.models import ModelRegistry, RegistryProvider  # noqa: E402
from lecturelens_agent.study.provider import MockProvider  # noqa: E402
from lecturelens_agent.study.runtime import StudyRuntime  # noqa: E402
from lecturelens_agent.study.store import StudyStore  # noqa: E402
from lecturelens_agent.study.trace import RunTrace  # noqa: E402
from lecturelens_agent.study.trace_cli import JavaGateway  # noqa: E402

BASE = "http://127.0.0.1:8084"
PRIVATE = ROOT / ".data/multi-user-phase-e"
GOAL = "请解释课程中字符串不可变与变量重新绑定的区别，并给两道概念自测题。"


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def store():
    return StudyStore(os.environ["AGENT_DATABASE_URL"])


def api(user, method, path, body=None):
    with httpx.Client(timeout=45, trust_env=False) as client:
        return client.request(
            method,
            BASE + path,
            json=body,
            headers={"Authorization": "Bearer " + user["token"]} if user else {},
        )


def command(user, body, course=None):
    response = api(user, "POST", f"/api/tasks/{course or user['task_id']}/study/command", body)
    response.raise_for_status()
    return response.json()["data"]


def login(i):
    user = json.loads((PRIVATE / "users" / f"user-{i:02}" / "session.local.json").read_text())
    response = api(None, "POST", "/api/auth/login", user["credentials"])
    response.raise_for_status()
    user.update(token=response.json()["data"]["accessToken"], number=i)
    return user


def create(user, session=None):
    session = (
        session
        or command(user, {"operation": "CREATE_SESSION", "request_key": uuid.uuid4().hex})["session_id"]
    )
    body = {
        "operation": "START",
        "session_id": session,
        "request_key": uuid.uuid4().hex,
        "goal": GOAL + f"（本次隔离标签 VU-{user['number']:02}，无需解释标签。）",
    }
    started = time.monotonic()
    response = command(user, body)
    again = command(user, body)
    assert response["run"]["run_id"] == again["run"]["run_id"]
    return {
        "user": user,
        "session_id": session,
        "run_id": response["run"]["run_id"],
        "scope": {k: response[k] for k in ("owner_id", "course_id", "revision")},
        "client_start": started,
    }


def trace_for(item):
    return RunTrace(store(), JavaGateway(BASE, item["user"]["token"]))


class FixedProvider(MockProvider):
    # API freezes the ordinary real-mode configuration; this explicit eval-only
    # adapter replaces responses, never Authority, tools or checkpoint persistence.
    mode = "real"

    def __init__(self, run_id, control=None):
        self.run_id, self.control = run_id, control
        self.held = False

    def identity(self, purpose):
        return {"model": "phase-e-fixed-response", "name": "mechanics-only", "version": 1}

    def barrier(self, timeout):
        if self.control and not self.held:
            self.held = True
            (self.control / (self.run_id + ".entered")).touch()
            deadline = time.monotonic() + min(timeout, 60)
            while not (self.control / "release").exists():
                if time.monotonic() > deadline:
                    raise TimeoutError("Eval barrier expired")
                time.sleep(0.05)
            (self.control / (self.run_id + ".returned")).touch()

    def review(self, messages, timeout):
        if self.control and (self.control / "hold-review").exists():
            self.barrier(timeout)
        return super().review(messages, timeout)

    def decide(self, messages, timeout):
        context = json.loads(messages[-1]["content"])
        if self.control and context["history"] and not (self.control / "hold-review").exists():
            self.barrier(timeout)
        time.sleep(0.1)  # Explicit fixed transport delay, included in all fixed results.
        response = super().decide(messages, timeout)
        if response.get("name") == "create_practice_set":
            response["arguments"]["title"] = context["goal"][-40:]
        return response


class PauseAfterCommitStore(StudyStore):
    """Fault hook AFTER the original transaction commits; never supplies DB results."""

    def __init__(self, dsn, control):
        super().__init__(dsn)
        self.control = control

    def save_tool(self, *args, **kwargs):
        result = super().save_tool(*args, **kwargs)
        if result.get("artifact_id"):
            (self.control / (args[0] + ".entered")).touch()
            deadline = time.monotonic() + 60
            while not (self.control / "release").exists():
                if time.monotonic() > deadline:
                    raise TimeoutError("Post-commit crash barrier expired")
                time.sleep(0.05)
        return result


def execute(item, mode, control=None):
    row = trace_for(item).locate(item["run_id"])
    if row["status"] not in {"queued", "running"}:
        return
    after_commit = control and (control / "after-commit").exists()
    provider = (
        FixedProvider(item["run_id"], None if after_commit else control)
        if mode == "deterministic"
        else RegistryProvider(
            ModelRegistry(os.environ["AGENT_DATABASE_URL"], os.environ["AGENT_SERVICE_SECRET"])
        )
    )
    if mode == "real":
        provider = provider.for_run(row)
        for role, client in provider.clients.items():

            def observe(body, role=role):
                destination = Path(item["capture_dir"]) / (
                    item["run_id"] + "-" + role + "-" + uuid.uuid4().hex + ".response.json"
                )
                destination.write_bytes(body)

            client.response_observer = observe
    runtime = StudyRuntime(
        PauseAfterCommitStore(store().dsn, control) if after_commit else store(),
        EvidenceAuthority(BASE, os.environ["AGENT_SERVICE_SECRET"]),
        provider,
        seconds=90,
    )
    runtime.execute(row)


def percentile(values, fraction):
    """Nearest-rank percentile; small samples do not imply stable tail estimates."""
    return round(sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)], 3) if values else None


def summarize(rows, traces, mode):
    latencies = [r["latency_seconds"] for r in rows if r.get("latency_seconds") is not None]
    searches = [v for t in traces for v in (t["metrics"]["retrieval_latency_ms"] or [])]
    successful = [r["latency_seconds"] for r in rows if r["status"] == "succeeded"]
    model_errors = [
        e["payload"].get("error_code", "")
        for t in traces
        for e in t["events"]
        if e["event_type"] == "model_failed"
    ]
    counts = Counter(r["status"] for r in rows)
    intervals = []
    for trace in traces:
        starts = [e["created_at"] for e in trace["events"] if e["event_type"] == "run_started"]
        if starts and trace["run"]["finished_at"]:
            intervals += [(str(starts[0]), 1), (str(trace["run"]["finished_at"]), -1)]
    active = peak = 0
    for _, change in sorted(intervals):
        active += change
        peak = max(peak, active)
    usage = {}
    for key in ("input_tokens", "output_tokens"):
        missing = sum(t["metrics"][key]["missing_calls"] for t in traces)
        known = sum(t["metrics"][key]["known_total"] for t in traces)
        usage[key] = {"total": known if not missing else None, "known_total": known, "missing_calls": missing}
    return {
        "mode": mode,
        "attempted": len(rows),
        "succeeded": counts["succeeded"],
        "failed": sum(v for k, v in counts.items() if k not in {"succeeded", "cancelled"}),
        "cancelled": counts["cancelled"],
        "recovered": sum(t["metrics"]["resumptions"] > 0 for t in traces),
        "failure_types": dict(
            Counter(r.get("error_code") or r.get("failure_type") for r in rows if r["status"] != "succeeded")
        ),
        "run_p50_seconds": percentile(latencies, 0.5),
        "run_p95_seconds": percentile(latencies, 0.95),
        "successful_run_p50_seconds": percentile(successful, 0.5),
        "successful_run_p95_seconds": percentile(successful, 0.95),
        "provider_rate_limit_events": model_errors.count("MODEL_RATE_LIMITED"),
        "timeout_runs": sum(
            r["error_code"] in {"MODEL_TIMEOUT", "RUN_BUDGET_EXCEEDED", "DEADLINE_EXCEEDED"} for r in rows
        ),
        "infra_failed_runs": sum(r["failure_type"] == "infra" for r in rows),
        "search_p50_ms": percentile(searches, 0.5),
        "search_p95_ms": percentile(searches, 0.95),
        "search_observations": len(searches),
        "peak_running_runs": peak,
        "model_calls": sum(t["metrics"]["model_calls"] for t in traces),
        "tool_calls": sum(t["metrics"]["logical_tool_calls"] for t in traces),
        **usage,
        "billable_model_calls": 0 if mode == "deterministic" else None,
        "rows": rows,
    }


def collect(item, out):
    trace = trace_for(item).read(item["run_id"])
    save(out / (item["run_id"] + ".trace.json"), trace)
    run = trace["run"]
    start, finish = run["created_at"], run["finished_at"]
    latency = (finish - start).total_seconds() if finish else None
    row = {
        "user": item["user"]["number"],
        "run_id": item["run_id"],
        "status": run["status"],
        "error_code": run["error_code"],
        "failure_type": trace["failure_type"],
        "latency_seconds": latency,
        "artifact_ids": [
            t["result"]["artifact_id"] for t in trace["tools"] if t["result"].get("artifact_id")
        ],
    }
    return row, trace


def isolation(items, traces):
    """Ring probes run concurrently; successful reads are independently checked for foreign IDs."""

    def probe(pair):
        i, item = pair
        other = items[(i + 1) % len(items)]
        user = item["user"]
        checks = []

        def record(label, response, expected):
            checks.append(
                {"case": label, "status": response.status_code, "passed": response.status_code in expected}
            )

        foreign = {"session_id": other["session_id"], "run_id": other["run_id"]}
        for op in ("READ", "ANSWERS", "EVENTS", "CANCEL"):
            for label, course, ids in (
                ("foreign_course", other["scope"]["course_id"], foreign),
                ("foreign_session", item["scope"]["course_id"], foreign),
                ("foreign_run", item["scope"]["course_id"], {**foreign, "session_id": item["session_id"]}),
            ):
                record(
                    label + "_" + op,
                    api(user, "POST", f"/api/tasks/{course}/study/command", {"operation": op, **ids}),
                    {403, 404},
                )
        record(
            "foreign_evidence",
            api(user, "GET", f"/api/tasks/{other['scope']['course_id']}/evidence?limit=200"),
            {403, 404},
        )
        canonical = api(user, "GET", f"/api/tasks/{user['task_id']}/evidence?limit=200")
        canonical.raise_for_status()
        ids = {e["evidenceId"] for e in canonical.json()["data"]["items"]}
        trace = traces[i]
        observed = []
        for event in trace["events"]:
            if event["event_type"] == "evidence_finished":
                observed += event["payload"].get("_trace", {}).get("evidence_ids", [])
        artifact = trace["final_answer"] or {}
        cited = [c["evidence_id"] for c in artifact.get("citations", [])]
        from langgraph.checkpoint.postgres import PostgresSaver

        with store().connect() as conn:
            session_runs = {
                r["run_id"]
                for r in conn.execute(
                    "SELECT run_id FROM study_run WHERE session_id=%s", (item["session_id"],)
                ).fetchall()
            }
        checkpoint_runs = []
        checkpoint_evidence = []
        with PostgresSaver.from_conn_string(store().dsn) as saver:
            for saved in saver.list({"configurable": {"thread_id": item["session_id"]}}):
                values = saved.checkpoint["channel_values"]
                checkpoint_runs.append((values.get("__start__") or values).get("run_id"))
                checkpoint_evidence.extend(values.get("selected", []))
        checks.extend(
            [
                {
                    "case": "trace_evidence_scope",
                    "passed": set(observed) <= ids,
                    "observations": len(observed),
                },
                {"case": "artifact_evidence_scope", "passed": set(cited) <= ids, "observations": len(cited)},
                {
                    "case": "checkpoint_run_scope",
                    "passed": bool(checkpoint_runs) and set(checkpoint_runs) <= session_runs,
                    "observations": len(checkpoint_runs),
                },
                {
                    "case": "checkpoint_evidence_scope",
                    "passed": set(checkpoint_evidence) <= ids,
                    "observations": len(checkpoint_evidence),
                },
            ]
        )
        # A failed SEARCH can have no observed IDs. Obtain a real foreign ID
        # using its owner's login; never count an empty READ as an attack probe.
        peer = api(other["user"], "GET", f"/api/tasks/{other['user']['task_id']}/evidence?limit=200")
        peer.raise_for_status()
        foreign_ids = [e["evidenceId"] for e in peer.json()["data"]["items"]]
        assert ids and foreign_ids and not (ids & set(foreign_ids))
        for label, scope in (
            ("wrong_owner", {**item["scope"], "owner_id": other["scope"]["owner_id"]}),
            ("stale_revision", {**item["scope"], "revision": item["scope"]["revision"] - 1}),
        ):
            for action, args in (
                ("CHECK", {}),
                ("SEARCH", {"query": "string"}),
                ("READ", {"evidence_ids": list(ids)[:1]}),
                ("WINDOW", {"evidence_id": sorted(ids)[0]}),
            ):
                payload = {**scope, "action": action, **args}
                body, timestamp = request_body(payload), str(int(time.time()))
                with httpx.Client(timeout=45, trust_env=False) as client:
                    response = client.post(
                        BASE + AUTHORITY_PATH,
                        content=body,
                        headers={
                            "Content-Type": "application/json",
                            "X-LectureLens-Timestamp": timestamp,
                            "X-LectureLens-Signature": signature(
                                os.environ["AGENT_SERVICE_SECRET"], timestamp, body, AUTHORITY_PATH
                            ),
                        },
                    )
                record(label + "_" + action, response, {403, 404, 409})
        authority = EvidenceAuthority(BASE, os.environ["AGENT_SERVICE_SECRET"])
        try:
            result = authority.read(item["scope"], "READ", evidence_ids=foreign_ids[:1])
            checks.append(
                {"case": "foreign_evidence_id", "passed": not result["evidence"], "observations": 1}
            )
        except Exception as error:
            from lecturelens_agent.study.store import StudyError

            if not isinstance(error, StudyError):
                raise
            checks.append(
                {
                    "case": "foreign_evidence_id",
                    "passed": error.code == "COURSE_UNAVAILABLE_OR_CHANGED",
                    "observations": 1,
                }
            )
        record(
            "unsigned_java_authority",
            api(None, "POST", AUTHORITY_PATH, {**item["scope"], "action": "SEARCH", "query": "string"}),
            {401, 403},
        )
        with httpx.Client(timeout=45, trust_env=False) as client:
            response = client.post(
                "http://127.0.0.1:8094/internal/v1/study/command",
                json={**item["scope"], "operation": "READ", **foreign},
            )
        record("unsigned_agent_command", response, {401, 403})
        return checks

    with ThreadPoolExecutor(max_workers=5) as pool:
        checks = [c for group in pool.map(probe, enumerate(items)) for c in group]
    grouped = {}
    for case in sorted({c["case"] for c in checks}):
        group = [c for c in checks if c["case"] == case]
        grouped[case] = {
            "attempted": len(group),
            "violations": sum(not c["passed"] for c in group),
            "observations": sum(c.get("observations", 0) for c in group),
        }
    return {"checks": checks, "by_case": grouped, "violations": sum(not c["passed"] for c in checks)}


def cohort(args, out):
    barrier = threading.Barrier(args.users)

    def start(i):
        barrier.wait(timeout=30)
        return create(login(i))

    with ThreadPoolExecutor(max_workers=args.users) as pool:
        items = list(pool.map(start, range(args.users)))
    for item in items:
        item["capture_dir"] = str(out)
    save(out / "manifest.local.json", items)
    # Same unchanged execute() used by the production dequeue loop. The only
    # scheduling change is an explicitly bounded, eval-only dispatch pool.
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(lambda item: execute(item, args.mode), items))
    collected = [collect(item, out) for item in items]
    rows, traces = map(list, zip(*collected, strict=True))
    result = summarize(rows, traces, args.mode)
    result.update(users=args.users, workers=args.workers, isolation=isolation(items, traces))
    save(out / "result.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in {"rows", "isolation"}}), flush=True)


def wait_entered(items, folder):
    deadline = time.monotonic() + 45
    while not all((folder / (item["run_id"] + ".entered")).exists() for item in items):
        if time.monotonic() > deadline:
            raise TimeoutError("Workers did not reach the post-SEARCH model barrier")
        time.sleep(0.1)


def spawn(folder, index, hold=False):
    log = (folder / f"worker-{index}-{uuid.uuid4().hex[:8]}.log").open("w")
    try:
        return subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "worker",
                "--label",
                folder.name,
                "--item",
                str(index),
                *(["--hold"] if hold else []),
            ],
            stdout=log,
            stderr=log,
        )
    finally:
        log.close()


def effects(item):
    # Read-only audit: there is no harness SQL mutation path.
    with store().connect() as conn:
        return {
            "artifact_content_hashes": [
                hashlib.sha256(json.dumps(r["content"], sort_keys=True).encode()).hexdigest()
                for r in conn.execute(
                    "SELECT content FROM study_artifact WHERE run_id=%s", (item["run_id"],)
                ).fetchall()
            ],
            "artifact_events": conn.execute(
                "SELECT count(*) AS n FROM study_event WHERE run_id=%s AND event_type='artifact_created'",
                (item["run_id"],),
            ).fetchone()["n"],
            "artifacts": conn.execute(
                "SELECT count(*) AS n FROM study_artifact WHERE run_id=%s", (item["run_id"],)
            ).fetchone()["n"],
            "tools": conn.execute(
                "SELECT call_id,tool_name FROM study_tool_result WHERE run_id=%s ORDER BY call_id",
                (item["run_id"],),
            ).fetchall(),
            "finished_events": conn.execute(
                "SELECT count(*) AS n FROM study_event WHERE run_id=%s AND event_type='run_finished'",
                (item["run_id"],),
            ).fetchone()["n"],
        }


def artifact_recovery(args, out):
    (out / "after-commit").touch()
    items = [create(login(i)) for i in range(5)]
    save(out / "manifest.local.json", items)
    processes = []
    try:
        for i in range(5):
            processes.append(spawn(out, i, True))
            wait_entered([items[i]], out)
        before = [effects(item) for item in items]
        traces_before = [trace_for(item).read(item["run_id"]) for item in items]
        for item, trace in zip(items, traces_before, strict=True):
            save(out / (item["run_id"] + ".before.trace.json"), trace)
        save(out / "before-effects.json", before)
        assert all(e["artifacts"] == e["artifact_events"] == 1 and e["finished_events"] == 0 for e in before)
        for process in processes:
            process.kill()
        for process in processes:
            assert process.wait(timeout=10) == -9
        processes = [spawn(out, i) for i in range(5) for _ in range(2)]
        for process in processes:
            assert process.wait(timeout=60) == 0
        collected = [collect(item, out) for item in items]
        rows, traces = map(list, zip(*collected, strict=True))
        result = summarize(rows, traces, "deterministic")
        result["checks"] = []
        for item, prior, previous, trace in zip(items, before, traces_before, traces, strict=True):
            after = effects(item)
            result["checks"].append(
                {
                    "run_id": item["run_id"],
                    "artifacts": after["artifacts"],
                    "artifact_events": after["artifact_events"],
                    "finished_events": after["finished_events"],
                    "artifact_content_unchanged": prior["artifact_content_hashes"]
                    == after["artifact_content_hashes"],
                    "tool_results_unchanged": prior["tools"] == after["tools"],
                    "model_calls_unchanged": previous["run"]["model_calls"] == trace["run"]["model_calls"],
                    "tool_calls_unchanged": previous["run"]["tool_calls"] == trace["run"]["tool_calls"],
                    "deadline_unchanged": previous["run"]["deadline"] == trace["run"]["deadline"],
                    "resumptions": trace["metrics"]["resumptions"],
                }
            )
        result["isolation"] = isolation(items, traces)
        save(out / "result.json", result)
        print(
            json.dumps(
                {
                    "succeeded": result["succeeded"],
                    "recovered": result["recovered"],
                    "checks": result["checks"],
                }
            ),
            flush=True,
        )
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)


def faults(args, out):
    results = {}
    processes = []
    try:
        if args.action == "late-result":
            (out / "hold-review").touch()
        # Five independently owned Sessions, all held after a real SEARCH has
        # been committed, with the next model decision in flight.
        with ThreadPoolExecutor(max_workers=5) as pool:
            items = list(pool.map(lambda i: create(login(i)), range(5)))
        save(out / "manifest.local.json", items)
        processes = []
        for i in range(5):
            processes.append(spawn(out, i, True))
            wait_entered([items[i]], out)
        wait_entered(items, out)
        active_traces = [trace_for(item).read(item["run_id"]) for item in items]
        for item, trace in zip(items, active_traces, strict=True):
            save(out / (item["run_id"] + ".active.trace.json"), trace)
        results["active_run_isolation"] = isolation(items, active_traces)
        before = [effects(item) for item in items]
        for item in items:
            command(
                item["user"],
                {"operation": "CANCEL", "session_id": item["session_id"], "run_id": item["run_id"]},
            )
        cancelled = [trace_for(item).read(item["run_id"]) for item in items]
        for item, trace in zip(items, cancelled, strict=True):
            save(out / (item["run_id"] + ".cancelled.trace.json"), trace)
        with ThreadPoolExecutor(max_workers=5) as pool:
            replacements = list(pool.map(lambda item: create(item["user"], item["session_id"]), items))
        # The old workers still own their Session advisory locks. Competitors
        # must leave replacements queued until the late response returns.
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(lambda item: execute(item, "deterministic"), replacements))
        assert all(trace_for(item).locate(item["run_id"])["status"] == "queued" for item in replacements)
        (out / "release").touch()
        for process in processes:
            assert process.wait(timeout=45) == 0
        late = [trace_for(item).read(item["run_id"]) for item in items]
        unchanged = []
        pending_changes = []
        for item, a, b in zip(items, cancelled, late, strict=True):
            added, removed = [], []
            for before_checkpoint, after_checkpoint in zip(a["checkpoints"], b["checkpoints"], strict=True):
                added.extend(
                    w
                    for w in after_checkpoint["pending_writes"]
                    if w not in before_checkpoint["pending_writes"]
                )
                removed.extend(
                    w
                    for w in before_checkpoint["pending_writes"]
                    if w not in after_checkpoint["pending_writes"]
                )
            pending_changes.append(
                {
                    "run_id": item["run_id"],
                    "added_channels": [w[1] for w in added],
                    "removed_channels": [w[1] for w in removed],
                    "error_values": [str(w[2]) for w in added if w[1] == "__error__"],
                }
            )
            unchanged.append(
                {
                    "run_id": item["run_id"],
                    "late_response_returned": (out / (item["run_id"] + ".returned")).exists(),
                    "events_unchanged": a["events"] == b["events"],
                    "checkpoints_unchanged": a["checkpoints"] == b["checkpoints"],
                    "checkpoint_states_unchanged": [
                        {k: v for k, v in c.items() if k != "pending_writes"} for c in a["checkpoints"]
                    ]
                    == [{k: v for k, v in c.items() if k != "pending_writes"} for c in b["checkpoints"]],
                    "pending_write_channels_after": sorted(
                        {w[1] for c in b["checkpoints"] for w in c["pending_writes"]}
                    ),
                    "status": b["run"]["status"],
                    "artifacts": effects(item)["artifacts"],
                }
            )
        save(out / "pending-write-audit.json", pending_changes)
        with ThreadPoolExecutor(max_workers=1 if args.action == "late-result" else 5) as pool:
            list(pool.map(lambda item: execute(item, "deterministic"), replacements))
        save(out / "replacements.local.json", replacements)
        original_results = [collect(item, out) for item in items]
        replacement_results = [collect(item, out) for item in replacements]
        results["cancel"] = {
            "attempted": 5,
            "cancelled": sum(t[0]["status"] == "cancelled" for t in original_results),
            "late_result_checks": unchanged,
            "replacement_succeeded": sum(t[0]["status"] == "succeeded" for t in replacement_results),
            "before_effects": before,
            "replacement_isolation": isolation(replacements, [t[1] for t in replacement_results]),
        }
        save(out / "cancel-result.json", results)
        if args.action == "late-result":
            save(out / "result.json", results)
            print(
                json.dumps(
                    {
                        "cancelled": results["cancel"]["cancelled"],
                        "replacement_succeeded": results["cancel"]["replacement_succeeded"],
                        "late_result_checks": unchanged,
                    }
                ),
                flush=True,
            )
            return

        # A separate cohort tests abrupt process loss and competing restart.
        restart = PRIVATE / (args.label + "-restart")
        restart.mkdir(exist_ok=False)
        with ThreadPoolExecutor(max_workers=5) as pool:
            items = list(pool.map(lambda i: create(login(i)), range(5)))
        save(restart / "manifest.local.json", items)
        processes = []
        for i in range(5):
            processes.append(spawn(restart, i, True))
            wait_entered([items[i]], restart)
        wait_entered(items, restart)
        before = [effects(item) for item in items]
        checkpoints = [trace_for(item).read(item["run_id"]) for item in items]
        for item, trace in zip(items, checkpoints, strict=True):
            save(restart / (item["run_id"] + ".before.trace.json"), trace)
        for process in processes:
            process.kill()
        for process in processes:
            assert process.wait(timeout=10) == -9
        # Two processes contend for each original Run. Existing session locks,
        # claim fencing, budgets, checkpoints and idempotency remain unchanged.
        processes = [spawn(restart, i) for i in range(5) for _ in range(2)]
        for process in processes:
            assert process.wait(timeout=60) == 0
        collected = [collect(item, restart) for item in items]
        rows, traces = map(list, zip(*collected, strict=True))
        recovery = summarize(rows, traces, "deterministic")
        recovery["checks"] = []
        for item, prior, checkpoint, trace in zip(items, before, checkpoints, traces, strict=True):
            after = effects(item)
            recovery["checks"].append(
                {
                    "run_id": item["run_id"],
                    "artifacts": after["artifacts"],
                    "finished_events": after["finished_events"],
                    "resumptions": trace["metrics"]["resumptions"],
                    "original_tools_retained": all(t in after["tools"] for t in prior["tools"]),
                    "search_executions": trace["metrics"]["retrieval_calls"],
                    "deadline_unchanged": checkpoint["run"]["deadline"] == trace["run"]["deadline"],
                    "checkpoint_history_retained": {c["checkpoint_id"] for c in checkpoint["checkpoints"]}
                    <= {c["checkpoint_id"] for c in trace["checkpoints"]},
                }
            )
        recovery["isolation"] = isolation(items, traces)
        results["recovery"] = recovery
        save(out / "result.json", results)
        print(
            json.dumps(
                {
                    "cancelled": results["cancel"]["cancelled"],
                    "replacement_succeeded": results["cancel"]["replacement_succeeded"],
                    "recovered": recovery["recovered"],
                    "recovery_succeeded": recovery["succeeded"],
                }
            ),
            flush=True,
        )
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["cohort", "worker", "faults", "late-result", "artifact-recovery"])
    parser.add_argument("--mode", choices=["deterministic", "real"], default="deterministic")
    parser.add_argument("--users", type=int, default=5)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--label", required=True)
    parser.add_argument("--item", type=int, default=0)
    parser.add_argument("--hold", action="store_true")
    args = parser.parse_args()
    configure()
    os.umask(0o077)
    if Path(args.label).name != args.label:
        parser.error("label must be a single new directory name")
    out = PRIVATE / args.label
    if args.action == "worker":
        items = json.loads((out / "manifest.local.json").read_text())
        execute(items[args.item], args.mode, out if args.hold else None)
        return
    out.mkdir(exist_ok=False)
    snapshot = out / "harness-source"
    snapshot.mkdir()
    for path in Path(__file__).parent.glob("*.py"):
        (snapshot / path.name).write_bytes(path.read_bytes())
    save(
        out / "identity.json",
        {
            "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "arguments": vars(args),
            "created_at": datetime.now().isoformat(),
            "source_sha256": {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for folder in (ROOT / "agent-service/src", Path(__file__).parent)
                for p in sorted(folder.rglob("*.py"))
            },
        },
    )
    if args.action == "cohort":
        cohort(args, out)
    elif args.action == "artifact-recovery":
        artifact_recovery(args, out)
    else:
        faults(args, out)


if __name__ == "__main__":
    main()
