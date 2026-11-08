"""Offline review export and layered aggregation; never calls an AI reviewer."""

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval/phase1a-tutor-readiness-20261108"))
from prepare import inspect  # noqa: E402
from quality_gate import CANDIDATE, PACKET, POINTS, TURN_KEYS  # noqa: E402


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2, default=str).encode() + b"\n"


def oracle():
    names, length, trace, inner = ["Ada", "Grace"], 2, [2], []
    for _ in names:
        length += 1
        trace.append(length)
        inner.append(length)
    return {
        "premises": {"names": names, "initial_length": 2},
        "trace": trace,
        "final_value": length,
        "inside_prints": inner,
        "outside_prints": [length],
        "index_0": names[0],
        "index_1": names[1],
        "kind": "EXECUTED_TRUSTED_REFERENCE_NOT_GENERATED_CODE",
    }


def canonical_course(snapshot, course):
    # Frozen v19 groups source passages and derives their IDs before retrieval.
    # Reuse that exact read-only transform, never IDs/text copied from responses.
    # Only this packet's development course enters the derived review material.
    from lecturelens_real_eval.tutor.claim_grounding_runtime import LessonAuthority

    original = snapshot["lectures"][course]
    if original["split"] != "development":
        raise ValueError("ONLY_ORIGINAL_EXPOSED_DEVELOPMENT_COURSE")
    return LessonAuthority({"lectures": {course: original}}).snapshot["lectures"][
        course
    ]


def deterministic(outcomes, summary, evidence, calls, ledger, requests):
    checks = {}
    checks["ordered_positions"] = [r.get("turn_key") for r in outcomes] == TURN_KEYS
    checks["all_completed"] = len(outcomes) == 3 and all(
        r.get("status") == "completed" for r in outcomes
    )
    checks["frozen_identity"] = (
        summary.get("candidate_sha256") == CANDIDATE
        and summary.get("packet_sha256") == PACKET
    )
    checks["live_not_mock"] = summary.get("mode") == "live" and all(
        r.get("live") is True for r in calls
    )
    checks["bounded_sends"] = (
        type(summary.get("sent_requests")) is int
        and 1 <= summary["sent_requests"] <= 12
        and len(calls) == len(requests) == summary["sent_requests"]
    )
    checks["per_turn_calls"] = all(
        sum(c.get("turn_key") == key for c in calls) <= 4 for key in TURN_KEYS
    )
    checks["tutor_only"] = all(
        c.get("purpose") == "tutor" and c.get("turn_key") in TURN_KEYS for c in calls
    )
    checks["no_reviewer_or_embedding"] = (
        summary.get("reviewer_calls") == summary.get("embedding_calls") == 0
    )
    checks["wire_profile"] = all(
        len(raw) <= 65536
        and p.get("model") == "deepseek-flash"
        and p.get("max_tokens") == 4096
        and p.get("thinking") == {"type": "disabled"}
        and p.get("temperature") == 0
        and p.get("tool_choice") == "required"
        and p.get("parallel_tool_calls") is False
        for raw in requests
        for p in [json.loads(raw)]
    )
    checks["wire_hashes"] = len(calls) == len(requests) and all(
        c.get("request_sha256") == sha(raw)
        for c, raw in zip(calls, requests, strict=False)
    )
    checks["usage_and_model"] = all(
        c.get("status") == "SUCCEEDED"
        and c.get("returned_model") == "deepseek-flash"
        and type((c.get("usage") or {}).get("prompt_tokens")) is int
        and c["usage"]["prompt_tokens"] >= 0
        and type(c["usage"].get("completion_tokens")) is int
        and 0 <= c["usage"]["completion_tokens"] <= 4096
        for c in calls
    )
    latest = {}
    valid_ledger = True
    for n, r in enumerate(ledger, 1):
        valid_ledger &= r.get("sequence") == n
        latest[r["call_id"]] = r
    cost = sum(r["charged_nano_usd"] for r in latest.values())
    checks["ledger"] = (
        valid_ledger
        and len(latest) == len(calls)
        and all(r["state"] == "settled" and not r.get("error") for r in latest.values())
        and cost <= 300000000
        and summary.get("ledger", {}).get("nano_usd") == cost
        and not summary.get("ledger", {}).get("pending")
        and not summary.get("ledger", {}).get("blocked")
    )
    checks["ledger_wire_binding"] = all(
        c.get("ledger_call_id") in latest
        and latest[c["ledger_call_id"]]["wire_sha256"] == c.get("request_sha256")
        for c in calls
    )
    canonical = {e["evidence_id"]: e for e in evidence}
    checks["source_binding"] = all(
        r.get("citations")
        and len(r["citations"]) <= 4
        and all(
            c.get("evidence_id") in canonical
            and c.get("text") == canonical[c["evidence_id"]]["text"]
            for c in r["citations"]
        )
        for r in outcomes
        if r.get("status") == "completed"
    )
    checks["rendered_limits"] = all(
        isinstance(r.get("answer"), str)
        and len(r["answer"]) <= 4096
        and len(r.get("evaluation") or "") <= 1024
        for r in outcomes
        if r.get("status") == "completed"
    )
    code = []
    for row in outcomes:
        for block in re.findall(
            r"```python\s*\n(.*?)```", row.get("answer") or "", re.DOTALL
        ):
            try:
                ast.parse(block)
                result = "SYNTAX_PASS"
            except SyntaxError:
                result = "SYNTAX_FAIL"
            code.append(
                {
                    "turn_key": row["turn_key"],
                    "sha256": sha(block.encode()),
                    "syntax": result,
                    "execution": "NOT_EXECUTED_UNTRUSTED_MODEL_CODE",
                }
            )
    checks["available_code_syntax"] = all(c["syntax"] == "SYNTAX_PASS" for c in code)
    return {
        "mechanical": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "local_nano_usd": cost,
        "reference_oracle": oracle(),
        "generated_code": code,
        "generated_code_semantics": "UNRESOLVED_EXTERNAL_REVIEW_REQUIRED",
        "citation_semantics": "UNRESOLVED_EXTERNAL_REVIEW_REQUIRED",
        "pg_mirror": "FROZEN_RUNNER_CHECK_REPORTED_NOT_REQUERIED",
    }


