#!/usr/bin/env python3
"""Run a frozen Study evaluation through real Java APIs. Resume without replacing failed trials."""

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".data/l22-eval"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--split", choices=["dev", "holdout", "all"], default="all")
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum additional trials for a development diagnostic; partial cohorts cannot pass",
    )
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--cases", type=Path, default=ROOT / "eval/study-v1/cases.json")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    output = args.output
    base = args.base_url.rstrip("/")
    assert args.label.replace("-", "").replace("_", "").isalnum()
    assert args.limit is None or args.limit > 0
    dataset_path = args.cases
    cases = json.loads(dataset_path.read_text())["cases"]
    env = json.loads((output / "runtime.local.json").read_text())
    destination = output / f"{args.label}.jsonl"
    old = [json.loads(line) for line in destination.read_text().splitlines()] if destination.exists() else []
    digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    assert all(row["dataset_sha256"] == digest for row in old), "Dataset changed; use a new evaluation label"
    source_root = Path(env.get("PYTHONPATH") or ROOT / "agent-service/src")
    source_digest = hashlib.sha256()
    for path in sorted((source_root / "lecturelens_agent").rglob("*.py")):
        source_digest.update(str(path.relative_to(source_root)).encode())
        source_digest.update(path.read_bytes())
    runtime = {
        "source_sha256": source_digest.hexdigest(),
        "model": env.get("EVAL_MODELS", env.get("AGENT_LLM_MODEL")),
        "base_url": base,
        "deadline_seconds": int(env["AGENT_RUN_DEADLINE_SECONDS"]),
    }
    if env.get("EVAL_JAVA_SHA256"):
        runtime["java_sha256"] = env["EVAL_JAVA_SHA256"]
    assert all(row.get("runtime") == runtime for row in old), (
        "Implementation changed; use a new evaluation label"
    )
    done = {row["case_id"] for row in old}
    produced = 0
    for case in cases:
        if case["id"] in done or (args.split != "all" and case["split"] != args.split):
            continue
        auth = json.loads((output / "courses" / case["clip_id"] / "session.local.json").read_text())
        task = auth["task_id"]

        def api(
            path,
            body=None,
            refresh=True,
            auth=auth,
            auth_path=output / "courses" / case["clip_id"] / "session.local.json",
        ):
            request = urllib.request.Request(
                base + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={"Authorization": "Bearer " + auth["token"], "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.loads(response.read())["data"]
            except urllib.error.HTTPError as error:
                if error.code != 401 or not refresh:
                    raise
                login = urllib.request.Request(
                    base + "/api/auth/login",
                    data=json.dumps(auth["credentials"]).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(login, timeout=10) as response:
                    auth["token"] = json.loads(response.read())["data"]["accessToken"]
                auth_path.write_text(json.dumps(auth))
                return api(path, body, refresh=False)

        endpoint = f"/api/tasks/{task}/study/command"
        key = f"eval:{args.label}:{case['id']}:{digest[:12]}"
        session = api(endpoint, {"operation": "CREATE_SESSION", "request_key": key})["session_id"]
        started = time.monotonic()
        result = api(
            endpoint, {"operation": "START", "session_id": session, "request_key": key, "goal": case["goal"]}
        )
        run_id = result["run"]["run_id"]
        while result["run"]["status"] in ["queued", "running"]:
            if time.monotonic() - started > 330:
                raise TimeoutError(f"{case['id']}: worker did not terminate; resume this same label")
            time.sleep(0.5)
            result = api(endpoint, {"operation": "READ", "session_id": session, "run_id": run_id})
        public = result.get("artifact")
        answers = None
        if public and public.get("questions"):
            answers = api(endpoint, {"operation": "ANSWERS", "session_id": session, "run_id": run_id})[
                "questions"
            ]
        canonical = api(f"/api/tasks/{task}/evidence?limit=200")["items"]
        by_id = {item["evidenceId"]: item for item in canonical}
        citations = public.get("citations", []) if public else []
        provenance = bool(public) and all(
            c["evidence_id"] in by_id
            and by_id[c["evidence_id"]]["normalizedText"].startswith(c["text"])
            and by_id[c["evidence_id"]]["startMs"] == c["start_ms"]
            and by_id[c["evidence_id"]]["endMs"] == c["end_ms"]
            for c in citations
        )
        with psycopg.connect(env["AGENT_DATABASE_URL"], row_factory=dict_row) as conn:
            journal = conn.execute(
                "SELECT sequence,event_type,payload,created_at FROM study_event WHERE run_id=%s ORDER BY sequence",
                (run_id,),
            ).fetchall()
            row = conn.execute(
                "SELECT created_at,deadline,finished_at FROM study_run WHERE run_id=%s", (run_id,)
            ).fetchone()
        claimed = next(
            (event["created_at"] for event in journal if event["event_type"] == "run_started"),
            row["created_at"],
        )
        record = {
            "case_id": case["id"],
            "split": case["split"],
            "category": case["category"],
            "expected_outcome": case["expected_outcome"],
            "dataset_sha256": digest,
            "runtime": runtime,
            "run": result["run"],
            "artifact": public,
            "answers": answers,
            "canonical": canonical,
            "provenance_valid": provenance,
            "elapsed_seconds": round((row["finished_at"] - row["created_at"]).total_seconds(), 3),
            "execution_seconds": round((row["finished_at"] - claimed).total_seconds(), 3),
            "queue_seconds": round((claimed - row["created_at"]).total_seconds(), 3),
            "observed_seconds": round(time.monotonic() - started, 3),
            "events": journal,
        }
        with destination.open("a") as file:
            file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        destination.chmod(0o600)
        print(
            case["id"],
            result["run"]["status"],
            result["run"].get("error_code"),
            record["elapsed_seconds"],
            flush=True,
        )
        produced += 1
        if args.limit is not None and produced >= args.limit:
            break


if __name__ == "__main__":
    main()
