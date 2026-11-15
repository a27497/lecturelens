"""Offline aggregation. Missing usage/stages stay null; sample SD uses ddof=1."""

import collections
import json
import statistics
from datetime import datetime

from support import PUBLIC, ROOT


def stats(values):
    values = [x for x in values if x is not None]
    return {
        "n": len(values),
        "mean": statistics.mean(values) if values else None,
        "sample_sd": statistics.stdev(values) if len(values) > 1 else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def load(path):
    return json.loads(path.read_text())


def aggregate():
    path = PUBLIC / "trials.jsonl"
    events = (
        [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    )
    trials = []
    price = load(PUBLIC / "pricing.json")
    for row in events:
        if row["phase"] != "finished":
            continue
        trial = row["trial_id"]
        result = load(PUBLIC / "results" / f"{trial}.json")
        calls = result["aiCallRecords"]
        steps = load(PUBLIC / "events" / f"{trial}.json")
        translations = [c for c in calls if c["stage"] == "TRANSLATION"]
        call = translations[0] if translations else {}
        costs = None
        if call.get("status") == "SUCCEEDED" and all(
            type(call.get(k)) is int for k in ["promptTokens", "completionTokens"]
        ):
            # Every batch in a trial must stay in one tariff interval to price
            # aggregate tokens without inventing per-request cache/time data.
            start = datetime.fromisoformat(row["created_utc"])
            end = datetime.fromisoformat(row["finished_utc"])

            def peak(dt):
                return dt.weekday() < 5 and (1 <= dt.hour < 4 or 6 <= dt.hour < 10)

            tariff = "peak" if peak(start) else "off_peak"
            assert peak(start) == peak(end), (
                "Trial crossed tariff boundary; per-call pricing required"
            )
            rate = price[tariff]
            a = call["promptTokens"]
            b = call["completionTokens"]
            costs = {
                "currency": "USD",
                "tariff": tariff,
                "lower_all_input_cache_hit": (
                    a * rate["input_cache_hit"] + b * rate["output"]
                )
                / 1e6,
                "upper_all_input_cache_miss": (
                    a * rate["input_cache_miss"] + b * rate["output"]
                )
                / 1e6,
                "exact_bill": None,
                "reason": "Java does not persist prompt cache-hit/miss split; this is a list-price interval, not a bill.",
            }
        stages = {}
        for step in steps:
            if step["event"] in ["completed", "failed"]:
                stages[step["step"]] = {
                    "event": step["event"],
                    "seconds": step["duration_ms"] / 1000,
                }
        batches = [
            s for s in steps if s["event"] == "llm_aligned_batch_translation_completed"
        ]
        retries = [s for s in steps if s["event"] == "asr_retry"]
        trials.append(
            {
                "trial_id": trial,
                "task_id": row["task_id"],
                "source_id": row["source_id"],
                "repeat": row["repeat"],
                "status": row["measurement_status"],
                "db_status": row["task"]["status"],
                "failure_stage": row["task"].get("currentStage"),
                "failure_reason": row["task"].get("errorMessage"),
                "config_version": row["config_version"],
                "upload_seconds": row["upload_ms"] / 1000,
                "task_terminal_seconds": row["task_terminal_ms"] / 1000,
                "processing_to_index_seconds": row["processing_to_index_ms"] / 1000,
                "index_status": row["index_status"],
                "translation_status": result["translationStatus"],
                "source_segment_count": result["source_segment_count"],
                "translated_segment_count": call.get("outputUnits")
                if call.get("status") == "SUCCEEDED"
                else None,
                "translation_batch_count": call.get("batchCount"),
                "translation_retries": call.get("retryCount"),
                "asr_chunk_retry_events": len(retries),
                "task_retry_count": row["task"].get("retryCount"),
                "deepseek_prompt_tokens": call.get("promptTokens"),
                "deepseek_completion_tokens": call.get("completionTokens"),
                "deepseek_total_tokens": call.get("totalTokens"),
                "completed_batch_total_tokens": sum(
                    x.get("totalTokens") or 0 for x in batches
                ),
                "failed_call_usage_available": False
                if call.get("status") == "FAILED"
                else None,
                "usage_scope": "Whole translation stage"
                if call.get("totalTokens") is not None
                else "Only successful batch totalTokens in logs; failed call and input/output split unavailable",
                "completed_batch_count": len(batches),
                "stages": stages,
                "deepseek_list_price_usd": costs,
                "asr_fee": None,
                "asr_fee_note": "Production ASR call records do not persist billing usage; original baseline used a response tee, which is not installed/reconfigured in this run.",
            }
        )
    stage_names = sorted({name for t in trials for name in t["stages"]})

    def group(rows):
        return {
            "n": len(rows),
            "successes": sum(x["status"] == "SUCCEEDED" for x in rows),
            "success_rate": sum(x["status"] == "SUCCEEDED" for x in rows) / len(rows)
            if rows
            else None,
            "translation_successes": sum(
                x["translation_status"] == "SUCCEEDED" for x in rows
            ),
            "task_terminal_seconds": stats([x["task_terminal_seconds"] for x in rows]),
            "stage_seconds": {
                s: stats([x["stages"].get(s, {}).get("seconds") for x in rows])
                for s in stage_names
            },
            "successful_stage_seconds": {
                s: stats(
                    [
                        x["stages"][s]["seconds"]
                        for x in rows
                        if s in x["stages"] and x["stages"][s]["event"] == "completed"
                    ]
                )
                for s in stage_names
            },
            "failed_stage_seconds": {
                s: stats(
                    [
                        x["stages"][s]["seconds"]
                        for x in rows
                        if s in x["stages"] and x["stages"][s]["event"] == "failed"
                    ]
                )
                for s in stage_names
            },
            "deepseek_cost_lower_usd": stats(
                [
                    x["deepseek_list_price_usd"]["lower_all_input_cache_hit"]
                    for x in rows
                    if x["deepseek_list_price_usd"]
                ]
            ),
            "deepseek_cost_upper_usd": stats(
                [
                    x["deepseek_list_price_usd"]["upper_all_input_cache_miss"]
                    for x in rows
                    if x["deepseek_list_price_usd"]
                ]
            ),
        }

    base = load(ROOT / "eval/baseline-asr-20261015/summary.json")
    return {
        "finished_trials": len(trials),
        "submitted_trials": sum(x["phase"] == "submitted" for x in events),
        "expected_trials": 10,
        "task_status_counts": dict(collections.Counter(x["status"] for x in trials)),
        "translation_status_counts": dict(
            collections.Counter(x["translation_status"] for x in trials)
        ),
        "overall": group(trials),
        "per_lecture": {
            name: group([x for x in trials if x["source_id"] == name])
            for name in ["algorithms", "calculus", "economics", "linear", "probability"]
        },
        "deepseek_tokens": {
            k: {
                "known_sum": sum(x[k] for x in trials if x[k] is not None)
                if any(x[k] is not None for x in trials)
                else None,
                "complete_trials": sum(x[k] is not None for x in trials),
            }
            for k in [
                "deepseek_prompt_tokens",
                "deepseek_completion_tokens",
                "deepseek_total_tokens",
            ]
        },
        "usage_complete_trials": sum(
            x["deepseek_total_tokens"] is not None for x in trials
        ),
        "baseline": {
            "task_status_counts": base["task_status_counts"],
            "translation_status_counts": base["translation_status_counts"],
            "processing_ms": base["processing_ms"],
            "stage_ms": base["stage_ms"],
            "per_lecture": base["per_lecture"],
            "known_successful_asr_call_fee_cny": base[
                "known_successful_asr_call_fee_cny"
            ],
        },
        "trials": trials,
    }


if __name__ == "__main__":
    print(json.dumps(aggregate(), ensure_ascii=False, indent=2))
