"""Hand-computed accounting examples and a real read-only PostgreSQL snapshot."""

import json
import os
from pathlib import Path

import pytest
import test_study

from lecturelens_agent.study.metrics_report import (
    build_report,
    load_database,
    load_records,
    main,
    markdown,
    project,
    summarize,
    timestamp,
)

setup = test_study.setup


def event(typ, **payload):
    return {"event_type": typ, "payload": payload}


def record(run_id="r1", *, status="succeeded", kind="practice", calls=1, events=(), ms=100, **extra):
    return {
        "run": {
            "run_id": run_id,
            "session_id": "s1",
            "status": status,
            "model_mode": "mock",
            "model_calls": calls,
            "tool_calls": 1,
            "reserved_tokens": 12345,
            "created_at": "2026-10-14T01:00:00+00:00",
            "finished_at": f"2026-10-14T01:00:00.{ms:06d}+00:00",
        },
        "artifact_kind": kind,
        "events": list(events),
        "elapsed_ms": ms,
        **extra,
    }


def normalized(*rows):
    return [project(r, "sample.jsonl") for r in rows]


def test_hand_calculated_nearest_rank_usage_outcomes_and_time_window():
    rows = normalized(
        *[
            record(
                f"r{i}",
                status=status,
                kind=kind,
                ms=i * 100,
                events=[
                    event("model_started", attempt=1),
                    event(
                        "model_finished",
                        attempt=1,
                        prompt_tokens=i * 10,
                        completion_tokens=i,
                        duration_ms=i * 20,
                    ),
                ],
            )
            for i, (status, kind) in enumerate(
                [
                    ("succeeded", "practice"),
                    ("succeeded", "insufficient_evidence"),
                    ("failed", None),
                    ("cancelled", None),
                ],
                start=1,
            )
        ]
    )
    result = summarize(rows)
    assert result["terminal_outcomes"]["counts"] == {
        "success": 1,
        "abstention": 1,
        "failed": 1,
        "cancelled": 1,
        "budget_exceeded": 0,
        "nonterminal": 0,
        "unknown": 0,
    }
    # [100,200,300,400] => ceil(4*.5)=2 and ceil(4*.95)=4.
    latency = result["latencies_ms"]["evaluation_execute_ms"]
    assert (latency["sample_count"], latency["p50"], latency["p95"]) == (4, 200, 400)
    tokens = result["per_run_metrics"]["total_tokens"]
    assert (tokens["total"], tokens["p50"], tokens["p95"]) == (110, 22, 44)
    assert tokens["time_range"]["from"] == "2026-10-14T01:00:00+00:00"
    assert result["per_run_metrics"]["model_calls"]["total"] == 4
    assert result["per_run_metrics"]["monetary_cost"]["availability"] == "不可得"


def test_partial_usage_and_reserved_tokens_are_never_actual_usage():
    rows = normalized(
        record(
            calls=2,
            events=[
                event("model_started"),
                event("model_finished", prompt_tokens=9, completion_tokens=3),
                event("model_started"),
                event("model_failed", prompt_tokens=7),
            ],
        )
    )
    result = summarize(rows)
    assert result["per_run"][0]["prompt_tokens"]["total"] == 16
    assert result["per_run"][0]["completion_tokens"] == {"total": None, "known_total": 3, "missing_calls": 1}
    assert result["per_run_metrics"]["total_tokens"]["total"] is None
    assert result["per_run_metrics"]["completion_tokens"]["known_total_including_partial_runs"] == 3
    assert "12345" not in json.dumps(result)


def test_zero_model_calls_means_zero_tokens_but_missing_counter_is_unknown():
    zero = record(calls=0)
    missing = record("missing", calls=0)
    del missing["run"]["model_calls"]
    result = summarize(normalized(zero, missing))
    assert result["per_run"][0]["total_tokens"] == 0
    assert result["per_run"][1]["total_tokens"] is None
    assert result["per_run_metrics"]["total_tokens"]["sample_count"] == 1


def test_logical_tool_recovery_failure_and_cancelled_unknown_are_separate():
    rows = normalized(
        record(
            events=[
                event("tool_started", call_id="a", tool="search_course_evidence"),
                event("tool_read_failed", call_id="a", error_code="MCP_TIMEOUT"),
                event("tool_retry_started", call_id="a"),
                event("tool_finished", call_id="a", tool="search_course_evidence"),
                event("tool_started", call_id="b", tool="search_course_evidence"),
                event("dependency_stopped", call_id="b", failure_category="malformed_response"),
                event("node_failed", call_id="b", node="tool", error_code="MCP_MALFORMED_RESPONSE"),
                event("tool_started", call_id="c", tool="search_course_evidence"),
                event("tool_rejected", error_code="INVALID_TOOL_ARGUMENTS"),
            ]
        )
    )
    result = summarize(rows)
    tool = result["logical_tools"]["search_course_evidence"]
    assert (tool["success"], tool["failed"], tool["unknown"], tool["success_rate"]) == (1, 1, 1, 0.5)
    assert tool["failure_categories"] == {"malformed_response": 1}
    assert result["per_run_metrics"]["read_retries"]["total"] == 1
    assert result["failure_event_counts"]["tool_rejected:invalid_parameters"]["sample_count"] == 1


