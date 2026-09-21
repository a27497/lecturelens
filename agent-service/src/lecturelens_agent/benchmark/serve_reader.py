"""Start a separate, hash-verified local reader; leave the production model untouched."""

import argparse
import json
import os
from pathlib import Path

from .core import digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--model-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8096)
    args = parser.parse_args()
    config = json.loads((args.dataset / "config.json").read_text())["reader"]
    if digest(args.server) != config["server_sha256"]:
        raise ValueError("Reader binary changed")
    if digest(args.model_file) != config["provenance"]["qwen2.5-3b-instruct-q4_k_m.gguf_sha256"]:
        raise ValueError("Reader weights changed")
    os.execv(
        str(args.server.resolve()),
        [
            str(args.server),
            "-m",
            str(args.model_file.resolve()),
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
            "--alias",
            config["model"],
            "--jinja",
            "-c",
            "8192",
            "-np",
            "1",
            "-t",
            "4",
        ],
    )


if __name__ == "__main__":
    main()
