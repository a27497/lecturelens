"""Hand-computed checks for the offline accounting rules, not model quality."""

import importlib.util
from pathlib import Path

import pytest
from coverage_asr import summarize_coverage
from rapidfuzz.distance import Levenshtein
from score import caption_text, normalize, stats, token_cost


def test_hand_computed_character_edits():
    reference = normalize("cat")
    hypothesis = normalize("cut!")
    assert len(reference) == 3
    assert Levenshtein.distance(reference, hypothesis) == 1
    assert Levenshtein.distance(reference, hypothesis) / len(reference) == 1 / 3


def test_same_number_spelling_and_punctuation_rules():
    assert normalize("PROFESSOR: The 12 values, [LAUGHTER] 1,000.") == normalize(
        "the twelve values one thousand"
    )
    assert normalize("2.5") == normalize("two point five")
    assert normalize("ＦＯＯ &amp; Bar") == "foobar"


def test_vtt_times_and_markup_never_count_as_reference(tmp_path):
    path = tmp_path / "reference.txt"
    path.write_text(
        "WEBVTT\n\ncue-1\n00:00:01.000 --> 00:00:02.000\n<c>Hello,</c>\nworld!\n\n"
    )
    assert normalize(caption_text(path)) == "helloworld"


def test_hand_computed_mean_and_sample_variation():
    result = stats([10, 14])
    assert result == {
        "n": 2,
        "mean": 12,
        "sample_sd": pytest.approx(8**0.5),
        "min": 10,
        "max": 14,
    }
    assert stats([])["mean"] is None
    assert stats([10])["sample_sd"] is None


def test_usage_cost_is_not_audio_duration_estimation():
    assert token_cost(
        {"input_tokens": 1_000_000, "output_tokens": 2_000_000}
    ) == pytest.approx(6.2)
    assert token_cost({"input_tokens": 120, "output_tokens": 5}) == pytest.approx(
        0.0001095
    )
    assert token_cost({"duration": 100}) is None
    assert token_cost({"input_tokens": True, "output_tokens": 5}) is None
    assert token_cost({"input_tokens": -1, "output_tokens": 5}) is None
    assert token_cost(None) is None


def test_weighted_cer_is_not_the_macro_average():
    # One edit in two characters and one edit in eight: 2/10, not (1/2+1/8)/2.
    edits = [
        Levenshtein.distance("ab", "ax"),
        Levenshtein.distance("abcdefgh", "abcdefgx"),
    ]
    assert sum(edits) / (2 + 8) == 0.2


def test_unexecuted_empty_result_is_not_an_asr_output_but_stays_a_failed_trial():
    result = {
        "trials": [
            {
                "trial_id": "real_empty",
                "source_id": "a",
                "stage_outcomes": {"TRANSCRIBE": "completed"},
                "edit_distance": 2,
                "reference_characters": 2,
                "cer": 1,
            },
            {
                "trial_id": "real_text",
                "source_id": "a",
                "stage_outcomes": {"TRANSCRIBE": "completed"},
                "edit_distance": 1,
                "reference_characters": 8,
                "cer": 0.125,
            },
            {
                "trial_id": "queue_failed",
                "source_id": "a",
                "stage_outcomes": {},
                "edit_distance": 10,
                "reference_characters": 10,
                "cer": 1,
            },
        ],
        "per_lecture": {"a": {}},
        "weighted_cer": 13 / 20,
    }
    observed = summarize_coverage(result)
    assert observed["attempted_trials"] == 3
    assert observed["completed_transcription_scored_trials"] == 2
    assert observed["unavailable_transcription_trials"] == ["queue_failed"]
    assert observed["completed_transcription_weighted_cer"] == 3 / 10
    assert observed["frozen_all_output_cer_including_empty_task_results"] == 13 / 20
    assert len(result["trials"]) == 3


def test_stage_failures_and_retries_do_not_import_unrelated_tasks():
    spec = importlib.util.spec_from_file_location(
        "asr_stage_projection", Path(__file__).with_name("collect-stages.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = module.project(
        [
            "event=pipeline_step_completed taskId=own stepName=TRANSCRIBE durationMillis=50",
            "event=pipeline_step_failed taskId=own stepName=TRANSLATE_SUBTITLES durationMillis=900",
            "ASR chunk failed, retrying: taskId=own, chunkIndex=2/4, attempt=1",
            "event=llm_aligned_batch_translation_failed taskId=own attempt=2 durationMillis=80",
            "event=pipeline_step_completed taskId=other stepName=TRANSCRIBE durationMillis=77",
        ],
        {"own"},
    )
    assert len(rows) == 4
    assert [row["duration_ms"] for row in rows if "duration_ms" in row] == [50, 900]
    assert sum(row["event"] == "asr_retry" for row in rows) == 1
    assert rows[-1]["attempt"] == 2
