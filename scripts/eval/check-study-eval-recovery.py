#!/usr/bin/env python3
"""Verify saved evaluation artifacts across an isolated Agent restart, or exercise cancellation."""

import argparse
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--phase", choices=["capture", "verify", "cancel"], required=True)
    parser.add_argument("--report-prefix", required=True)
    args = parser.parse_args()
    assert args.report_prefix.replace("-", "").replace("_", "").isalnum()
    base = args.base_url.rstrip("/")
    cases = {case["id"]: case for case in json.loads(args.cases.read_text())["cases"]}
    rows = [json.loads(line) for line in args.results.read_text().splitlines()]
    tokens = {}

    def api(clip, path, body, expected=200):
        auth = json.loads((args.output / "courses" / clip / "session.local.json").read_text())
        assert auth.get("base_url") == base, "Course belongs to another API endpoint"
        if clip not in tokens and path != "/api/auth/login":
            tokens[clip] = api(clip, "/api/auth/login", auth["credentials"])["accessToken"]
        request = urllib.request.Request(
            base + path,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": "Bearer " + tokens[clip]} if clip in tokens else {}),
            },
        )
        try:
            response = urllib.request.urlopen(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            assert response.status == expected, (path, response.status)
            return json.loads(response.read()).get("data")

    saved = []
    selected = [row for row in rows if row["run"]["status"] == "succeeded"]
    assert selected
    for row in selected:
        clip = cases[row["case_id"]]["clip_id"]
        auth = json.loads((args.output / "courses" / clip / "session.local.json").read_text())
        endpoint = f"/api/tasks/{auth['task_id']}/study/command"
        scope = {"session_id": row["run"]["session_id"], "run_id": row["run"]["run_id"]}
        result = api(clip, endpoint, {"operation": "READ", **scope})
        assert result["artifact"] == row["artifact"]
        assert result["run"]["status"] == "succeeded"
        assert result["run"]["model_calls"] == row["run"]["model_calls"]
        assert all("answer" not in q and "rubric" not in q for q in result["artifact"]["questions"])
        if row["artifact"]["kind"] == "practice":
            answers = api(clip, endpoint, {"operation": "ANSWERS", **scope})["questions"]
            assert answers == row["answers"]
        events = api(clip, endpoint, {"operation": "EVENTS", **scope, "after": 0})["events"]
        cursor = events[-1]["sequence"] if events else 0
        assert api(clip, endpoint, {"operation": "EVENTS", **scope, "after": cursor})["events"] == []
        if args.phase == "verify":
            replay = api(
                clip,
                endpoint,
                {
                    "operation": "START",
                    "session_id": scope["session_id"],
                    "request_key": row["run"]["request_key"],
                    "goal": row["run"]["goal"],
                },
            )
            assert replay["run"]["run_id"] == scope["run_id"]
            assert replay["run"]["model_calls"] == row["run"]["model_calls"]
        saved.append(
            {
                "case_id": row["case_id"],
                "artifact_digest": hashlib.sha256(
                    json.dumps(result["artifact"], sort_keys=True).encode()
                ).hexdigest(),
                "model_calls": result["run"]["model_calls"],
                "last_event_sequence": cursor,
            }
        )
    path = args.output / f"{args.report_prefix}-restart-capture.json"
    if args.phase == "capture":
        assert not path.exists(), "Do not overwrite the pre-restart snapshot"
        path.write_text(json.dumps(saved, indent=2) + "\n")
        path.chmod(0o600)
    elif args.phase == "verify":
        assert saved == json.loads(path.read_text()), "Persistence changed across restart"
    else:
        session = api(
            clip,
            endpoint,
            {"operation": "CREATE_SESSION", "request_key": "cancel-check:" + secrets.token_hex(10)},
        )["session_id"]
        command = {
            "operation": "START",
            "session_id": session,
            "request_key": secrets.token_hex(10),
            "goal": row["run"]["goal"],
        }
        run = api(clip, endpoint, command)["run"]
        assert api(clip, endpoint, command)["run"]["run_id"] == run["run_id"]
        scope = {"session_id": session, "run_id": run["run_id"]}
        api(clip, endpoint, {"operation": "CANCEL", **scope})
        deadline = time.monotonic() + 45
        while True:
            canceled = api(clip, endpoint, {"operation": "READ", **scope})
            if canceled["run"]["status"] not in ("queued", "running"):
                break
            assert time.monotonic() < deadline
            time.sleep(0.3)
        assert canceled["run"]["status"] == "cancelled" and not canceled.get("artifact")
        private = args.output / f"{args.report_prefix}-cancel-run.json"
        private.write_text(json.dumps(canceled, indent=2) + "\n")
        private.chmod(0o600)
    report = {
        "phase": args.phase,
        "successful_artifacts_checked": len(saved),
        "hidden_answers": True,
        "event_tail_empty": True,
        "semantic_quality_evaluated_here": False,
    }
    (args.output / f"{args.report_prefix}-{args.phase}-report.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