def export(root, destination, execution=None):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    state = inspect(root)
    base = root / "eval/tutor-selection-v19-v1"
    packet = json.loads((base / "sample-candidate.json").read_bytes())
    snapshot = json.loads((root / "eval/tutor-v14-fresh-v1/snapshot.json").read_bytes())
    course = packet["sessions"][0]["course_id"]
    selected = canonical_course(snapshot, course)
    outputs = [
        {
            "turn_key": k,
            "status": "SKIPPED",
            "reason": "PREFLIGHT_BLOCKED_NO_GENERATION",
        }
        for k in TURN_KEYS
    ]
    summary = {"mode": "NOT_RUN", "real_model_calls": 0, "quality": "NOT_RUN"}
    checks = {"mechanical": "NOT_RUN", "reference_oracle": oracle()}
    assets = {
        "candidate.json": (base / "candidate.json").read_bytes(),
        "original-packet.json": (base / "sample-candidate.json").read_bytes(),
        "original-reference-review.json": (
            base / "reference-review-pack.json"
        ).read_bytes(),
        "course.md": (
            root / "eval/tutor-v14-fresh-v1/materials/carpentries-python-new.md"
        ).read_bytes(),
        "course-evidence.json": encode(selected),
        "course-evidence-original.json": encode(snapshot["lectures"][course]),
        "evidence-mapping.json": encode(
            {
                "transform": "FROZEN_V19_LessonAuthority_SOURCE_ONLY",
                "execution_head": state["execution_head"],
                "original_sha256": sha(encode(snapshot["lectures"][course])),
                "canonical_sha256": sha(encode(selected)),
                "mapping": [
                    {
                        "evidence_id": row["evidence_id"],
                        "member_evidence_ids": row["member_evidence_ids"],
                        "content_hash": row["content_hash"],
                    }
                    for row in selected["evidence"]
                ],
            }
        ),
        "review-plan.json": Path(__file__).with_name("review-plan.json").read_bytes(),
        "REVIEW_PROMPT.md": Path(__file__).with_name("REVIEW_PROMPT.md").read_bytes(),
    }
    if execution:
        execution = Path(execution).resolve()
        if not execution.is_relative_to(root / ".data"):
            raise ValueError("FROZEN_PRIVATE_EXECUTION_DIRECTORY_REQUIRED")
        summary = json.loads((execution / "summary.json").read_bytes())
        if summary.get("mode") != "live":
            raise ValueError("MOCK_OUTPUT_CANNOT_BE_REAL_QUALITY_EVIDENCE")
        if (
            summary.get("candidate_sha256") != CANDIDATE
            or summary.get("packet_sha256") != PACKET
        ):
            raise ValueError("REAL_OUTPUT_FROZEN_BINDING_MISMATCH")
        outputs = json.loads((execution / "outcomes.json").read_bytes())
        for name in [
            "summary.json",
            "outcomes.json",
            "execution.json",
            "runtime.json",
            "owner.json",
            "calls.jsonl",
            "ledger.jsonl",
        ]:
            assets["execution/" + name] = (execution / name).read_bytes()
        for f in sorted((execution / "wire").glob("*")):
            if f.is_file() and f.suffix in {".body", ".json"}:
                assets["execution/wire/" + f.name] = f.read_bytes()

        def lines(name):
            return [json.loads(x) for x in assets["execution/" + name].splitlines()]

        requests = [assets[k] for k in sorted(assets) if k.endswith("-request.body")]
        try:
            checks = deterministic(
                outputs,
                summary,
                selected["evidence"],
                lines("calls.jsonl"),
                lines("ledger.jsonl"),
                requests,
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            checks = {
                "mechanical": "FAIL",
                "reason": "INCOMPLETE_OR_INVALID_EXECUTION_RECORD",
                "reference_oracle": oracle(),
            }
    assets["outcomes.json"] = encode(outputs)
    assets["deterministic.json"] = encode(checks)
    review = json.loads(
        (
            ROOT / "eval/phase1a-tutor-readiness-20261108/review-template.json"
        ).read_bytes()
    )
    review["reviewer"] = {
        "kind": "EXTERNAL_AI",
        "provider": None,
        "model": None,
        "separate_context": None,
        "implementation_session": None,
        "reviewed_utc": None,
    }
    review["outcomes_sha256"] = sha(assets["outcomes.json"])
    review["status"] = "NOT_RUN" if not execution else "UNRESOLVED"
    for turn in review["turns"]:
        turn["all_substantive_claims_reviewed"] = False
        for item in turn["points"]:
            item["confidence"] = "UNRESOLVED"
    manifest = {
        "review_tool_sha256": sha(Path(__file__).read_bytes()),
        "candidate_sha256": CANDIDATE,
        "packet_sha256": PACKET,
        "execution_head": state["execution_head"],
        "human_review": "HUMAN_NOT_RUN",
        "generation": "NOT_RUN" if not execution else "REAL_OUTPUTS_PRESENT",
        "files": {k: sha(v) for k, v in assets.items()},
    }
    manifest["bundle_id"] = sha(encode(manifest))
    review["bundle_id"] = manifest["bundle_id"]
    assets["review-response-template.json"] = encode(review)
    assets["manifest.json"] = encode(manifest)
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, content in assets.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(content)
    return manifest


def aggregate(directory, response=None):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_bytes())
    identity = {k: v for k, v in manifest.items() if k != "bundle_id"}
    if (
        sha(encode(identity)) != manifest["bundle_id"]
        or manifest["candidate_sha256"] != CANDIDATE
        or manifest["packet_sha256"] != PACKET
    ):
        raise ValueError("REVIEW_MANIFEST_IDENTITY_CHANGED")
    for name, expected in manifest["files"].items():
        if sha((directory / name).read_bytes()) != expected:
            raise ValueError("REVIEW_BUNDLE_CHANGED")
    result = {
        "mechanical": json.loads((directory / "deterministic.json").read_bytes())[
            "mechanical"
        ],
        "quality": "NOT_RUN" if manifest["generation"] == "NOT_RUN" else "UNRESOLVED",
        "human_review": "HUMAN_NOT_RUN",
        "expert_verified": False,
        "release_or_expansion_authorized": False,
    }
    outcomes = json.loads((directory / "outcomes.json").read_bytes())
    if not any(r.get("status") == "completed" for r in outcomes):
        result["quality"] = "NOT_RUN"
    if not response or result["quality"] == "NOT_RUN":
        return result
    review = json.loads(Path(response).read_bytes())
    if (
        review["bundle_id"] != manifest["bundle_id"]
        or review["candidate_sha256"] != CANDIDATE
        or review["packet_sha256"] != PACKET
        or review["outcomes_sha256"] != sha((directory / "outcomes.json").read_bytes())
    ):
        raise ValueError("AI_REVIEW_BINDING_MISMATCH")
    if [r["turn_key"] for r in review["turns"]] != TURN_KEYS:
        raise ValueError("ALL_ORIGINAL_POSITIONS_REQUIRED")
    statuses = []
    sources = {
        e["evidence_id"]: e["text"]
        for e in json.loads((directory / "course-evidence.json").read_bytes())[
            "evidence"
        ]
    }
    rows = {r["turn_key"]: r for r in outcomes}
    for turn in review["turns"]:
        if [p["id"] for p in turn["points"]] != POINTS[turn["turn_key"]]:
            raise ValueError("ALL_ORIGINAL_POINTS_REQUIRED")
        if (
            not turn["claims"]
            or turn.get("all_substantive_claims_reviewed") is not True
        ):
            statuses.append("UNRESOLVED")
        for item in turn["points"] + turn["claims"]:
            if item["status"] not in {"PASS", "FAIL", "UNRESOLVED", "NOT_RUN"}:
                raise ValueError("INVALID_REVIEW_STATUS")
            if item["status"] in {"PASS", "FAIL"} and (
                not item["reason"] or not item["evidence"]
            ):
                raise ValueError("REVIEW_REASON_AND_EVIDENCE_REQUIRED")
            if item["status"] in {"PASS", "FAIL"}:
                for link in item["evidence"]:
                    field = link.get("answer_field")
                    body = (
                        rows[turn["turn_key"]].get(field)
                        if field in {"answer", "evaluation"}
                        else None
                    )
                    quote = link.get("answer_quote")
                    whole = link.get("whole_field_sha256")
                    bound_answer = isinstance(body, str) and (
                        (isinstance(quote, str) and quote and quote in body)
                        or whole == sha(body.encode())
                    )
                    source = sources.get(link.get("evidence_id"))
                    source_quote = link.get("source_quote")
                    if (
                        not bound_answer
                        or not isinstance(source, str)
                        or not isinstance(source_quote, str)
                        or not source_quote
                        or source_quote not in source
                    ):
                        raise ValueError(
                            "AI_REVIEW_QUOTATIONS_NOT_BOUND_TO_ACTUAL_ANSWER_AND_SOURCE"
                        )
            statuses.append(
                "UNRESOLVED"
                if item["status"] == "PASS" and item.get("confidence") != "HIGH"
                else item["status"]
            )
    who = review["reviewer"]
    try:
        reviewed = datetime.fromisoformat(who["reviewed_utc"])
        timestamp_valid = reviewed.tzinfo is not None and reviewed <= datetime.now(
            timezone.utc
        )
    except (TypeError, ValueError):
        timestamp_valid = False
    cross_review = (
        who["kind"] == "EXTERNAL_AI"
        and who["provider"]
        and who["model"]
        and who["separate_context"] is True
        and who["implementation_session"] is False
        and timestamp_valid
    )
    if "FAIL" in statuses:
        result["quality"] = "FAIL"
    elif (
        cross_review
        and result["mechanical"] == "PASS"
        and all(s == "PASS" for s in statuses)
    ):
        result["quality"] = "AI_REVIEW_PASS"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--export", type=Path)
    parser.add_argument("--execution", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--response", type=Path)
    args = parser.parse_args()
    if args.export:
        result = export(args.candidate_root, args.export, args.execution)
        print(
            json.dumps(
                {
                    "bundle_id": result["bundle_id"],
                    "generation": result["generation"],
                    "human_review": "HUMAN_NOT_RUN",
                    "automatic_ai_calls": 0,
                }
            )
        )
        return 0
    result = aggregate(args.bundle, args.response)
    print(json.dumps(result, indent=2))
    return 0 if result["quality"] == "AI_REVIEW_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
