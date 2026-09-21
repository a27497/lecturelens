#!/usr/bin/env python3
"""Fixed-draft reviewer diagnostic. No generation, runtime execution, DB writes or retries."""

import argparse
import hashlib
import importlib.util
import json
import os
import random
import time
from collections import Counter
from pathlib import Path

import lecturelens_agent
from lecturelens_agent.study.contracts import InsufficientArgs, PracticeArgs
from lecturelens_agent.study.models import ModelRegistry
from lecturelens_agent.study.quality import review_messages
from lecturelens_agent.study.store import StudyError

ROOT = Path(__file__).resolve().parents[2]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_cases(data, split="development"):
    cases = data["cases"]
    if not 1 <= len(cases) <= 8 or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Use at most eight uniquely identified cases")
    for case in cases:
        if case.get("split") != split:
            raise ValueError(f"Expected only {split} diagnostics")
        if type(case["expected"]["accept"]) is not bool or not case["expected"]["reason"]:
            raise ValueError("Freeze explicit source-based labels before calling the reviewer")
        candidate = dict(case["candidate"])
        kind = candidate.pop("kind")
        if kind not in {"practice", "insufficient_evidence"}:
            raise ValueError("Unsupported candidate kind")
        (PracticeArgs if kind == "practice" else InsufficientArgs).model_validate(candidate)
    return cases


def validate_holdout(data, runtime_sha256, development, previous_holdouts=()):
    """A new diagnostic requires a predeclared candidate and no reused dev drafts."""
    if data.get("frozen_candidate_sha256") != runtime_sha256:
        raise ValueError("Holdout candidate does not match its frozen source")
    cases = validate_cases(data, "holdout")
    prior = validate_cases(development)
    for previous in previous_holdouts:
        prior.extend(validate_cases(previous, "holdout"))
    old_ids = {case["id"] for case in prior}
    old_drafts = {json.dumps(case["candidate"], sort_keys=True) for case in prior}
    if any(c["id"] in old_ids or json.dumps(c["candidate"], sort_keys=True) in old_drafts for c in cases):
        raise ValueError("Holdout reuses a previously seen draft")
    return cases


def messages_for(case, evidence):
    # Deliberately whitelist inputs: never send id, pair, expected verdict or label rationale.
    return review_messages(case["goal"], case["candidate"], evidence)


