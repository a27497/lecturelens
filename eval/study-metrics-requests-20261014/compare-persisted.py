#!/usr/bin/env python3
"""Exercise both report CLI inputs against the same retained synthetic Runs."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts/eval/report-study-metrics.py"


def snapshot():
    with psycopg.connect(
        os.environ["AGENT_DATABASE_URL"], row_factory=dict_row
    ) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        data = {
            "runs": conn.execute(
                "SELECT run_id,status,model_calls,tool_calls,xmin::text AS row_version FROM study_run ORDER BY run_id"
            ).fetchall(),
            "table_counts": {
                table: conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()[
                    "n"
                ]
                for table in (
                    "study_session",
                    "study_run",
                    "study_event",
                    "study_artifact",
                    "checkpoints",
                )
            },
        }
        data["sha256"] = hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()
        return data


def cli(output, *args):
    subprocess.run(
        [sys.executable, str(CLI), *args, "--output-dir", str(output)], check=True
    )
    return json.loads((output / "report.json").read_text())


def counts(report):
    values = Counter()
    for cohort in report["cohorts"]:
        values.update(cohort["terminal_outcomes"]["counts"])
    return dict(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.records.read_text().splitlines()]
    args.output_dir.mkdir(parents=True, exist_ok=False)
    before = snapshot()
    ids = {row["run"]["run_id"] for row in records}
    assert ids == {row["run_id"] for row in before["runs"]}, (
        "Use the isolated fixture database only"
    )
    db_report = cli(args.output_dir / "database", "--database")
    file_report = cli(args.output_dir / "jsonl", "--records", str(args.records))
    assert db_report["selected_runs"] == file_report["selected_runs"] == len(records)
    assert counts(db_report) == counts(file_report)
    db_runs = {row["run_id"]: row for c in db_report["cohorts"] for row in c["per_run"]}
    file_runs = {
        row["run_id"]: row for c in file_report["cohorts"] for row in c["per_run"]
    }
    for run_id in ids:
        assert {
            k: v for k, v in db_runs[run_id].items() if k != "evaluation_execute_ms"
        } == {
            k: v for k, v in file_runs[run_id].items() if k != "evaluation_execute_ms"
        }
    scenarios = []
    for scenario in sorted({row["scenario"] for row in records}):
        matching = [
            row["run"]["run_id"] for row in records if row["scenario"] == scenario
        ]
        selector = [flag for run_id in matching for flag in ("--run-id", run_id)]
        selected = cli(
            args.output_dir / ("database-" + scenario), "--database", *selector
        )["cohorts"][0]
        saved = next(
            c for c in file_report["cohorts"] if c["identity"]["scenario"] == scenario
        )
        for key in (
            "terminal_outcomes",
            "raw_statuses",
            "per_run_metrics",
            "requested_tools",
            "executed_tools",
            "tool_totals",
            "failure_event_counts",
        ):
            assert selected[key] == saved[key], (scenario, key)
        assert (
            selected["latencies_ms"]["run_created_to_finished_ms"]
            == saved["latencies_ms"]["run_created_to_finished_ms"]
        )
        for key, measured in selected["latencies_ms"].items():
            if key.startswith("model:"):
                assert measured == saved["latencies_ms"][key]
        scenarios.append(
            {
                "scenario": scenario,
                "sample_count": len(matching),
                "terminal_outcomes": selected["terminal_outcomes"],
                "tools": selected["tool_totals"],
                "model_calls": selected["per_run_metrics"]["model_calls"],
                "exact_match": True,
            }
        )
    after = snapshot()
    assert before == after, "Report paths changed retained data"
    result = {
        "sample_count": len(records),
        "samples_per_scenario": scenarios,
        "terminal_outcomes": counts(db_report),
        "per_run_resources_and_outcomes_match": True,
        "per_scenario_tool_counts_rates_and_categories_match": True,
        "persisted_end_to_end_and_model_latency_match": True,
        "db_unchanged": True,
        "database_before": before,
        "database_after": after,
        "differences": [
            "DB does not store evaluation elapsed_ms: evaluation_execute_ms is unavailable; JSONL records it.",
            "DB has persisted private node/evidence timing metadata; public JSONL excludes those events, so those metrics are unavailable there.",
            "DB does not persist scenario/label/fixture identity: manifest-selected Run IDs match JSONL cohorts; no historical identity is inferred.",
            "Internal authority fixture has no MCP transport observer: MCP metrics unavailable in both paths.",
        ],
    }
    (args.output_dir / "comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "sample_count": len(records),
                "terminal_outcomes": counts(db_report),
                "exact_counts_match": True,
                "db_unchanged": True,
            }
        )
    )


if __name__ == "__main__":
    main()
