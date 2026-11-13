"""Read-only CER, latency and actual-usage accounting for frozen ASR trials."""

import argparse
import collections
import hashlib
import html
import json
import re
import statistics
import unicodedata
from pathlib import Path

from num2words import num2words
from rapidfuzz.distance import Levenshtein

REPORT = Path(__file__).resolve().parent
ROOT = REPORT.parents[1]


def normalize(text):
    text = unicodedata.normalize("NFKC", html.unescape(text))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"(?m)^\s*[A-Z][A-Z .'-]{2,50}:\s*", "", text)
    text = text.casefold()
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    text = re.sub(
        r"(?<!\w)\d+(?:\.\d+)?(?!\w)", lambda m: num2words(m[0], lang="en"), text
    )
    return "".join(c for c in text if unicodedata.category(c)[0] in {"L", "N"})


def caption_text(path):
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    texts, in_cue = [], False
    for line in lines:
        if "-->" in line:
            in_cue = True
        elif not line.strip():
            in_cue = False
        elif in_cue:
            texts.append(line)
    if not texts:
        raise ValueError("Missing reference cues")
    return "\n".join(texts)


def stats(values):
    return {
        "n": len(values),
        "mean": statistics.mean(values) if values else None,
        "sample_sd": statistics.stdev(values) if len(values) > 1 else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def token_cost(usage):
    if not usage or any(
        type(usage.get(k)) is not int or usage[k] < 0
        for k in ("input_tokens", "output_tokens")
    ):
        return None
    return (usage["input_tokens"] * 0.8 + usage["output_tokens"] * 2.7) / 1_000_000


def records(path):
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )


