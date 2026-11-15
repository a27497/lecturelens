"""Distinguish an executed ASR output from a pre-execution empty task result."""

import json

from score import REPORT, stats


def summarize_coverage(result):
    eligible = [
        row
        for row in result["trials"]
        if row["stage_outcomes"].get("TRANSCRIBE") == "completed"
        and row["edit_distance"] is not None
    ]
    excluded = [r["trial_id"] for r in result["trials"] if r not in eligible]
    edits = sum(row["edit_distance"] for row in eligible)
    characters = sum(row["reference_characters"] for row in eligible)
    return {
        "attempted_trials": len(result["trials"]),
        "completed_transcription_scored_trials": len(eligible),
        "unavailable_transcription_trials": excluded,
        "edit_distance": edits,
        "reference_characters": characters,
        "completed_transcription_weighted_cer": edits / characters
        if characters
        else None,
        "per_lecture_completed_transcription_cer": {
            key: stats([r["cer"] for r in eligible if r["source_id"] == key])
            for key in result["per_lecture"]
        },
        "frozen_all_output_cer_including_empty_task_results": result["weighted_cer"],
        "interpretation": "Additional availability view; original summary and all failed trials are unchanged. A completed ASR with a genuine empty hypothesis still scores 100% CER. A task that never executed TRANSCRIBE has no ASR CER; its failure remains in the 10-attempt denominator and the frozen empty-output penalty metric.",
    }


def main():
    value = json.loads((REPORT / "summary.json").read_text())
    print(json.dumps(summarize_coverage(value), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
