"""Recorded source-support diagnostics; these are not end-to-end Study trials."""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from run import ROOT, save, source_digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime", "source", "cases", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    for path in (args.runtime, args.cases, args.output):
        if not path.resolve().is_relative_to(ROOT / ".data"):
            parser.error("Private inputs and results must stay in ignored .data")
    config = json.loads(args.runtime.read_text())
    if (
        config["AGENT_LLM_MODE"] != "real"
        or config["AGENT_RUN_DEADLINE_SECONDS"] != "90"
    ):
        parser.error("Use the isolated real-provider configuration")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    freeze = {
        "source_sha256": source_digest(args.source),
        "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "model": config["AGENT_LLM_MODEL"],
        "kind": "development-source-review-diagnostic",
        "timeout_seconds": 30,
    }
    save(args.output / "freeze.json", freeze)
    sys.path.insert(0, str(args.source.resolve()))
    from lecturelens_agent.study.provider import ChatProvider
    from lecturelens_agent.study.quality import review_messages
    from lecturelens_agent.study.runtime import price_review
    from lecturelens_agent.study.store import BudgetExceeded, StudyError

    provider = ChatProvider(
        config["AGENT_LLM_BASE_URL"],
        config["AGENT_LLM_MODEL"],
        config["AGENT_LLM_API_KEY"],
    )
    summary = []
    for case in json.loads(args.cases.read_text())["cases"]:
        identifier = case["id"]
        if not identifier.replace("-", "").isalnum():
            raise ValueError("Invalid case ID")
        messages = review_messages(
            case["goal"],
            {
                "kind": "explanation",
                "title": "Source review",
                "explanation": case["answer"],
                "evidence_ids": ["own"],
            },
            [{"evidence_id": "own", "text": case["source"]}],
        )
        record = {
            "case": case,
            "messages": messages,
            "estimate": price_review(provider, messages),
        }
        record_path = args.output / (identifier + ".private.json")
        save(record_path, record)
        started = time.monotonic()
        provider.response_observer = lambda raw, label=identifier: save(
            args.output / (label + "-response.private.json"), json.loads(raw)
        )
        try:
            result = provider.review(messages, 30)
            accepted = not result["review"]["issues"]
            record.update(
                result=result,
                accepted=accepted,
                correct=accepted == case["expected_accepted"],
            )
        except (StudyError, BudgetExceeded) as error:
            record.update(
                error_code=getattr(error, "code", type(error).__name__), correct=False
            )
        record["seconds"] = round(time.monotonic() - started, 3)
        save(record_path, record)
        row = {"id": identifier, **{k: record[k] for k in ("correct", "seconds")}}
        row.update({k: record[k] for k in ("accepted", "error_code") if k in record})
        summary.append(row)
        save(args.output / "summary.json", summary)
        print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