def summarize(data, rows, split="development"):
    cases = {case["id"]: case for case in validate_cases(data, split)}
    if len({row["case_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate trial; do not replace failures with retries")
    if len({json.dumps(row["identity"], sort_keys=True) for row in rows}) > 1:
        raise ValueError("Mixed reviewer/source identities")
    counts = Counter()
    details, by_id = [], {}
    for row in rows:
        case = cases[row["case_id"]]
        expected = case["expected"]["accept"]
        observed = not row["response"]["review"]["issues"] if row["status"] == "ok" else None
        correct = observed is not None and observed == expected
        code_hit = observed is False and bool(
            set(case["expected"]["issue_any_of"]) & set(row["response"]["review"]["issues"])
        )
        counts["correct"] += correct
        counts["errors"] += observed is None
        counts["false_accepts"] += observed is True and not expected
        counts["false_rejects"] += observed is False and expected
        counts["target_code_hits"] += not expected and code_hit
        detail = {
            "case_id": row["case_id"],
            "pair": case["pair"],
            "expected_accept": expected,
            "observed_accept": observed,
            "correct": correct,
            "target_code_hit": bool(code_hit),
            "issues": row.get("response", {}).get("review", {}).get("issues"),
            "error_code": row.get("error_code"),
            "seconds": row["seconds"],
        }
        details.append(detail)
        by_id[row["case_id"]] = detail
    pairs = {}
    for group in sorted({c["pair"] for c in cases.values()}):
        members = [c for c in cases.values() if c["pair"] == group]
        pairs[group] = all(by_id.get(c["id"], {}).get("correct", False) for c in members)
    usage = [r.get("usage", {}) for r in rows]
    return {
        "expected_cases": len(cases),
        "observed_cases": len(rows),
        "expected_accepts": sum(c["expected"]["accept"] for c in cases.values()),
        "expected_rejects": sum(not c["expected"]["accept"] for c in cases.values()),
        **counts,
        "all_labels_matched": len(rows) == len(cases) and counts["correct"] == len(cases),
        "pairs_both_correct": pairs,
        "known_prompt_tokens": sum(u.get("prompt_tokens", 0) for u in usage),
        "known_completion_tokens": sum(u.get("completion_tokens", 0) for u in usage),
        "calls_without_complete_usage": sum(
            not all(k in u for k in ["prompt_tokens", "completion_tokens"]) for u in usage
        ),
        "cases": details,
        "full_l2_gate_assessed": False,
        "scope": f"Fixed source-annotated {split} drafts; direct reviewer only; no generation, repair, runtime or full-stack evaluation.",
        "assessment": "Pre-call Codex source-based labels, not blind human gold. Code hits do not establish useful correction feedback.",
    }


def write_new(path, value):
    with path.open("x") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-config", required=True, type=Path)
    parser.add_argument("--owner-id", required=True, type=int)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--variant", required=True, choices=["c", "e", "f", "g", "h", "i", "j", "k", "l", "m"]
    )
    parser.add_argument("--split", choices=["development", "holdout"], default="development")
    args = parser.parse_args()
    os.umask(0o077)
    package = Path(lecturelens_agent.__file__).resolve().parent
    if not package.is_relative_to(args.output.resolve() / "src"):
        raise ValueError("Use the frozen output/src package on PYTHONPATH")
    data = json.loads(args.cases.read_text())
    runtime_sha256 = digest(
        b"".join(str(p.relative_to(package)).encode() + p.read_bytes() for p in sorted(package.rglob("*.py")))
    )
    cases = (
        validate_holdout(
            data,
            runtime_sha256,
            json.loads((ROOT / "eval/reviewer-probe/cases.json").read_text()),
            [
                json.loads(path.read_text())
                for path in sorted((ROOT / "eval/reviewer-probe").glob("holdout-*.json"))
                if path.resolve() != args.cases.resolve()
            ],
        )
        if args.split == "holdout"
        else validate_cases(data)
    )
    order = list(range(len(cases)))
    random.Random(data["order_seed"]).shuffle(order)
    source = json.loads((ROOT / "eval/study-v2/sources.json").read_text())
    spec = importlib.util.spec_from_file_location(
        "review_probe_evidence", Path(__file__).with_name("replay-study-quality.py")
    )
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    evidence = replay.captions(source, ROOT / ".data/study-v2/lecture4.vtt")
    allowed = {e["evidence_id"] for e in evidence}
    for case in cases:
        candidate = case["candidate"]
        refs = set(candidate.get("evidence_ids", []))
        for question in candidate.get("questions", []):
            refs.update(question["evidence_ids"])
        if not refs <= allowed:
            raise ValueError("Unknown evidence reference")
    deployment = json.loads(args.runtime_config.read_text())
    os.environ.update(deployment)
    registry = ModelRegistry(deployment["AGENT_DATABASE_URL"], deployment["AGENT_SERVICE_SECRET"])
    config = registry.freeze(args.owner_id)["review"]
    if config["model"] != "qwen3-max":
        raise ValueError("Review model changed; re-scope the diagnostic first")
    provider = registry.client(config)
    # Preserve returned tool arguments even if the review validator rejects them.
    # This is private diagnostic recording; it does not retry or alter the request.
    wire_responses = []
    request = provider._request

    def recorded_request(*args, **kwargs):
        response = request(*args, **kwargs)
        wire_responses.append(response)
        return response

    provider._request = recorded_request
    identity = {
        "protocol": "fixed-draft-reviewer-probe-v1",
        "variant": args.variant,
        "runtime_sha256": runtime_sha256,
        "evaluation_split": args.split,
        "runner_sha256": digest(Path(__file__).read_bytes()),
        "dataset_sha256": digest(args.cases.read_bytes()),
        "evidence_sha256": digest(json.dumps(evidence, sort_keys=True).encode()),
        "source_sha256": source["subtitle_sha256"],
        "reviewer": {k: config[k] for k in ["model", "version", "base_url"]},
        "order": [cases[i]["id"] for i in order],
        "timeout_seconds": 30,
        "max_output_tokens": 300,
        "temperature": 0.2,
        "retries": 0,
        "labels_sent": False,
        "runtime_executed": False,
        "database_writes": False,
    }
    write_new(args.output / "identity.json", identity)
    write_new(args.output / "cases.json", data)
    write_new(args.output / "evidence.json", evidence)
    rows = []
    with (args.output / "results.jsonl").open("x") as output:
        for index in order:
            case = cases[index]
            messages = messages_for(case, evidence)
            row = {"identity": identity, "case_id": case["id"], "messages": messages}
            started = time.monotonic()
            wire_responses.clear()
            try:
                response = provider.review(messages, 30)
                row.update(status="ok", response=response, usage=response.get("usage", {}))
            except Exception as error:  # noqa: BLE001 -- record bounded code; never provider/credential text
                row.update(
                    status="failed",
                    error_code=error.code if isinstance(error, StudyError) else "PROBE_EXECUTION_FAILED",
                    usage=getattr(error, "usage", {}),
                    diagnostics=getattr(error, "diagnostics", {}),
                )
            row["wire_responses"] = wire_responses.copy()
            row["seconds"] = round(time.monotonic() - started, 4)
            serialized = json.dumps(row, ensure_ascii=False)
            if provider.key:
                serialized = serialized.replace(provider.key, "[REDACTED]")
            output.write(serialized + "\n")
            output.flush()
            os.fsync(output.fileno())
            rows.append(json.loads(serialized))
            print(
                json.dumps({"variant": args.variant, "case": case["id"], "status": row["status"]}), flush=True
            )
    write_new(args.output / "report.json", summarize(data, rows, args.split))


if __name__ == "__main__":
    main()