def test_hand_calculated_requested_and_executed_denominators():
    result = summarize(
        normalized(
            record(
                events=[
                    event("tool_started", call_id="a", tool="search_course_evidence"),
                    event("tool_finished", call_id="a", tool="search_course_evidence"),
                    event("tool_started", call_id="b", tool="search_course_evidence"),
                    event("dependency_stopped", call_id="b", error_code="MCP_TIMEOUT"),
                    event(
                        "tool_rejected",
                        node="decide",
                        tool="search_course_evidence",
                        error_code="INVALID_TOOL_ARGUMENTS",
                    ),
                    event("tool_started", call_id="c", tool="search_course_evidence"),
                ]
            )
        )
    )
    requested = result["requested_tools"]["search_course_evidence"]
    executed = result["executed_tools"]["search_course_evidence"]
    assert (
        requested["sample_count"],
        requested["success"],
        requested["failed"],
        requested["rejected"],
        requested["unknown"],
    ) == (4, 1, 1, 1, 1)
    assert requested["rate_denominator"] == 3
    assert requested["success_rate"] == requested["failure_rate"] == requested["rejection_rate"] == 1 / 3
    assert (executed["sample_count"], executed["rate_denominator"], executed["rejected"]) == (3, 2, 0)
    assert executed["success_rate"] == executed["failure_rate"] == 0.5
    assert requested["rejection_categories"] == {"invalid_parameters": 1}
    assert requested["failure_categories"] == {"timeout": 1}
    assert result["logical_tools"] == result["executed_tools"]
    assert result["tool_totals"]["requested"] == requested


@pytest.mark.parametrize(
    "tool,code,cat",
    [
        (None, "INVALID_TOOL_ARGUMENTS", "invalid_parameters"),
        ("publish_untrusted_answer", "UNKNOWN_TOOL", "model_tool_selection"),
        (17, "UNKNOWN_TOOL", "model_tool_selection"),
        (["search_course_evidence"], "UNKNOWN_TOOL", "model_tool_selection"),
        (None, "MODEL_TOOL_CONTRACT", "model_protocol"),
    ],
)
def test_missing_illegal_tool_name_and_nonobject_rejection_are_unknown(tool, code, cat):
    result = summarize(
        normalized(
            record(
                status="failed",
                kind=None,
                events=[
                    event("tool_rejected", node="decide", tool=tool, error_code=code),
                    event("node_failed", node="decide", error_code=code, duration_ms=1),
                ],
            )
        )
    )
    requested = result["requested_tools"]["unknown"]
    assert requested["sample_count"] == requested["rejected"] == 1
    assert requested["success_rate"] == requested["failure_rate"] == 0
    assert requested["rejection_rate"] == 1
    assert requested["rejection_categories"] == {cat: 1}
    assert result["executed_tools"] == {}
    assert result["tool_totals"]["executed"]["success_rate"] is None


def test_decision_rejection_does_not_reuse_previous_successful_call_id():
    result = summarize(
        normalized(
            record(
                events=[
                    event("tool_started", call_id="previous", tool="search_course_evidence"),
                    event("tool_finished", call_id="previous", tool="search_course_evidence"),
                    event("tool_rejected", call_id="previous", node="decide", error_code="UNKNOWN_TOOL"),
                ]
            )
        )
    )
    assert result["executed_tools"]["search_course_evidence"]["success"] == 1
    assert result["tool_totals"]["requested"]["sample_count"] == 2
    assert result["requested_tools"]["unknown"]["rejected"] == 1


def test_nested_rejection_is_counted_once_in_both_started_call_scopes():
    result = summarize(
        normalized(
            record(
                events=[
                    event("tool_started", call_id="a", tool="read_evidence_window"),
                    event(
                        "tool_rejected",
                        node="tool",
                        action="WINDOW",
                        call_id="a",
                        error_code="MCP_INVALID_REQUEST",
                    ),
                    event("tool_rejected", node="tool", call_id="a", error_code="INVALID_TOOL_ARGUMENTS"),
                    event("node_failed", node="tool", call_id="a", error_code="INVALID_TOOL_ARGUMENTS"),
                ]
            )
        )
    )
    for scope in ("requested", "executed"):
        total = result["tool_totals"][scope]
        assert (total["sample_count"], total["rejected"], total["failed"], total["rejection_rate"]) == (
            1,
            1,
            0,
            1,
        )


