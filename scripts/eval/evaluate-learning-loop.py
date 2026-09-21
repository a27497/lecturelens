#!/usr/bin/env python3
"""Run frozen fresh goals through the authenticated real gateway, preserving every trial.

This records execution, not semantic acceptance. Review private answers and canonical
citations separately. Credentials and raw results must remain in an ignored directory.
"""

import argparse
import hashlib
import json
import secrets
import time
import urllib.request
from pathlib import Path


def source_digest(root):
    digest = hashlib.sha256()
    for path in sorted((root / "lecturelens_agent").rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def save_record(path, record):
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auth", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=["development", "holdout"], required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    freeze = json.loads(args.freeze.read_text())
    assert source_digest(root / "agent-service/src") == freeze["source_sha256"]
    assert hashlib.sha256(args.cases.read_bytes()).hexdigest() == freeze["tasks_sha256"]
    auth = json.loads(args.auth.read_text())
    base = auth["base_url"].rstrip("/")
    args.output.mkdir(parents=True, exist_ok=True)
    token = ""

    def api(path, body=None):
        request = urllib.request.Request(
            base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Content-Type": "application/json",
                **({"Authorization": "Bearer " + token} if token else {}),
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)["data"]

    token = api("/api/auth/login", auth["credentials"])["accessToken"]
    endpoint = f"/api/tasks/{auth['task_id']}/study/command"
    assert (
        api(f"/api/tasks/{auth['task_id']}/evidence/index-status")["status"] == "READY"
    )
    cases = [
        case
        for case in json.loads(args.cases.read_text())["cases"]
        if case["split"] == args.split
    ]
    for case in cases:
        path = args.output / (case["id"] + ".json")
        if path.exists():
            raise RuntimeError(
                "Trial exists; use a new output directory for an explicitly recorded retry"
            )
        # Reserve the record before any model run, including failed transport/start trials.
        record = {
            "case_id": case["id"],
            "source_sha256": freeze["source_sha256"],
            "expected": case["expected"],
            "semantic_review": "pending",
            "started_at": time.time(),
        }
        save_record(path, record)
        try:
            session = api(
                endpoint,
                {"operation": "CREATE_SESSION", "request_key": secrets.token_hex(16)},
            )["session_id"]
            command = {
                "operation": "START",
                "session_id": session,
                "request_key": secrets.token_hex(16),
                "goal": case["goal"],
            }
            record["start_command"] = command
            save_record(path, record)
            result = api(endpoint, command)
            scope = {"session_id": session, "run_id": result["run"]["run_id"]}
            record["run_id"] = scope["run_id"]
            save_record(path, record)
            deadline = time.monotonic() + 150
            while (
                result["run"]["status"] in ["queued", "running"]
                and time.monotonic() < deadline
            ):
                time.sleep(1)
                result = api(endpoint, {"operation": "READ", **scope})
            record.update(result)
            record["events"] = api(
                endpoint, {"operation": "EVENTS", **scope, "after": 0}
            )["events"]
            artifact = result.get("artifact")
            if artifact and artifact["kind"] == "practice":
                assert all(
                    "answer" not in q and "rubric" not in q
                    for q in artifact["questions"]
                )
                record["answers"] = api(endpoint, {"operation": "ANSWERS", **scope})[
                    "questions"
                ]
            record["expected_type"] = bool(
                artifact and artifact["kind"] == case["expected"]
            )
            record["finished_at"] = time.time()
            save_record(path, record)
            print(
                case["id"],
                result["run"]["status"],
                result["run"].get("error_code"),
                "expected_type=" + str(record["expected_type"]),
                flush=True,
            )
        except Exception as error:
            record["harness_error_type"] = type(error).__name__
            save_record(path, record)
            raise


if __name__ == "__main__":
    main()
