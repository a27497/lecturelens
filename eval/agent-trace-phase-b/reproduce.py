"""Replay recorded model transport through archived runtime with LIVE Java authority.

Requires an isolated service stack with its automatic worker paused. Only the new
run is executed here. No tool result, evidence, checkpoint, permission or business
state is supplied by the recording. Credentials are read exclusively from env.
"""

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lecturelens_agent.study.replay import start_replay
from lecturelens_agent.study.store import StudyStore
from lecturelens_agent.study.trace import RunTrace
from lecturelens_agent.study.trace_cli import JavaGateway

WORKER = r"""
import os,sys,json
sys.path.insert(0,sys.argv[1])
from lecturelens_agent.study.store import StudyStore
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.provider import ChatProvider
from lecturelens_agent.study.authority import EvidenceAuthority
store=StudyStore(os.environ['AGENT_DATABASE_URL'])
with store.connect() as conn:
    run=conn.execute('SELECT r.*,s.owner_id,s.course_id,s.revision FROM study_run r JOIN study_session s USING(session_id) WHERE run_id=%s',(sys.argv[2],)).fetchone()
assert run['status']=='queued', 'Replay run must be queued in an isolated stack with worker paused'
provider=ChatProvider(base_url=sys.argv[3],model=sys.argv[4],api_key='recorded-transport-only')
runtime=StudyRuntime(store,EvidenceAuthority(os.environ['AGENT_JAVA_BASE_URL'],os.environ['AGENT_SERVICE_SECRET']),provider,seconds=90)
runtime.execute(run)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--request-key", required=True)
    parser.add_argument("--archive", type=pathlib.Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--calls-log", type=pathlib.Path, required=True)
    parser.add_argument("--calls-dir", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    trace = RunTrace(
        StudyStore(os.environ["AGENT_DATABASE_URL"]),
        JavaGateway(args.base_url, os.environ["LECTURELENS_AUTH_TOKEN"]),
    )
    source = trace.read(args.run_id)
    if source["run"]["status"] != "failed":
        parser.error("Use a real failed historical run")
    records = [json.loads(line) for line in args.calls_log.read_text().splitlines()]
    records = [r for r in records if r.get("run_id") == args.run_id and r.get("event") == "started"]
    if not records or any(r["source_sha256"] != args.source_sha256 for r in records):
        parser.error("Recording/source identity mismatch")
    archived = args.output / "archived"
    with tarfile.open(args.archive) as archive:
        archive.extractall(archived, filter="data")
    digest = hashlib.sha256()
    for path in sorted((archived / "src/lecturelens_agent").rglob("*.py")):
        digest.update(str(path.relative_to(archived / "src")).encode())
        digest.update(path.read_bytes())
    if digest.hexdigest() != args.source_sha256:
        parser.error("Archived source hash mismatch")
    responses = [(args.calls_dir / r["call_id"] / "response.json").read_bytes() for r in records]
    cursor = 0
    requests = []

    class Transport(BaseHTTPRequestHandler):
        def do_POST(self):
            nonlocal cursor
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(request)
            if cursor >= len(responses):
                self.send_error(409)
                return
            body = responses[cursor]
            cursor += 1
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    result = start_replay(trace, args.run_id, args.request_key, mode="recorded_model_response")
    run_id = result["run"]["run_id"]
    (args.output / "start.json").write_text(json.dumps(result, default=str, indent=2))
    server = ThreadingHTTPServer(("127.0.0.1", 0), Transport)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        worker = subprocess.run(
            [
                sys.executable,
                "-c",
                WORKER,
                str((archived / "src").resolve()),
                run_id,
                f"http://127.0.0.1:{server.server_port}/v1",
                records[0]["model"],
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        (args.output / "worker.log").write_text(worker.stdout + worker.stderr)
    finally:
        server.shutdown()
        server.server_close()
    after = trace.read(run_id)
    (args.output / "trace.json").write_text(json.dumps(after, ensure_ascii=False, default=str, indent=2))
    (args.output / "requests.json").write_text(json.dumps(requests, ensure_ascii=False, indent=2))
    equivalence = []
    for record, request in zip(records, requests, strict=False):
        original = json.loads((args.calls_dir / record["call_id"] / "request.json").read_text())
        equivalence.append(
            {
                "messages_equal": original["messages"] == request["messages"],
                "schemas_equal": original["schemas"] == request["tools"],
            }
        )
    report = {
        "source_run_id": args.run_id,
        "replay_run_id": run_id,
        "source_sha256": digest.hexdigest(),
        "transport": "recorded_model_response",
        "new_billable_model_calls": 0,
        "response_sha256": [hashlib.sha256(r).hexdigest() for r in responses],
        "consumed_responses": cursor,
        "request_equivalence": equivalence,
        "worker_exit_code": worker.returncode,
        "status": after["run"]["status"],
        "error_code": after["run"]["error_code"],
        "failure_type": after["failure_type"],
        "reproduced": after["run"]["error_code"] == source["run"]["error_code"] and cursor == len(responses),
        "metrics": after["metrics"],
    }
    (args.output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))
    if not report["reproduced"] or worker.returncode:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