def test_authority_check_rejection_is_not_a_model_tool_request():
    result = summarize(
        normalized(
            record(
                events=[
                    event(
                        "tool_rejected",
                        node="execute",
                        action="CHECK",
                        call_id=None,
                        error_code="MCP_INVALID_REQUEST",
                    ),
                ]
            )
        )
    )
    assert result["tool_totals"]["requested"]["sample_count"] == 0
    assert result["failure_event_counts"]["tool_rejected:invalid_parameters"]["sample_count"] == 1


def test_transport_return_is_not_semantic_response_validation_success():
    row = record(
        events=[event("tool_read_failed", error_code="MCP_MALFORMED_RESPONSE")],
        mcp_events=[
            {"event": "initialize", "duration_ms": 999},
            {"event": "tools/call", "tool": "get_course_revision", "duration_ms": 10, "error_code": None},
            {
                "event": "tools/call",
                "tool": "get_course_revision",
                "duration_ms": 30,
                "error_code": "MCP_TIMEOUT",
            },
        ],
    )
    result = summarize(normalized(row))
    assert result["mcp_transport_attempts"]["get_course_revision"]["success_rate"] == 0.5
    assert result["latencies_ms"]["mcp:get_course_revision"]["sample_count"] == 2
    assert result["failure_event_counts"]["tool_read_failed:malformed_response"]["sample_count"] == 1


def test_node_durations_are_inclusive_and_missing_is_unavailable():
    row = record(
        ms=1000,
        events=[
            event("node_finished", node="tool", duration_ms=70),
            event("node_failed", node="tool", duration_ms=90),
            event("model_finished", purpose="review", duration_ms=15),
        ],
    )
    result = summarize(normalized(row))
    node = result["latencies_ms"]["node:tool"]
    assert (node["p50"], node["p95"], node["sample_count"]) == (70, 90, 2)
    assert result["latencies_ms"]["node:feedback_tool"]["availability"] == "不可得"
    assert result["latencies_ms"]["evaluation_execute_ms"]["p50"] == 1000
    assert result["latencies_ms"]["run_created_to_finished_ms"]["p50"] == 1


def test_outcome_missing_artifact_is_not_silently_counted_as_success():
    result = summarize(
        normalized(record(kind=None), record("b", status="budget_exceeded"), record("q", status="queued"))
    )
    assert result["terminal_outcomes"]["counts"]["unknown"] == 1
    assert result["terminal_outcomes"]["counts"]["budget_exceeded"] == 1
    assert result["terminal_outcomes"]["counts"]["nonterminal"] == 1


def test_duplicate_snapshots_rejected_and_cohorts_not_blended():
    rows = normalized(record("a", label="baseline"), record("b", label="candidate"))
    report = build_report(rows, [])
    assert len(report["cohorts"]) == 2
    with pytest.raises(ValueError, match="Duplicate"):
        build_report(rows + rows, [])


def test_filters_are_creation_time_inclusive_exclusive_with_timezone():
    rows = normalized(record())
    assert build_report(rows, [], since=timestamp("2026-10-14T01:00:00Z"))["selected_runs"] == 1
    assert build_report(rows, [], until=timestamp("2026-10-14T01:00:00Z"))["selected_runs"] == 0
    assert build_report(rows, [], labels=["other"])["selected_runs"] == 0
    with pytest.raises(ValueError, match="Timezone"):
        timestamp("2026-10-14T01:00:00")
    del rows[0]["run"]["created_at"]
    rows[0]["run"]["created_at"] = None
    with pytest.raises(ValueError, match="without created_at"):
        build_report(rows, [], since=timestamp("2026-10-14T01:00:00Z"))


def test_absent_timestamps_and_active_run_not_filled_with_clock_time():
    row = record(status="running")
    row["run"]["created_at"] = row["run"]["finished_at"] = None
    result = summarize(normalized(row))
    assert result["time_range"]["runs_without_timestamps"] == 1
    assert result["latencies_ms"]["run_created_to_finished_ms"]["sample_count"] == 0


@pytest.mark.parametrize("bad", [-1, float("nan"), True, "12"])
def test_invalid_usage_not_summed(bad):
    with pytest.raises(ValueError, match="measurement"):
        project(record(events=[event("model_finished", prompt_tokens=bad)]), "sample")


