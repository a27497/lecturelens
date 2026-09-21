#!/usr/bin/env python3
"""Frozen development probes: direct reviewer, no generation, repair or retries.

Inputs and complete request/response records belong in an ignored private directory.
Expected labels never enter model messages. A protocol failure remains a failed trial.
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from lecturelens_agent.study.provider import ChatProvider
from lecturelens_agent.study.quality import (
    review_messages,
    review_schema,
    review_wire_messages,
)
from lecturelens_agent.study.support_review import output_tokens


def source_digest():
    root = Path(__file__).resolve().parents[2] / "agent-service/src"
    digest = hashlib.sha256()
    for path in sorted((root / "lecturelens_agent").rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def raw_model_accept(arguments):
    """Only called after a valid protocol response; excludes local policy vetoes."""
    checks = arguments.get("checks") or [
        arguments[name] for name in ("explanation", "question_1", "question_2")
    ]
    return (
        all(
            check["issue"] == "none"
            and (check.get("answer_check") is None or check["answer_check"]["matches"])
            for check in checks
        )
        and all(check["matches"] for check in arguments.get("goal_checks", []))
        and all(check["supported"] for check in arguments.get("explanation_checks", []))
        and arguments.get("application_method_check", {}).get("matches", True)
        and all(
            check.get("method_alignment", {}).get("matches", True)
            for check in checks
            if check.get("method_alignment")
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["runtime-config", "cases", "freeze", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--check-goal", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    freeze = json.loads(args.freeze.read_text())
    assert source_digest() == freeze["source_sha256"]
    assert hashlib.sha256(args.cases.read_bytes()).hexdigest() == freeze["tasks_sha256"]
    cases = json.loads(args.cases.read_text())["cases"]
    assert 1 <= len(cases) <= 8 and len({c["id"] for c in cases}) == len(cases)
    assert all(type(c["expected_accept"]) is bool and c["label_reason"] for c in cases)
    args.output.mkdir(parents=True, exist_ok=False)
    config = json.loads(args.runtime_config.read_text())
    provider = ChatProvider(
        config["AGENT_LLM_BASE_URL"],
        config["AGENT_LLM_MODEL"],
        config["AGENT_LLM_API_KEY"],
    )
    for case in cases:
        directory = args.output / case["id"]
        directory.mkdir()
        request = review_messages(
            case["goal"],
            case["candidate"],
            case["evidence"],
            structured_support=True,
            application_method=case["application_method"],
            check_goal=args.check_goal,
        )
        body = json.loads(request[-1]["content"])
        wire = review_wire_messages(request)
        schema = review_schema(
            body["candidate"]["kind"],
            body.get("rubric_policy"),
            body["review_mode"],
            method_scope=True,
            context=body,
        )
        (directory / "request.json").write_text(
            json.dumps(
                {
                    "messages": wire,
                    "schemas": [schema],
                    "max_tokens": output_tokens(body["review_mode"]),
                },
                ensure_ascii=False,
            )
        )
        provider.response_observer = lambda data, directory=directory: (
            directory / "response.json"
        ).write_bytes(data.replace(provider.key.encode(), b"[redacted]") if provider.key else data)
        record = {
            "case_id": case["id"],
            "source_sha256": freeze["source_sha256"],
            "model": provider.model,
            "started_at": time.time(),
            "expected_accept": case["expected_accept"],
            "status": "started",
        }
        path = directory / "result.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        try:
            record["response"] = provider.review(request, 90)
            record["status"] = "completed"
            review = record["response"]["review"]
            raw = json.loads((directory / "response.json").read_text())
            arguments = raw["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            record["model_observed_accept"] = raw_model_accept(arguments)
            record["model_label_matched"] = record["model_observed_accept"] == case["expected_accept"]
            record["rule_observations"] = review.get("rule_observations", [])
            record["observed_accept"] = not review["issues"]
            record["label_matched"] = record["observed_accept"] == case["expected_accept"]
        except Exception as error:  # noqa: BLE001 - preserve all failed trials before continuing the fixed batch
            record.update(
                status="failed",
                error_type=type(error).__name__,
                error_code=getattr(error, "code", None),
                usage=getattr(error, "usage", {}),
                label_matched=False,
            )
        record["finished_at"] = time.time()
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        print(
            case["id"],
            record["status"],
            "label_matched=" + str(record["label_matched"]),
            flush=True,
        )


if __name__ == "__main__":
    main()
