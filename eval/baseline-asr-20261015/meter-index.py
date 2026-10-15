"""Observe existing index HTTP calls only; no ASR forwarding or model retries."""

import argparse
import http.server
import os
from pathlib import Path

from meter import Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--source-pid", type=int, required=True)
    args = parser.parse_args()
    env = dict(
        item.split("=", 1)
        for item in Path(f"/proc/{args.source_pid}/environ").read_text().split("\0")
        if "=" in item
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 18099), Handler)
    server.settings = args
    server.kind = "index"
    server.upstream = env["AGENT_SERVICE_URL"].rstrip("/")
    print("Index meter PID", os.getpid(), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
