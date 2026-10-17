"""Recompute saved measurements without any API calls or source-system writes."""

import hashlib
import json
import math

from coverage_asr import summarize_coverage
from score import REPORT, records, summarize, token_cost


def main():
    directory = REPORT / "batch-v2"
    recomputed = summarize(directory)
    saved = json.loads((REPORT / "summary.json").read_text())
    assert recomputed == saved, (
        "Saved report differs from actual raw-record recomputation"
    )
    assert recomputed["lecture_count"] == 5
    assert recomputed["unique_audio_hours"] >= 3
    assert recomputed["finished_trials"] == 10 and not recomputed["pending_trials"]
    assert all(group["n"] == 2 for group in recomputed["per_lecture"].values())
    freeze = json.loads((directory / "freeze-v2.json").read_text())
    for name, digest in freeze["files"].items():
        assert hashlib.sha256((REPORT / name).read_bytes()).hexdigest() == digest, name
    driver = json.loads((directory / "executed-driver-identity.json").read_text())
    assert (
        hashlib.sha256((REPORT / "run-final.py").read_bytes()).hexdigest()
        == driver["sha256"]
    )
    asr = records(directory / "http-calls.jsonl")
    known = [token_cost(row.get("usage")) for row in asr]
    assert math.isclose(
        sum(v for v in known if v is not None),
        recomputed["known_successful_asr_call_fee_cny"],
        abs_tol=1e-10,
    )
    assert sum(v is None for v in known) == recomputed["asr_usage_missing_calls"]
    values = {
        key: recomputed[key]
        for key in (
            "lecture_count",
            "unique_audio_hours",
            "finished_trials",
            "time_range_utc",
            "cer_scored_trials",
            "reference_characters",
            "edit_distance",
            "weighted_cer",
            "processing_ms",
            "successful_index_ready_ms",
            "asr_list_price_cny",
            "known_successful_asr_call_fee_cny",
            "asr_usage_missing_calls",
            "asr_failed_calls",
            "asr_chunk_retries",
            "task_status_counts",
            "translation_status_counts",
        )
    }
    coverage = summarize_coverage(recomputed)
    assert coverage == json.loads((REPORT / "coverage-asr.json").read_text())
    values["completed_transcription_availability"] = coverage
    print(json.dumps(values, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
