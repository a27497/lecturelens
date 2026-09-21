"""Metric-accounting regressions; these are not concurrency acceptance results."""

from run import percentile, summarize


def example(status, seconds, *, started, finished, missing=0, error=None):
    return (
        {
            "status": status,
            "latency_seconds": seconds,
            "error_code": error,
            "failure_type": "infra" if error else None,
        },
        {
            "run": {"finished_at": finished},
            "events": [{"event_type": "run_started", "created_at": started}],
            "metrics": {
                "retrieval_latency_ms": [20],
                "resumptions": 0,
                "model_calls": 2,
                "logical_tool_calls": 1,
                "input_tokens": {"missing_calls": missing, "known_total": 10},
                "output_tokens": {"missing_calls": missing, "known_total": 3},
            },
        },
    )


def test_nearest_rank_small_sample_and_missing():
    assert percentile([], 0.95) is None
    assert percentile([5, 1, 4, 2, 3], 0.5) == 3
    assert percentile([5, 1, 4, 2, 3], 0.95) == 5


def test_fail_fast_does_not_disappear_from_denominator_or_success_latency():
    data = [
        example("failed", 1, started="01", finished="02", error="STUDY_EXECUTION_FAILED"),
        example("succeeded", 20, started="01", finished="21"),
    ]
    rows, traces = zip(*data, strict=True)
    report = summarize(rows, traces, "real")
    assert (report["attempted"], report["succeeded"], report["failed"]) == (2, 1, 1)
    assert report["run_p50_seconds"] == 1
    assert report["successful_run_p50_seconds"] == 20
    assert report["peak_running_runs"] == 2
    assert report["infra_failed_runs"] == 1


def test_missing_usage_is_unknown_and_reservation_is_never_token_usage():
    row, trace = example("cancelled", 4, started="01", finished="05", missing=1)
    report = summarize([row], [trace], "deterministic")
    assert report["cancelled"] == 1
    assert report["failed"] == 0
    assert report["input_tokens"] == {"total": None, "known_total": 10, "missing_calls": 1}
    assert report["billable_model_calls"] == 0


def test_recovery_and_timeout_are_counted_separately():
    row, trace = example("budget_exceeded", 90, started="01", finished="91", error="RUN_BUDGET_EXCEEDED")
    trace["metrics"]["resumptions"] = 1
    report = summarize([row], [trace], "real")
    assert report["failed"] == report["recovered"] == report["timeout_runs"] == 1
    assert report["failure_types"] == {"RUN_BUDGET_EXCEEDED": 1}
