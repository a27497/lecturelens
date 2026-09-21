"""python -m lecturelens_agent.study.trace_cli --help"""

import argparse
import json
import os
import time
from urllib.parse import quote, urlsplit

import httpx

from .replay import start_replay
from .store import TERMINAL, StudyError, StudyStore
from .trace import RunTrace, compare


class JavaGateway:
    def __init__(self, base_url, token):
        url = urlsplit(base_url)
        if (
            (
                url.scheme != "https"
                and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"})
            )
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise StudyError("INVALID_GATEWAY_URL", 422)
        if not token:
            raise StudyError("AUTH_TOKEN_REQUIRED", 401)
        self.base_url, self.token = base_url.rstrip("/"), token

    def command(self, course_id, command):
        try:
            with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as client:
                response = client.post(
                    f"{self.base_url}/api/tasks/{quote(course_id, safe='')}/study/command",
                    headers={"Authorization": "Bearer " + self.token},
                    json=command,
                )
            if response.status_code != 200:
                raise StudyError("JAVA_AUTHORITY_REJECTED", response.status_code)
            body = response.json()
            result = body.get("data")
            if not isinstance(result, dict) or "owner_id" not in result:
                raise StudyError("JAVA_AUTHORITY_REJECTED", 403)
            return result
        except (httpx.HTTPError, ValueError):
            raise StudyError("JAVA_GATEWAY_UNAVAILABLE", 503) from None


def main():
    parser = argparse.ArgumentParser(
        description="Private Run Trace / authorized fresh Replay (operator DB + Java login required)"
    )
    parser.add_argument("operation", choices=["trace", "replay", "compare"])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--after-run-id")
    parser.add_argument("--request-key")
    parser.add_argument("--wait-seconds", type=int, default=0)
    parser.add_argument(
        "--output", required=True, help="New private JSON file; never overwrites an earlier trial"
    )
    args = parser.parse_args()
    if not 0 <= args.wait_seconds <= 600:
        parser.error("wait-seconds must be 0..600")
    if os.path.exists(args.output):
        parser.error("output already exists; preserve the earlier trial")
    if args.operation == "compare" and not args.after_run_id:
        parser.error("compare requires --after-run-id")
    try:
        trace = RunTrace(
            StudyStore(os.environ["AGENT_DATABASE_URL"]),
            JavaGateway(args.base_url, os.environ.get("LECTURELENS_AUTH_TOKEN", "")),
        )
        if args.operation == "replay":
            result = start_replay(trace, args.run_id, args.request_key)
            run_id = result["run"]["run_id"]
            until = time.monotonic() + args.wait_seconds
            while args.wait_seconds and result["run"]["status"] not in TERMINAL and time.monotonic() < until:
                time.sleep(1)
                result = trace.authorize(trace.locate(run_id))
            result = {"source_run_id": args.run_id, "replay": result}
        elif args.operation == "compare":
            result = compare(trace.read(args.run_id), trace.read(args.after_run_id))
        else:
            result = trace.read(args.run_id)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(result, output, ensure_ascii=False, indent=2, default=str)
            output.write("\n")
        print(json.dumps({"output": args.output, "operation": args.operation}))
    except StudyError as error:
        parser.exit(1, error.code + "\n")
    except (KeyError, OSError):
        parser.exit(1, "Trace configuration or output unavailable\n")


if __name__ == "__main__":
    main()
