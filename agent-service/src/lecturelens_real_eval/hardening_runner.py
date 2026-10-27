"""Read-only public snapshot evaluation through the frozen flashcard graph."""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import time
import uuid
from dataclasses import replace
from pathlib import Path

import httpx

from lecturelens_agent.study.acceptance_cost import verify_development_agent
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyStore

from .channel import usd_to_nano
from .hardening_channel import (
    DEFAULT_LEDGER,
    PRICES,
    Channel,
    EvalError,
    Ledger,
    RealPolicy,
)
from .runner import (
    GraphAdapter,
    SnapshotAuthority,
    citation_ids,
)
from .runner import (
    fake_transport as historical_fake_transport,
)
from .runner import (
    review_cards as review_once,
)
from .runner import (
    verify_inputs as verify_historical_inputs,
)

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "eval/p7-hardening"
SNAPSHOT = ROOT / "eval/p7-real/snapshot.json"


def verify_inputs():
    # Check the prior round in full, including its evaluator code and candidate.
    verify_historical_inputs()
    verify_development_agent()
    frozen = json.loads((DATA / "frozen.json").read_bytes())
    for path, digest in frozen["files"].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
            raise EvalError("REAL_EVAL_FROZEN_INPUT_CHANGED")
    identity = hashlib.sha256(json.dumps(frozen["files"], sort_keys=True).encode()).hexdigest()
    if identity != frozen["candidate_sha256"]:
        raise EvalError("REAL_EVAL_FROZEN_INPUT_CHANGED")
    tasks = json.loads((DATA / "tasks.json").read_bytes())["tasks"]
    snapshot = json.loads(SNAPSHOT.read_bytes())
    thresholds = json.loads((DATA / "thresholds.json").read_bytes())
    originals = json.loads((ROOT / "eval/p7-real/tasks.json").read_bytes())["tasks"]
    confusables = [t for t in tasks if t["kind"] == "confusable"]
    if (
        tasks[:24] != originals
        or len(tasks) != thresholds["task_count"]
        or len({t["task_id"] for t in tasks}) != len(tasks)
        or len(confusables) != thresholds["confusable_count"]
        or len(confusables) < 8
        or len({t["lecture_id"] for t in confusables}) < 6
        or any(t not in confusables for t in tasks[24:])
    ):
        raise EvalError("REAL_EVAL_TASK_SET_INVALID")
    for task in confusables:
        terms = task.get("evidence_absence_check", [])
        text = "\n".join(e["text"] for e in snapshot["lectures"][task["lecture_id"]]["evidence"])
        if (
            not task["expected_stop"]
            or not task.get("concept")
            or not terms
            or any(
                not isinstance(term, str) or not term.strip() or term.lower() in text.lower()
                for term in terms
            )
        ):
            raise EvalError("REAL_EVAL_ABSENCE_CHECK_FAILED")
    return tasks, snapshot, thresholds


def candidate_identity():
    return json.loads((DATA / "frozen.json").read_bytes())["candidate_sha256"]


def fake_transport():
    # Labels are used only by the fake response fixture, never by search or live prompts.
    tasks = json.loads((DATA / "tasks.json").read_bytes())["tasks"]
    negatives = {t["goal"] for t in tasks if t["expected_stop"]}
    historical = historical_fake_transport()

    def respond(request):
        body = json.loads(json.loads(request.content)["messages"][-1]["content"])
        if body.get("history") and body.get("goal") in negatives:
            return httpx.Response(
                200,
                json={
                    "usage": {"prompt_tokens": 100, "completion_tokens": 100},
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "tool_calls": [
                                    {
                                        "type": "function",
                                        "function": {
                                            "name": "stop_cards",
                                            "arguments": json.dumps(
                                                {
                                                    "reason": "Mock fixture: no supporting evidence for the requested concept."
                                                }
                                            ),
                                        },
                                    }
                                ]
                            },
                        }
                    ],
                },
            )
        return historical.handle_request(request)

    return httpx.MockTransport(respond)


def card_key(task_id, index):
    return f"{task_id}:{index}"


