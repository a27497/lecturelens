"""Offline public projection. Raw traces, model responses and credentials remain private."""

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from run import percentile, summarize


def read(path):
    return json.loads(path.read_text())


def public_projection(value):
    if isinstance(value, list):
        return [public_projection(item) for item in value]
    if not isinstance(value, dict):
        return value
    if {"by_case", "checks", "violations"} <= value.keys():
        # Individual request audit records stay private; publish denominators.
        return {"by_case": value["by_case"], "violations": value["violations"]}
    return {key: public_projection(item) for key, item in value.items() if key != "before_effects"}


def cohort(folder):
    original = read(folder / "result.json")
    audit = read(folder / "isolation-audit-v2.json")
    traces = [read(folder / (row["run_id"] + ".trace.json")) for row in original["rows"]]
    result = summarize(original["rows"], traces, original["mode"])
    queue, execution, search_ok, search_failed = [], [], [], []
    artifacts = []
    checkpoint_ids = []
    successful_model_seconds = 0
    successful_run_seconds = 0
    identity = read(folder / "identity.json")
    observed_models = sorted(
        {
            e["payload"].get("model_selection", {}).get("model")
            for trace in traces
            for e in trace["events"]
            if e["event_type"] == "model_started"
        }
    )
    for trace in traces:
        run = trace["run"]
        if run["status"] == "succeeded":
            successful_model_seconds += sum(trace["metrics"]["llm_latency_ms"]) / 1000
            successful_run_seconds += (
                datetime.fromisoformat(run["finished_at"]) - datetime.fromisoformat(run["created_at"])
            ).total_seconds()
        started = next(e["created_at"] for e in trace["events"] if e["event_type"] == "run_started")
        queue.append(
            (datetime.fromisoformat(started) - datetime.fromisoformat(run["created_at"])).total_seconds()
        )
        execution.append(
            (datetime.fromisoformat(run["finished_at"]) - datetime.fromisoformat(started)).total_seconds()
        )
        for event in trace["events"]:
            if event["payload"].get("action") == "SEARCH":
                if event["event_type"] == "evidence_finished":
                    search_ok.append(event["payload"]["duration_ms"])
                elif event["event_type"] == "evidence_failed":
                    search_failed.append(event["payload"]["duration_ms"])
        artifacts += [t["result"]["artifact_id"] for t in trace["tools"] if t["result"].get("artifact_id")]
        checkpoint_ids += [c["checkpoint_id"] for c in trace["checkpoints"]]
    result.update(
        users=original["users"],
        workers=original["workers"],
        queue_p50_seconds=percentile(queue, 0.5),
        queue_p95_seconds=percentile(queue, 0.95),
        execution_p50_seconds=percentile(execution, 0.5),
        execution_p95_seconds=percentile(execution, 0.95),
        successful_search_count=len(search_ok),
        failed_search_count=len(search_failed),
        successful_search_p50_ms=percentile(search_ok, 0.5),
        successful_search_p95_ms=percentile(search_ok, 0.95),
        failed_search_p50_ms=percentile(search_failed, 0.5),
        failed_search_p95_ms=percentile(search_failed, 0.95),
        unique_artifacts=len(set(artifacts)),
        duplicate_artifact_ids=len(artifacts) - len(set(artifacts)),
        checkpoint_observations=len(checkpoint_ids),
        duplicate_checkpoint_ids=len(checkpoint_ids) - len(set(checkpoint_ids)),
        isolation=audit["by_case"],
        isolation_audit_sha256=hashlib.sha256((folder / "isolation-audit-v2.json").read_bytes()).hexdigest(),
        identity={
            "commit": identity["commit"],
            "created_at": identity["created_at"],
            "arguments": identity["arguments"],
            "runtime_sources_sha256": hashlib.sha256(
                json.dumps(
                    {
                        k: v
                        for k, v in identity["source_sha256"].items()
                        if k.startswith("agent-service/src/")
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
            "harness_sources_sha256": hashlib.sha256(
                json.dumps(
                    {k: v for k, v in identity["source_sha256"].items() if k.startswith("eval/")},
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
        },
        captured_provider_responses=len(list(folder.glob("*.response.json"))),
        observed_models=observed_models,
        successful_run_model_time_fraction=round(successful_model_seconds / successful_run_seconds, 4)
        if successful_run_seconds
        else None,
        raw_result_sha256=hashlib.sha256((folder / "result.json").read_bytes()).hexdigest(),
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", type=Path, default=Path(".data/multi-user-phase-e"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    labels = ["deterministic-5", "deterministic-20", "deterministic-50", "real-5", "real-10"]
    cohorts = {label: cohort(args.private / label) for label in labels}
    checks = {}
    for result in cohorts.values():
        for case, counts in result["isolation"].items():
            summary = checks.setdefault(case, Counter())
            summary.update(counts)
    late = read(args.private / "late-artifact-5/result.json")
    faults = read(args.private / "faults-5/result.json")
    pilot = read(args.private / "pilot-fixed-3/result.json")
    pending_changes = read(args.private / "late-artifact-5/pending-write-audit.json")
    control = read(args.private / "sequential-control-5/result.json")
    committed = read(args.private / "artifact-recovery-5/result.json")
    manifest = read(args.private / "deterministic-50/manifest.local.json")
    completed = (
        all(cohorts[f"deterministic-{n}"]["attempted"] == n for n in [5, 20, 50])
        and cohorts["real-5"]["attempted"] == 5
        and all(
            c["observed_models"]
            == (["phase-e-fixed-response"] if c["mode"] == "deterministic" else ["qwen3-max"])
            for c in cohorts.values()
        )
        and len({i["scope"]["owner_id"] for i in manifest}) == 50
        and len({i["scope"]["course_id"] for i in manifest}) == 50
        and len(late["cancel"]["late_result_checks"]) == 5
        and len(faults["recovery"]["checks"]) == 5
        and len(pending_changes) == 5
        and all(
            c["added_channels"] == ["__error__"]
            and not c["removed_channels"]
            and c["error_values"] == ["RunStopped()"]
            for c in pending_changes
        )
        and late["cancel"]["replacement_succeeded"] == faults["recovery"]["succeeded"] == 5
        and not any(c["duplicate_artifact_ids"] or c["duplicate_checkpoint_ids"] for c in cohorts.values())
        and not sum(c["violations"] for c in checks.values())
        and all(
            c["late_response_returned"]
            and c["events_unchanged"]
            and c["checkpoint_states_unchanged"]
            and c["artifacts"] == 0
            and c["status"] == "cancelled"
            for c in late["cancel"]["late_result_checks"]
        )
        and all(
            c["artifacts"] == c["finished_events"] == c["resumptions"] == c["search_executions"] == 1
            and c["deadline_unchanged"]
            and c["original_tools_retained"]
            and c["checkpoint_history_retained"]
            for c in faults["recovery"]["checks"]
        )
        and not late["active_run_isolation"]["violations"]
        and not faults["recovery"]["isolation"]["violations"]
        and committed["succeeded"] == committed["recovered"] == len(committed["checks"]) == 5
        and not committed["isolation"]["violations"]
        and all(
            c["artifacts"] == c["artifact_events"] == c["finished_events"] == c["resumptions"] == 1
            and all(
                c[k]
                for k in [
                    "artifact_content_unchanged",
                    "tool_results_unchanged",
                    "model_calls_unchanged",
                    "tool_calls_unchanged",
                    "deadline_unchanged",
                ]
            )
            for c in committed["checks"]
        )
    )
    result = {
        "phase": "E",
        "experiment_acceptance_checks_pass": completed,
        "production_code_changed": False,
        "quality_benchmark": False,
        "environment": read(args.private / "environment.json"),
        "cohorts": cohorts,
        "sequential_control": {k: v for k, v in control.items() if k != "isolation"},
        "isolation_formal_cohorts": checks,
        "independent_owners": len({i["scope"]["owner_id"] for i in manifest}),
        "independent_courses": len({i["scope"]["course_id"] for i in manifest}),
        "cancel": late["cancel"],
        "cancel_active_run_isolation": late["active_run_isolation"]["by_case"],
        "recovery": faults["recovery"],
        "post_commit_recovery": committed,
        "bad_cases": {
            "formal_failed_runs": [
                dict(cohort=label, **row)
                for label, result in cohorts.items()
                for row in result["rows"]
                if row["status"] != "succeeded"
            ],
            "pilot": {k: pilot[k] for k in ["attempted", "succeeded", "failed", "failure_types", "rows"]},
            "pilot_accounting_note": "Two empty-evidence traces were initially marked as scope-check failures. Both were failed SEARCHs with zero returned Evidence, not cross-user disclosure. Original result is preserved; subsequent harness separates observations from violations.",
            "foreign_id_probe_note": "The initial harness derived peer IDs from successful SEARCH traces, so failed peers could yield an empty READ. Published formal isolation totals use a separate v2 audit with actual nonempty peer-owned Java Evidence IDs for every probe. Original trial results remain untouched.",
            "initial_cancel": faults["cancel"],
            "checkpoint_diagnostic": read(args.private / "late-artifact-5/pending-write-audit.json"),
            "preparation_wait_timeouts": read(args.private / "preparation-timeouts.json"),
        },
        "regression": read(args.private / "regression.json"),
        "limitations": [
            "Concurrent login/start burst; deterministic executor bounded to five workers. Real cohorts use five and ten workers. Production default remains one sequential worker.",
            "Fixed responses prove mechanics only. Successful real Runs are completion counts, not independently scored teaching quality.",
            "Same public MIT strings clip independently uploaded by 50 owners; this is not unseen-course or long-duration soak testing.",
            "Run latency is persisted creation-to-terminal, includes queue; SEARCH includes failures. Small-sample nearest-rank P95.",
            "Background course preparation shares host and provider during early cohorts. Not an isolated hardware throughput benchmark.",
            "Unknown token usage is null. Fixed provider makes no billable model calls; real usage comes only from provider replies.",
            "Negative browser/gateway probes use ring peers, not every user pair. Signed stale revision and wrong-owner probes hit all four Java Authority actions.",
        ],
    }
    args.output.write_text(json.dumps(public_projection(result), ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {
                "experiment_acceptance_checks_pass": completed,
                "formal_attempted": sum(c["attempted"] for c in cohorts.values()),
                "formal_failed": len(result["bad_cases"]["formal_failed_runs"]),
            }
        )
    )


if __name__ == "__main__":
    main()
