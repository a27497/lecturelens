"""Execute a recorded multi-turn development trial through the isolated gateway.

Every turn is reserved before START. A failed turn stops its conversation; no
trial is overwritten. Semantic acceptance is a separate source review.
"""

import argparse
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")
    path.chmod(0o600)


def source_digest(source):
    digest = hashlib.sha256()
    for path in sorted((source / "lecturelens_agent").rglob("*.py")):
        digest.update(str(path.relative_to(source)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def validate_origin(base):
    if base != "http://127.0.0.1:8084":
        raise ValueError("Use the isolated localhost gateway on port 8084")


class Gateway:
    def __init__(self, base):
        validate_origin(base)
        self.base = base
        self.token = ""

    def api(self, method, path, body=None):
        request = Request(
            self.base + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Content-Type": "application/json",
                **({"Authorization": "Bearer " + self.token} if self.token else {}),
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                result = json.load(response)
        except HTTPError as error:
            raise RuntimeError("GATEWAY_HTTP_" + str(error.code)) from None
        return result["data"]


def evidence_snapshot(gateway, course):
    result, after, revision = [], None, None
    while True:
        query = {"limit": 200}
        if after is not None:
            query.update(after=after, revision=revision)
        page = gateway.api("GET", f"/api/tasks/{course}/evidence?" + urlencode(query))
        if page["stale"] or revision is not None and page["revision"] != revision:
            raise RuntimeError("EVIDENCE_REVISION_CHANGED")
        revision = page["revision"]
        result.extend(page["items"])
        if len(result) > 2000:
            raise RuntimeError("EVIDENCE_MANIFEST_LIMIT")
        after = page["nextCursor"]
        if after is None:
            return {"revision": revision, "items": result}


def execute(gateway, auth, cases, freeze, runtime, output):
    # Exclusive reservation precedes login, session creation and every START.
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    save(
        output / "trial.json",
        {"freeze": freeze, "status": "started", "semantic_review": "pending"},
    )
    gateway.token = gateway.api("POST", "/api/auth/login", auth["credentials"])[
        "accessToken"
    ]
    course = auth["task_id"]
    endpoint = f"/api/tasks/{course}/study/command"
    index = gateway.api("GET", f"/api/tasks/{course}/evidence/index-status")
    if index["status"] != "READY":
        raise RuntimeError("INDEX_NOT_READY")
    canonical = evidence_snapshot(gateway, course)
    save(output / "evidence.private.json", canonical)
    results = []
    for case in cases:
        prefix = case["id"]
        if not prefix.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Unsafe case ID")
        if case.get("resume"):
            prior = gateway.api(
                "POST", endpoint, {"operation": "READ", **case["resume"]["scope"]}
            )
            if (
                prior["run"]["status"] != "succeeded"
                or prior["artifact"] != case["resume"]["artifact"]
            ):
                raise RuntimeError("FROZEN_PREVIOUS_TURN_CHANGED")
            session = case["resume"]["scope"]["session_id"]
            save(output / (prefix + "-prior.private.json"), prior)
        else:
            session = gateway.api(
                "POST",
                endpoint,
                {"operation": "CREATE_SESSION", "request_key": uuid.uuid4().hex},
            )["session_id"]
        for number, turn in enumerate(case["turns"], 1):
            record_path = output / f"{prefix}-turn-{number}.private.json"
            command = {
                "operation": "START",
                "session_id": session,
                "request_key": uuid.uuid4().hex,
                "goal": turn["goal"],
            }
            record = {
                "case_id": prefix,
                "turn": number,
                "command": command,
                "expected": turn["expected"],
                "source_sha256": freeze["source_sha256"],
                "semantic_review": "pending",
                "started_at": time.time(),
            }
            save(record_path, record)
            try:
                response = gateway.api("POST", endpoint, command)
                scope = {"session_id": session, "run_id": response["run"]["run_id"]}
                record["scope"] = scope
                save(record_path, record)
                deadline = time.monotonic() + 150
                while response["run"]["status"] in {"queued", "running"}:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("OBSERVATION_TIMEOUT")
                    time.sleep(1)
                    response = gateway.api(
                        "POST", endpoint, {"operation": "READ", **scope}
                    )
                record.update(response)
                record["events"] = gateway.api(
                    "POST", endpoint, {"operation": "EVENTS", **scope, "after": 0}
                )["events"]
                if (response.get("artifact") or {}).get("kind") == "practice":
                    record["answers"] = gateway.api(
                        "POST", endpoint, {"operation": "ANSWERS", **scope}
                    )
                with psycopg.connect(
                    runtime["AGENT_DATABASE_URL"],
                    row_factory=dict_row,
                    options="-c default_transaction_read_only=on",
                ) as conn:
                    record["private_tools"] = conn.execute(
                        "SELECT * FROM study_tool_result WHERE run_id=%s ORDER BY call_id",
                        (scope["run_id"],),
                    ).fetchall()
                    record["private_events"] = conn.execute(
                        "SELECT * FROM study_event WHERE run_id=%s ORDER BY sequence",
                        (scope["run_id"],),
                    ).fetchall()
                record["finished_at"] = time.time()
                save(record_path, record)
                summary = {
                    "case_id": prefix,
                    "turn": number,
                    "run_id": scope["run_id"],
                    "status": response["run"]["status"],
                    "error_code": response["run"].get("error_code"),
                    "kind": (response.get("artifact") or {}).get("kind"),
                    "model_calls": response["run"]["model_calls"],
                    "tool_calls": response["run"]["tool_calls"],
                }
                results.append(summary)
                save(output / "execution-summary.json", results)
                print(json.dumps(summary), flush=True)
                if response["run"]["status"] != "succeeded":
                    return False
            except Exception as error:
                record["harness_error_type"] = type(error).__name__
                save(record_path, record)
                raise
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["auth", "cases", "freeze", "runtime", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    for path in [args.auth, args.runtime, args.output]:
        if not path.resolve().is_relative_to(ROOT / ".data"):
            parser.error("Credentials, runtime and output must stay in ignored .data")
    auth, runtime, freeze = (
        json.loads(p.read_text()) for p in [args.auth, args.runtime, args.freeze]
    )
    if (
        runtime["APP_PORT"] != "8084"
        or "lecturelens_learning_loop" not in runtime["MYSQL_JDBC_URL"]
    ):
        parser.error("Use the isolated learning-loop runtime")
    if (
        runtime["AGENT_LLM_MODE"] != "real"
        or runtime["AGENT_RUN_DEADLINE_SECONDS"] != "90"
    ):
        parser.error("Use the frozen real model and original deadline")
    if source_digest(Path(runtime["PYTHONPATH"])) != freeze["source_sha256"]:
        parser.error("Frozen source changed")
    if hashlib.sha256(args.cases.read_bytes()).hexdigest() != freeze["tasks_sha256"]:
        parser.error("Frozen tasks changed")
    cases = json.loads(args.cases.read_text())["cases"]
    passed = execute(
        Gateway(auth["base_url"]), auth, cases, freeze, runtime, args.output
    )
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