def review_cards(channel, cards, seed=20261028):
    passes = []
    for number in (1, 2):
        order = list(range(len(cards)))
        if number == 2:
            random.Random(seed).shuffle(order)
            # Ensure a changed order whenever multiple cards make it possible.
            if len(order) > 1 and order == list(range(len(cards))):
                order = order[1:] + order[:1]
        try:
            result = review_once(channel, [cards[i] for i in order])
            checks = [{**check, "index": order[check["index"]]} for check in result["checks"]]
            passes.append({"pass": number, "order": order, "checks": checks, "usage": result["usage"]})
        except Exception as exc:  # noqa: BLE001 -- never persist raw transport/ledger details
            code = str(exc) if isinstance(exc, EvalError) else "REAL_EVAL_CHANNEL_OR_LEDGER_FAILED"
            passes.append({"pass": number, "order": order, "checks": [], "error": code})
            if code != "REAL_EVAL_PROTOCOL_FAILURE":
                break
    by_pass = [{c["index"]: c["verdict"] for c in p["checks"]} for p in passes]
    final = []
    for i in range(len(cards)):
        verdicts = [p.get(i) for p in by_pass]
        verdict = verdicts[0] if len(verdicts) == 2 and verdicts[0] == verdicts[1] else "unclear"
        final.append({"index": i, "verdict": verdict or "unclear"})
    errors = [p["error"] for p in passes if "error" in p]
    # A later channel/ledger failure must not be hidden by an earlier schema miss.
    fatal = next((e for e in errors if e != "REAL_EVAL_PROTOCOL_FAILURE"), None)
    return {"checks": final, "passes": passes, **({"error": fatal or errors[0]} if errors else {})}


def normalized(text):
    return " ".join(re.findall(r"\w+", text.casefold()))


def near_duplicate_pairs(cards):
    pairs = []
    for i, left in enumerate(cards):
        for j in range(i + 1, len(cards)):
            right = cards[j]
            if {e["evidence_id"] for e in left["citations"]} != {
                e["evidence_id"] for e in right["citations"]
            }:
                continue
            a = set(normalized(left["front"] + " " + left["back"]).split())
            b = set(normalized(right["front"] + " " + right["back"]).split())
            similarity = len(a & b) / len(a | b) if a | b else 0.0
            if normalized(left["back"]) == normalized(right["back"]) or similarity >= 0.8:
                pairs.append((i, j))
    return pairs


def append(path, value):
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(value, ensure_ascii=False) + "\n")
        file.flush()
        os.fsync(file.fileno())


def summarize(generations, reviews, accounting, thresholds, fatal, live):
    cards = [c for g in generations for c in g["cards"]]
    by_task = {r["task_id"]: r for r in reviews}
    verdicts, agreements = [], []
    review_failures = 0
    for generation in generations:
        review = by_task.get(generation["task"]["task_id"], {})
        passes = review.get("passes", [])
        lookups = [{c["index"]: c["verdict"] for c in p["checks"]} for p in passes]
        if review.get("error"):
            review_failures += 1
        for i in range(len(generation["cards"])):
            observations = [p.get(i) for p in lookups]
            complete = len(observations) == 2 and None not in observations
            agreements.append(complete and observations[0] == observations[1])
            # Recompute from observations: a saved aggregate must never inflate support.
            verdicts.append(observations[0] if complete and observations[0] == observations[1] else "unclear")
    pairs = near_duplicate_pairs(cards)
    pair_agreement = sum(verdicts[i] == verdicts[j] for i, j in pairs) / len(pairs) if pairs else None
    offtopic = [g for g in generations if g["task"]["expected_stop"] and g["task"]["kind"] != "confusable"]
    confusable = [g for g in generations if g["task"]["kind"] == "confusable"]
    positives = [g for g in generations if not g["task"]["expected_stop"]]

    def correct(rows):
        return sum(g["stopped"] and not g["cards"] and not g["protocol_failure"] for g in rows)

    latencies = sorted(g["latency_s"] for g in generations)
    citation_count = sum(
        g.get("citation_count", sum(len(c["citations"]) for c in g["cards"])) for g in generations
    )
    valid_count = sum(
        g.get("valid_citation_count", sum(len(c["citations"]) for c in g["cards"])) for g in generations
    )
    values = {
        "citation_valid_rate": valid_count / citation_count if citation_count else 1.0,
        "source_supported_rate": sum(v == "supported" for v in verdicts) / len(cards) if cards else 0.0,
        "offtopic_correct_stop_rate": correct(offtopic) / thresholds["offtopic_count"],
        "confusable_correct_stop_rate": correct(confusable) / thresholds["confusable_count"],
        "false_stop_rate": sum(g["stopped"] and not g["cards"] for g in positives)
        / (thresholds["task_count"] - thresholds["offtopic_count"] - thresholds["confusable_count"]),
        "review_self_agreement": sum(agreements) / len(cards) if cards else 0.0,
        "near_duplicate_pairs": len(pairs),
        "near_duplicate_agreement": pair_agreement,
        "protocol_failure_rate": sum(
            g["protocol_failure"] or bool(by_task.get(g["task"]["task_id"], {}).get("error"))
            for g in generations
        )
        / thresholds["task_count"],
        "p95_generation_latency_s": latencies[math.ceil(len(latencies) * 0.95) - 1] if latencies else None,
        "max_calls": accounting["calls"],
        "max_usd": accounting["nano_usd"] / 1e9 if accounting["nano_usd"] is not None else None,
    }
    minimum_gates = {"source_supported_rate", "offtopic_correct_stop_rate", "review_self_agreement"}
    gates = {}
    for key, value in values.items():
        if key in {"near_duplicate_pairs", "near_duplicate_agreement", "confusable_correct_stop_rate"}:
            continue
        gates[key] = value is not None and (
            value == thresholds[key]
            if key == "citation_valid_rate"
            else value >= thresholds[key]
            if key in minimum_gates
            else value <= thresholds[key]
        )
    required_confusable = math.floor(
        thresholds["confusable_correct_stop_rate"] * thresholds["confusable_count"]
    )
    gates["confusable_correct_stop_rate"] = correct(confusable) >= required_confusable
    gates["near_duplicate_agreement"] = (
        "insufficient_n"
        if len(pairs) < thresholds["near_duplicate_min_pairs"]
        else pair_agreement >= thresholds["near_duplicate_agreement"]
    )
    gates["completed_tasks"] = len(generations) == thresholds["task_count"]
    gates["ledger_consistent"] = accounting["calls"] is not None and (not fatal or "LEDGER" not in fatal)
    fatal = fatal or accounting.get("blocked")
    if valid_count < citation_count:
        fatal = "REAL_EVAL_CITATION_FABRICATED"
    passed = all(value is True or value == "insufficient_n" for value in gates.values())
    return {
        "verdict": "FAIL" if fatal else "PASS" if passed else "PARTIAL",
        "mode": "live" if live else "mock",
        "quality_status": "REAL_MODEL_EVALUATION" if live else "NOT_RUN_MOCK_MECHANICS_ONLY",
        "values": values,
        "gates": gates,
        "thresholds": thresholds,
        "completed_tasks": len(generations),
        "card_count": len(cards),
        "calls": accounting["calls"],
        "cost_usd": values["max_usd"],
        "accounting": accounting,
        "fatal": fatal,
        "review_failures": review_failures,
        "near_duplicate_n": len(pairs),
        "review_self_agreement_n": len(cards),
        "offtopic_n": len(offtopic),
        "confusable_n": len(confusable),
        "positive_n": len(positives),
        "confusable_required_correct": required_confusable,
        "dropped_tool_calls": sum(g.get("dropped_tool_calls", 0) for g in generations)
        + sum(r.get("dropped_tool_calls", 0) for r in reviews),
    }


