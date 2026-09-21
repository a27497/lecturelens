"""Append a fresh, non-vacuous HTTP isolation audit without changing trial outcomes."""

import argparse
import hashlib
import json
from pathlib import Path

from run import PRIVATE, configure, isolation, login, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    configure()
    folder = PRIVATE / args.label
    destination = folder / "isolation-audit-v2.json"
    if destination.exists():
        parser.error("Preserve the existing audit")
    items = json.loads((folder / "manifest.local.json").read_text())
    for item in items:
        item["user"] = login(item["user"]["number"])
    traces = [json.loads((folder / (item["run_id"] + ".trace.json")).read_text()) for item in items]
    result = isolation(items, traces)
    result["harness_sha256"] = hashlib.sha256(Path(__file__).with_name("run.py").read_bytes()).hexdigest()
    result["note"] = (
        "Fresh HTTP probes and read-only checkpoint audit. Foreign IDs come from the peer's authoritative nonempty Evidence list, including failed Runs. Original experiment results are unchanged."
    )
    save(destination, result)
    print(
        json.dumps({"label": args.label, "violations": result["violations"], "checks": len(result["checks"])})
    )


if __name__ == "__main__":
    main()
