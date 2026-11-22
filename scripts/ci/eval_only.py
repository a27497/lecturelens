#!/usr/bin/env python3
"""Classify an effective PR diff for CI."""

import subprocess
import sys


# Keep this list and the Eval Fixtures job in sync when tests start reading eval data.
FIXTURE_PREFIXES = (
    b"eval/feedback-v1/",
    b"eval/p7-real/",
    b"eval/p8-tutor/",
    b"eval/retrieval-phase-a/",
    b"eval/retrieval-v2/",
    b"eval/reviewer-probe/",
    b"eval/source-support/",
    b"eval/tool-resilience-20261014/",
    b"eval/tool-resilience-latency-20261014/",
)


def ci_route(base: str, head: str) -> str:
    # Treat a rename as a deletion and an addition so either side can require full CI.
    diff = subprocess.check_output(
        ["git", "diff", "--name-only", "--no-renames", "-z", base, head, "--"]
    )
    paths = diff.split(b"\0")[:-1]
    if not paths or any(
        not path.startswith(b"eval/") or not path.endswith((b".md", b".json", b".jsonl"))
        for path in paths
    ):
        return "full"
    if any(path.startswith(FIXTURE_PREFIXES) for path in paths):
        return "eval-fixtures"
    return "eval-reports"


if __name__ == "__main__":
    print(ci_route(*sys.argv[1:]))