def run_evaluation(dsn, ledger_path, run_id, policy, *, transport=None, output_root=None):
    tasks, snapshot, thresholds = verify_inputs()
    policy = replace(policy, candidate_sha256=candidate_identity())
    ledger = Ledger(dsn, ledger_path, run_id, policy)
    directory = (Path(output_root) if output_root else ROOT / ".data/p7-hardening") / run_id
    directory.mkdir(parents=True, exist_ok=False)
    generations, reviews, fatal = [], [], None
    accounting = {"calls": 0, "nano_usd": 0, "pending": 0, "blocked": None}
    runtime = None
    try:
        ledger.install()
        accounting = ledger.check()
        print(
            json.dumps(
                {
                    "mode": "live" if policy.live else "mock",
                    "run_id": run_id,
                    "per_model_worst_reservation_usd": {
                        m: (65536 * p[0] + policy.max_tokens * p[1]) / 1e9 for m, p in PRICES.items()
                    },
                    "max_calls": policy.max_calls,
                    "max_usd": policy.max_nano_usd / 1e9,
                    "ledger_current": accounting,
                }
            ),
            flush=True,
        )
        channel = Channel(
            ledger,
            transport=transport if transport is not None else None if policy.live else fake_transport(),
        )
        authority = SnapshotAuthority(snapshot)
        adapter = GraphAdapter(channel, authority)
        store = StudyStore(ledger.dsn)
        runtime = StudyRuntime(store, authority, adapter, seconds=70)
        runtime.initialize()
        for task in tasks:
            scope = {
                "owner_id": 700027,
                "course_id": f"p7-real-{hashlib.sha256(run_id.encode()).hexdigest()[:24]}-{task['task_id']}",
                "revision": 1,
            }
            authority.register(scope, task["lecture_id"])
            session = store.command(
                StudyCommand(**scope, operation="CREATE_SESSION", request_key="session"), "mock"
            )
            scope["session_id"] = session["session_id"]
            adapter.start(scope)
            command = store.command(
                StudyCommand(**scope, operation="GENERATE_CARDS", request_key="generate", goal=task["goal"]),
                "mock",
            )
            with ledger.connect() as conn:
                first_sequence = conn.execute(
                    "SELECT COALESCE(max(sequence),0) AS n FROM p7_real_event WHERE run_id=%s", (run_id,)
                ).fetchone()["n"]
            dropped_before = channel.dropped_tool_calls
            started = time.monotonic()
            runtime.execute(next(r for r in store.candidates() if r["run_id"] == command["run"]["run_id"]))
            latency = time.monotonic() - started
            result = store.command(StudyCommand(**scope, operation="DUE_CARDS"), "mock")
            generation = result["generation"]
            cards = [{k: c[k] for k in ("front", "back", "citations")} for c in result["cards"]]
            canonical = {e["evidence_id"]: e for e in authority.rows(scope)}
            for card in cards:
                card["citations"] = [canonical[e["evidence_id"]] for e in card["citations"]]
            accounting = ledger.check()
            code = generation.get("error_code")
            if accounting["blocked"]:
                fatal = accounting["blocked"]
            elif (
                code
                and code.startswith("REAL_EVAL_")
                and code not in {"REAL_EVAL_GENERATION_CALL_LIMIT", "REAL_EVAL_PROTOCOL_FAILURE"}
            ):
                fatal = code
            row = {
                "task": task,
                "cards": cards,
                "latency_s": latency,
                "usage": [],
                "stopped": generation["status"] == "succeeded" and adapter.last_action == "stop_cards",
                "protocol_failure": generation["status"] != "succeeded",
                "error": code,
                "model_calls": adapter.task_calls,
                "proposals": adapter.proposals,
                "study_run_id": command["run"]["run_id"],
                "dropped_tool_calls": channel.dropped_tool_calls - dropped_before,
            }
            # Usage is read from the independent ledger, not private model traces.
            with ledger.connect() as conn:
                events = [
                    r["record"]
                    for r in conn.execute(
                        "SELECT record FROM p7_real_event WHERE run_id=%s AND sequence>%s ORDER BY sequence",
                        (run_id, first_sequence),
                    )
                ]
            row["usage"] = [e["usage"] for e in events if e["state"] != "reserved"]
            proposed_ids = [
                eid
                for p in adapter.proposals
                if p["name"] == "create_evidence_cards"
                for eid in citation_ids(p["arguments"])
            ]
            row["citation_count"] = len(proposed_ids)
            row["valid_citation_count"] = sum(
                isinstance(eid, str) and eid in canonical for eid in proposed_ids
            )
            generations.append(row)
            append(directory / "generations.jsonl", row)
            if fatal:
                break
            dropped_before = channel.dropped_tool_calls
            review = {
                "task_id": task["task_id"],
                **review_cards(channel, cards, thresholds["review_shuffle_seed"]),
            }
            review["dropped_tool_calls"] = channel.dropped_tool_calls - dropped_before
            reviews.append(review)
            append(directory / "reviews.jsonl", review)
            if review.get("error") and review["error"] != "REAL_EVAL_PROTOCOL_FAILURE":
                fatal = review["error"]
                fatal = ledger.check()["blocked"] or fatal
            if fatal:
                break
        accounting = ledger.check()
    except Exception:  # noqa: BLE001 -- preserve failed trial without logging provider details
        fatal = fatal or "REAL_EVAL_CHANNEL_OR_LEDGER_FAILED"
        # Preserve all prior accounting; never turn an unreadable ledger into zero cost.
        try:
            accounting = ledger.check()
        except Exception:  # noqa: BLE001 -- preserve failed trial without logging provider details
            accounting = {"calls": None, "nano_usd": None, "pending": None, "blocked": "UNKNOWN"}
    finally:
        if runtime:
            runtime.close()
    for name in ("generations.jsonl", "reviews.jsonl"):
        (directory / name).touch(exist_ok=True)
    summary = summarize(generations, reviews, accounting, thresholds, fatal, policy.live)
    summary["run_id"] = run_id
    summary["candidate_sha256"] = policy.candidate_sha256
    summary["frozen_sha256"] = hashlib.sha256((DATA / "frozen.json").read_bytes()).hexdigest()
    (directory / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    spec = importlib.util.spec_from_file_location("p7_sample", DATA / "sample.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.sample(directory, thresholds["sample_seed"])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--ledger", default=DEFAULT_LEDGER)
    parser.add_argument("--max-calls", type=int, default=220)
    parser.add_argument("--max-usd", default="0.60")
    parser.add_argument("--run-id", default="p7-" + uuid.uuid4().hex)
    parser.add_argument("--check-ledger", action="store_true")
    args = parser.parse_args()
    try:
        policy = RealPolicy(live=args.live, max_calls=args.max_calls, max_nano_usd=usd_to_nano(args.max_usd))
        policy.validate()
        verify_inputs()
        policy = replace(policy, candidate_sha256=candidate_identity())
        if args.check_ledger:
            result = Ledger(args.dsn, args.ledger, args.run_id, policy).check()
        else:
            result = run_evaluation(args.dsn, args.ledger, args.run_id, policy)
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result.get("verdict") == "FAIL" else 0
    except Exception:  # noqa: BLE001 -- preserve failed trial without logging provider details
        print('{"error":"REAL_EVAL_PREFLIGHT_FAILED"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