def summarize(directory):
    manifest = json.loads((REPORT / "assets.lock.json").read_text())
    sources = {s["id"]: s for s in manifest["sources"]}
    references = {}
    for key, source in sources.items():
        path = ROOT / source["captions_file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["captions_sha256"]:
            raise ValueError("Reference hash mismatch")
        references[key] = normalize(caption_text(path))
    events = records(directory / "trials.jsonl")
    finished = [r for r in events if r["phase"] == "finished"]
    if len({r["trial_id"] for r in finished}) != len(finished):
        raise ValueError("Duplicate finished trial")
    calls = records(directory / "http-calls.jsonl") + records(
        directory / "index-http-calls.jsonl"
    )
    stages = records(directory / "pipeline-events.jsonl")
    computed = []
    for row in finished:
        prediction = json.loads((ROOT / row["prediction_file"]).read_text())
        reference = references[row["source_id"]]
        hypothesis = prediction.get("sourceFullText")
        own = [
            c
            for c in calls
            if (c["kind"] == "asr" and c["trial_id"] == row["trial_id"])
            or (c["kind"] == "index" and c.get("course_id") == row["task_id"])
        ]
        asr = [c for c in own if c["kind"] == "asr"]
        index = [c for c in own if c["kind"] == "index"]
        distances = (
            Levenshtein.distance(reference, normalize(hypothesis))
            if isinstance(hypothesis, str)
            else None
        )
        prices = [token_cost(c.get("usage")) for c in asr]
        cost = sum(prices) if asr and all(p is not None for p in prices) else None
        ai = prediction.get("aiCallRecords") or []
        item = {
            "trial_id": row["trial_id"],
            "source_id": row["source_id"],
            "task_id": row["task_id"],
            "status": row["task"]["status"],
            "translation_status": prediction.get("translationStatus"),
            "index_status": row.get("index_status"),
            "submitted_at_utc": row["submitted_at_utc"],
            "finished_at_utc": row["finished_at_utc"],
            "reference_characters": len(reference),
            "edit_distance": distances,
            "cer": distances / len(reference) if distances is not None else None,
            "task_terminal_ms": row["task_terminal_ms"],
            "processing_to_index_ms": row["processing_to_index_ms"],
            "successful_index_ready_ms": row["processing_to_index_ms"]
            if (row.get("index_status") or {}).get("status") == "READY"
            else None,
            "latency_interpretation": "index_ready"
            if (row.get("index_status") or {}).get("status") == "READY"
            else "observed_failure_or_unready_stop_not_success_latency",
            "upload_ms": row["upload_ms"],
            "upload_inclusive_ms": row["upload_ms"] + row["processing_to_index_ms"],
            "index_wait_ms": row["processing_to_index_ms"] - row["task_terminal_ms"]
            if row.get("index_status")
            else None,
            "index_http_ms": sum(c["upstream_elapsed_ms"] for c in index)
            if index
            else None,
            "asr_http_calls": len(asr),
            "asr_failed_calls": sum(c["http_status"] != 200 for c in asr),
            "asr_tokens": {
                k: sum((c.get("usage") or {}).get(k, 0) for c in asr)
                for k in ("input_tokens", "output_tokens")
            },
            "asr_usage_missing_calls": sum(p is None for p in prices),
            "asr_token_measurement": "Observed responses only; missing-request tokens unavailable",
            "asr_usage_duration_seconds": sum(
                (c.get("usage") or {}).get("duration", 0) for c in asr
            ),
            "asr_list_price_cny": cost,
            "known_successful_asr_call_fee_cny": sum(
                p for p in prices if p is not None
            ),
            "local_llm_external_api_fee_cny": 0,
            "local_embedding_external_api_fee_cny": 0,
            "machine_cost_cny": None,
            "task_retry_count": row["task"].get("retryCount"),
            "asr_chunk_retries": sum(
                s["event"] == "asr_retry"
                for s in stages
                if s["task_id"] == row["task_id"]
            ),
            "translation_batches_started": sum(
                s["event"] == "translation_batch_started"
                for s in stages
                if s["task_id"] == row["task_id"]
            ),
            "translation_batches_failed": sum(
                s["event"] == "translation_batch_failed"
                for s in stages
                if s["task_id"] == row["task_id"]
            ),
            "translation_semantic_retries": sum(
                s["event"] == "translation_semantic_retry"
                for s in stages
                if s["task_id"] == row["task_id"]
            ),
            "translation_provider_retry_count": next(
                (
                    a["retryCount"]
                    for a in ai
                    if a.get("stage") == "TRANSLATION"
                    and a.get("retryCount") is not None
                ),
                None,
            ),
            "model_tokens": {
                k: sum(
                    a[k]
                    for a in ai
                    if a.get("callType") == "LLM" and a.get(k) is not None
                )
                if any(a.get("callType") == "LLM" and a.get(k) is not None for a in ai)
                else None
                for k in ("promptTokens", "completionTokens")
            },
            "model_token_samples": {
                k: sum(a.get("callType") == "LLM" and a.get(k) is not None for a in ai)
                for k in ("promptTokens", "completionTokens")
            },
            "model_usage_missing_records": sum(
                a.get("promptTokens") is None or a.get("completionTokens") is None
                for a in ai
                if a.get("callType") == "LLM"
            ),
            "stage_ms": {
                s["step"]: s["duration_ms"]
                for s in stages
                if s["task_id"] == row["task_id"]
                and s["event"] in {"completed", "failed"}
            },
            "stage_outcomes": {
                s["step"]: s["event"]
                for s in stages
                if s["task_id"] == row["task_id"]
                and s["event"] in {"completed", "failed"}
            },
            "pipeline_failed_steps": sum(
                s["event"] == "failed" for s in stages if s["task_id"] == row["task_id"]
            ),
            "ai_call_records": ai,
        }
        computed.append(item)
    grouped = {}
    for source_id in sources:
        group = [r for r in computed if r["source_id"] == source_id]
        grouped[source_id] = {
            "n": len(group),
            "cer": stats([r["cer"] for r in group if r["cer"] is not None]),
            "processing_ms": stats([r["processing_to_index_ms"] for r in group]),
            "stage_ms": {
                step: stats(
                    [r["stage_ms"][step] for r in group if step in r["stage_ms"]]
                )
                for step in sorted({s for r in group for s in r["stage_ms"]})
            },
            "index_http_ms": stats(
                [r["index_http_ms"] for r in group if r["index_http_ms"] is not None]
            ),
            "asr_list_price_cny": stats(
                [
                    r["asr_list_price_cny"]
                    for r in group
                    if r["asr_list_price_cny"] is not None
                ]
            ),
        }
    scored = [r for r in computed if r["edit_distance"] is not None]
    return {
        "lecture_count": len(sources),
        "unique_audio_hours": manifest["total_duration_ms"] / 3_600_000,
        "finished_trials": len(computed),
        "time_range_utc": {
            "from": min((r["submitted_at_utc"] for r in computed), default=None),
            "to": max((r["finished_at_utc"] for r in computed), default=None),
        },
        "pending_trials": sorted(
            {r["trial_id"] for r in events if r["phase"] == "submitted"}
            - {r["trial_id"] for r in finished}
        ),
        "cer_scored_trials": len(scored),
        "weighted_cer": sum(r["edit_distance"] for r in scored)
        / sum(r["reference_characters"] for r in scored)
        if scored
        else None,
        "reference_characters": sum(r["reference_characters"] for r in scored),
        "edit_distance": sum(r["edit_distance"] for r in scored),
        "processing_ms": stats([r["processing_to_index_ms"] for r in computed]),
        "stage_ms": {
            step: stats(
                [r["stage_ms"][step] for r in computed if step in r["stage_ms"]]
            )
            for step in sorted({s for r in computed for s in r["stage_ms"]})
        },
        "index_http_ms": stats(
            [r["index_http_ms"] for r in computed if r["index_http_ms"] is not None]
        ),
        "successful_index_ready_ms": stats(
            [
                r["successful_index_ready_ms"]
                for r in computed
                if r["successful_index_ready_ms"] is not None
            ]
        ),
        "asr_list_price_cny": stats(
            [
                r["asr_list_price_cny"]
                for r in computed
                if r["asr_list_price_cny"] is not None
            ]
        ),
        "known_trial_api_fee_cny": sum(
            r["asr_list_price_cny"]
            for r in computed
            if r["asr_list_price_cny"] is not None
        ),
        "known_successful_asr_call_fee_cny": sum(
            r["known_successful_asr_call_fee_cny"] for r in computed
        ),
        "asr_usage_missing_calls": sum(r["asr_usage_missing_calls"] for r in computed),
        "asr_failed_calls": sum(r["asr_failed_calls"] for r in computed),
        "asr_chunk_retries": sum(r["asr_chunk_retries"] for r in computed),
        "task_status_counts": dict(collections.Counter(r["status"] for r in computed)),
        "translation_status_counts": dict(
            collections.Counter(r["translation_status"] for r in computed)
        ),
        "per_lecture": grouped,
        "trials": computed,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=REPORT / "batch-v2")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = summarize(args.batch)
    output = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        with args.output.open("x") as stream:
            stream.write(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
