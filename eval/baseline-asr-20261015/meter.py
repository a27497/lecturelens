"""Transparent evaluation-only ASR/index HTTP metering; never retries or caches."""

import argparse
import hashlib
import http.server
import json
import ssl
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

LOCK = threading.Lock()
SPENT = 0.0
INFLIGHT = 0
UNKNOWN = False


def utc():
    return datetime.now(timezone.utc).isoformat()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # Headers, credentials and upstream request bodies never enter logs.

    def do_POST(self):
        global SPENT, INFLIGHT, UNKNOWN
        settings = self.server.settings
        body = self.rfile.read(int(self.headers["Content-Length"]))
        payload = json.loads(body)
        marker = settings.private / "active-trial.json"
        trial = json.loads(marker.read_text()) if marker.exists() else {}
        record = {
            "trial_id": trial.get("trial_id"),
            "kind": self.server.kind,
            "started_at_utc": utc(),
            "path": self.path,
            "request_sha256": hashlib.sha256(body).hexdigest(),
            "operation": payload.get("operation"),
            "course_id": payload.get("course_id"),
        }
        if self.server.kind == "asr":
            with LOCK:
                # Reserve headroom for both already-running chunks. This is a
                # spending guard, never a substitute for observed billing usage.
                if UNKNOWN or SPENT + INFLIGHT + 1 > 28:
                    self.send_error(402, "Evaluation budget or missing usage stop")
                    return
                INFLIGHT += 1
        started = time.monotonic()
        response = None
        try:
            response = httpx.post(
                self.server.upstream + self.path,
                content=body,
                headers={
                    k: v
                    for k, v in self.headers.items()
                    if k.lower() not in {"host", "content-length", "connection"}
                },
                timeout=httpx.Timeout(180, connect=5),
                follow_redirects=False,
            )
            parsed = response.json()
            record.update(
                http_status=response.status_code,
                usage=parsed.get("usage"),
                error_code=parsed.get("code"),
            )
            if self.server.kind == "asr":
                usage = parsed.get("usage") or {}
                complete = all(
                    type(usage.get(k)) is int and usage[k] >= 0
                    for k in ("input_tokens", "output_tokens")
                )
                record["list_price_cny"] = (
                    (usage["input_tokens"] * 0.8 + usage["output_tokens"] * 2.7)
                    / 1_000_000
                    if complete
                    else None
                )
                with LOCK:
                    if complete:
                        SPENT += record["list_price_cny"]
                    elif response.is_success:
                        UNKNOWN = True
                    else:
                        # Unknown failed-request charges stay unavailable in
                        # reports; reserve conservative budget headroom only.
                        SPENT += 1
        except Exception as error:  # noqa: BLE001 -- record and fail closed on every meter failure
            record.update(
                http_status=None,
                usage=None,
                error_type=type(error).__name__,
                list_price_cny=None,
            )
            if self.server.kind == "asr":
                with LOCK:
                    UNKNOWN = True
        finally:
            record["upstream_elapsed_ms"] = round(
                (time.monotonic() - started) * 1000, 3
            )
            record["finished_at_utc"] = utc()
            with LOCK:
                if self.server.kind == "asr":
                    INFLIGHT -= 1
                with settings.records.open("a") as output:
                    output.write(json.dumps(record) + "\n")
        if response is None:
            self.send_error(502, "Evaluation upstream transport failure")
        else:
            self.send_response(response.status_code)
            self.send_header(
                "Content-Type", response.headers.get("Content-Type", "application/json")
            )
            self.send_header("Content-Length", str(len(response.content)))
            self.end_headers()
            self.wfile.write(response.content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--source-pid", type=int, required=True)
    args = parser.parse_args()
    # Read the existing process environment without copying credentials to disk.
    env = dict(
        item.split("=", 1)
        for item in Path(f"/proc/{args.source_pid}/environ").read_text().split("\0")
        if "=" in item
    )
    for line in args.records.read_text().splitlines() if args.records.exists() else []:
        record = json.loads(line)
        if record["kind"] == "asr":
            global SPENT, UNKNOWN
            SPENT += record.get("list_price_cny") or 1
            UNKNOWN |= (
                record.get("http_status") == 200
                and record.get("list_price_cny") is None
            )
    asr_url = httpx.URL(env["BAILIAN_ASR_ENDPOINT"])
    configurations = [
        (18443, "asr", str(asr_url.copy_with(path=""))),
        (18099, "index", env["AGENT_SERVICE_URL"].rstrip("/")),
    ]
    for port, kind, upstream in configurations:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
        server.settings, server.kind, server.upstream = args, kind, upstream.rstrip("/")
        if kind == "asr":
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(args.private / "cert.pem", args.private / "key.pem")
            server.socket = context.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print("Evaluation meters listening on loopback", flush=True)
    threading.Event().wait()


if __name__ == "__main__":
    main()