def test_jsonl_and_cli_export_only_accounting_never_private_text(tmp_path, monkeypatch):
    secret = "PRIVATE_BODY_OR_CREDENTIAL"
    raw = record(
        events=[
            event(
                "model_finished",
                _trace={"response": secret},
                prompt_tokens=10,
                completion_tokens=5,
                diagnostics=secret,
            )
        ]
    )
    raw["run"]["goal"] = secret
    raw["artifact"] = {"kind": "practice", "questions": [secret]}
    path = tmp_path / "records.jsonl"
    path.write_text(json.dumps(raw) + "\n")
    rows, sources = load_records([path])
    assert sources[0]["records"] == 1 and len(sources[0]["sha256"]) == 64
    assert secret not in json.dumps(build_report(rows, sources))
    output = tmp_path / "output"
    monkeypatch.setattr("sys.argv", ["report", "--records", str(path), "--output-dir", str(output)])
    main()
    assert secret not in (output / "report.json").read_text()
    assert "不可得" in (output / "REPORT.md").read_text()
    assert (output / "report.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_old_quality_record_elapsed_seconds_and_identity_supported():
    raw = record()
    del raw["elapsed_ms"]
    raw.update(
        elapsed_seconds=1.25,
        runtime={"model": "fixed", "dataset_sha256": "frozen"},
        artifact={"kind": "practice"},
    )
    del raw["artifact_kind"]
    row = project(raw, "legacy")
    assert row["elapsed_ms"] == 1250 and row["artifact_kind"] == "practice"
    assert row["cohort"]["dataset_sha256"] == "frozen"
    assert "legacy" in markdown(build_report([row], []))


def test_actual_pg_snapshot_is_read_only_metadata_projection_and_bounded(setup):
    store, _, runtime, _ = setup
    run = test_study.start(setup)
    runtime.execute(run)
    with store.connect() as conn:
        before = conn.execute(
            "SELECT count(*) AS n FROM study_event WHERE run_id=%s", (run["run_id"],)
        ).fetchone()
    rows, sources = load_database(os.environ["AGENT_TEST_DATABASE_URL"], run_ids=[run["run_id"]])
    assert len(rows) == 1 and rows[0]["run"]["run_id"] == run["run_id"]
    assert all(
        set(e["payload"])
        <= {
            "call_id",
            "tool",
            "node",
            "span_id",
            "evidence_call_id",
            "action",
            "attempt",
            "purpose",
            "duration_ms",
            "prompt_tokens",
            "completion_tokens",
            "error_code",
            "failure_category",
            "mode",
        }
        for e in rows[0]["events"]
    )
    report = build_report(rows, sources)
    assert report["cohorts"][0]["terminal_outcomes"]["counts"]["success"] == 1
    assert report["cohorts"][0]["latencies_ms"]["node:tool"]["sample_count"] > 0
    assert "解释" not in json.dumps(report, ensure_ascii=False)
    assert "An algorithm needs" not in json.dumps(report)
    assert "DATABASE_URL" not in json.dumps(report)
    with store.connect() as conn:
        assert (
            conn.execute("SELECT count(*) AS n FROM study_event WHERE run_id=%s", (run["run_id"],)).fetchone()
            == before
        )
    empty, _ = load_database(os.environ["AGENT_TEST_DATABASE_URL"], since=timestamp("2100-01-01T00:00:00Z"))
    assert empty == []


def test_saved_p0_batches_load_without_rewriting_frozen_records():
    root = Path(__file__).resolve().parents[2]
    paths = [
        root / "eval/tool-resilience-20261014/baseline.jsonl",
        root / "eval/tool-resilience-20261014/candidate.jsonl",
        root / "eval/tool-resilience-latency-20261014/serial-clean/healthy-candidate.jsonl",
    ]
    rows, sources = load_records(paths)
    report = build_report(rows, sources)
    assert report["selected_runs"] == 620
    candidate = [c for c in report["cohorts"] if c["identity"]["label"] == "candidate-final"]
    assert sum(c["terminal_outcomes"]["counts"]["success"] for c in candidate) == 80
    assert sum(c["terminal_outcomes"]["counts"]["failed"] for c in candidate) == 220
    for scenario, cat in (
        ("integer_overflow", "invalid_parameters"),
        ("unknown_tool", "model_tool_selection"),
        ("illegal_call_shape", "model_protocol"),
    ):
        c = next(c for c in candidate if c["identity"]["scenario"] == scenario)
        assert c["requested_tools"]["unknown"]["rejected"] == 20
        assert c["requested_tools"]["unknown"]["rejection_categories"] == {cat: 20}
        assert c["requested_tools"]["unknown"]["success_rate"] == 0
        assert c["executed_tools"] == {}
    healthy = next(c for c in report["cohorts"] if c["identity"]["label"] == "healthy-candidate")
    assert healthy["per_run_metrics"]["model_calls"]["total"] == 80
    assert healthy["latencies_ms"]["evaluation_execute_ms"]["p50"] == 871.212
    assert healthy["latencies_ms"]["node:tool"]["availability"] == "不可得"
