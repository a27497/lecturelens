"""Real Java + MCP + real-model acceptance in an isolated stack, preserving every Run.

Use a stack with its automatic Study worker paused: this driver executes only the
two new Runs it creates through the authenticated Java gateway. No business writes
or deleted-state fixture mutations are made by this driver.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import pathlib
import sys
import time

from mcp import StdioServerParameters

from lecturelens_agent.course_mcp.client import McpEvidenceAuthority
from lecturelens_agent.study.authority import EvidenceAuthority
from lecturelens_agent.study.models import ModelRegistry, RegistryProvider
from lecturelens_agent.study.replay import start_replay
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyError, StudyStore
from lecturelens_agent.study.trace import RunTrace
from lecturelens_agent.study.trace_cli import JavaGateway


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--request-key", required=True)
    parser.add_argument("--deleted-course-id", required=True)
    parser.add_argument("--deleted-owner-id", type=int, required=True)
    parser.add_argument("--deleted-revision", type=int, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    root = pathlib.Path(__file__).resolve().parents[2]
    (args.output / "identity.json").write_text(
        json.dumps(
            {
                "mcp_sdk": importlib.metadata.version("mcp"),
                "source_sha256": {
                    str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted((root / "agent-service/src/lecturelens_agent").rglob("*.py"))
                },
                "lock_sha256": hashlib.sha256((root / "agent-service/uv.lock").read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )
    store = StudyStore(os.environ["AGENT_DATABASE_URL"])
    gateway = JavaGateway(args.base_url, os.environ["LECTURELENS_AUTH_TOKEN"])
    trace = RunTrace(store, gateway)
    source = trace.locate(args.source_run_id)
    trace.authorize(source)
    secret, java_url = os.environ["AGENT_SERVICE_SECRET"], os.environ["AGENT_JAVA_BASE_URL"]
    direct = EvidenceAuthority(java_url, secret)
    calls = []

    def observe(event):
        calls.append(event)
        with (args.output / "mcp-calls.jsonl").open("a") as output:
            output.write(json.dumps(event, ensure_ascii=False) + "\n")

    client = McpEvidenceAuthority(java_url, secret, observer=observe)
    parity = []
    denials = []
    try:
        search = client.read(source, "SEARCH", query="字符串不可变性与变量重新绑定")
        ids = [e["evidence_id"] for e in search["evidence"]]
        assert ids
        for action, arguments in [
            ("CHECK", {}),
            ("SEARCH", {"query": "字符串不可变性与变量重新绑定"}),
            ("SEARCH", {"query": "string rebinding", "start_ms": 30000, "end_ms": 90000}),
            ("READ", {"evidence_ids": ids[:2]}),
            ("READ", {"evidence_ids": []}),
            ("WINDOW", {"evidence_id": ids[0]}),
        ]:
            started = time.monotonic()
            expected = direct.read(source, action, **arguments)
            direct_ms = (time.monotonic() - started) * 1000
            actual = client.read(source, action, **arguments)
            row = {
                "action": action,
                "arguments": arguments,
                "equal": actual == expected,
                "result_sha256": hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest(),
                "evidence_ids": [e["evidence_id"] for e in actual["evidence"]],
                "direct_ms": round(direct_ms, 3),
                "mcp_ms": calls[-1]["duration_ms"],
            }
            parity.append(row)
            assert row["equal"]
        for label, scope in [
            ("wrong_owner", {**source, "owner_id": source["owner_id"] + 1}),
            ("old_revision", {**source, "revision": source["revision"] - 1}),
            (
                "deleted_course",
                {
                    "course_id": args.deleted_course_id,
                    "owner_id": args.deleted_owner_id,
                    "revision": args.deleted_revision,
                },
            ),
        ]:
            errors = []
            for authority in (direct, client):
                try:
                    authority.read(scope, "SEARCH", query="string")
                except StudyError as error:
                    errors.append({"code": error.code, "status": error.status})
                else:
                    raise AssertionError(f"Java failed to reject {label}")
            denials.append(
                {"case": label, "internal": errors[0], "mcp": errors[1], "equal": errors[0] == errors[1]}
            )
        (args.output / "parity.json").write_text(json.dumps(parity, ensure_ascii=False, indent=2))
        (args.output / "denials.json").write_text(json.dumps(denials, indent=2))

        registry = ModelRegistry(store.dsn, secret)
        results = []
        for label in ("normal", "malformed"):
            created = start_replay(trace, args.source_run_id, args.request_key + "-" + label)
            run = trace.locate(created["run"]["run_id"])
            assert run["status"] == "queued", "Use an isolated stack with automatic worker paused"
            (args.output / f"{label}-start.json").write_text(json.dumps(created, default=str, indent=2))
            authority = (
                client
                if label == "normal"
                else McpEvidenceAuthority(
                    java_url,
                    secret,
                    parameters=StdioServerParameters(
                        command=sys.executable,
                        args=[str(pathlib.Path(__file__).with_name("fault_server.py").resolve())],
                        env={"AGENT_JAVA_BASE_URL": java_url},
                    ),
                    observer=observe,
                )
            )
            try:
                StudyRuntime(store, authority, RegistryProvider(registry), seconds=90).execute(run)
                result = trace.read(run["run_id"])
                (args.output / f"{label}.trace.json").write_text(
                    json.dumps(result, ensure_ascii=False, default=str, indent=2)
                )
                results.append(
                    {
                        "case": label,
                        "run_id": run["run_id"],
                        "status": result["run"]["status"],
                        "error_code": result["run"]["error_code"],
                        "metrics": result["metrics"],
                    }
                )
            finally:
                if label != "normal":
                    authority.close()
        report = {
            "parity": parity,
            "denials": denials,
            "runs": results,
            "protocol": next(e for e in calls if e["event"] == "initialize"),
            "mcp_calls": sum(e["event"] == "tools/call" for e in calls),
        }
        (args.output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False))
        assert all(row["equal"] for row in parity + denials)
        assert results[0]["status"] == "succeeded"
        assert results[1]["error_code"] == "MCP_MALFORMED_RESPONSE"
    finally:
        client.close()


if __name__ == "__main__":
    main()
