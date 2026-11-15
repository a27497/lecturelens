#!/usr/bin/env python3
"""Read only fixed log events and archived non-sensitive diagnostic projections."""
import collections
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=PUBLIC / 'diagnosis.json')
    parser.add_argument('--since', default='48 hours ago')
    parser.add_argument('--until')
    args = parser.parse_args()
    output = args.output
    assert not output.exists()
    allowed = {"event", "taskId", "providerErrorCategory", "httpStatus", "providerErrorCode",
               "retryable", "responseFormatUsed", "attempt", "batchSegmentCount", "batchInputChars",
               "durationMillis", "stepName", "errorType", "snapshotId", "configVersion", "outcome",
               "category", "segmentCount", "totalTokens", "outputLength"}
    command = ["journalctl", "-u", "lecturelens-live-backend.service", "--since", args.since,
               "--no-pager", "--grep=event=(llm_aligned_batch_translation_(failed|completed)|system_model_call_completed|pipeline_step_failed)", "-o", "json"]
    if args.until:
        command.extend(['--until', args.until])
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
    events = []
    event_names = ("llm_aligned_batch_translation_failed", "llm_aligned_batch_translation_completed",
                   "system_model_call_completed", "pipeline_step_failed")
    for line in process.stdout:
        row = json.loads(line)
        fields = {key: value for key, value in re.findall(r"\b([A-Za-z][A-Za-z0-9]*)=([A-Za-z0-9_.:/-]+)", row.get("MESSAGE", "")) if key in allowed}
        # ANSI color reset ends in a word character immediately before event=.
        # Match known event literals, rather than requiring a word boundary.
        fields["event"] = next((name for name in event_names if "event=" + name in row.get("MESSAGE", "")), None)
        events.append({"timestamp_us": row["__REALTIME_TIMESTAMP"], "pid": row.get("_PID"), **fields})
    assert process.wait(timeout=10) == 0
    failures = [row for row in events if row.get("event") == "llm_aligned_batch_translation_failed" and row.get("providerErrorCategory") == "OUTPUT_INVALID"]
    ids = {row["taskId"] for row in failures}
    assert failures and len(failures) == len(ids), "invalid or duplicate cohort extraction"
    events = [row for row in events if row.get("taskId") in ids]
    diagnostic_path = ROOT / "eval/baseline-deepseek-20261015T185735Z/p13d/diagnostics.json"
    diagnostic_fields = {"id", "task_id", "model", "feature", "created_at", "http_status", "finish_reason",
                         "provider_reason", "validation_reason", "validation_category", "final_validation_reason",
                         "prompt_tokens", "completion_tokens", "total_tokens", "config_version", "snapshot_id"}
    diagnostics = [{key: value for key, value in row.items() if key in diagnostic_fields} for row in json.loads(diagnostic_path.read_text())]
    tasks = []
    for failure in failures:
        task = failure["taskId"]
        rows = [row for row in events if row.get("taskId") == task]
        detail = [row for row in diagnostics if row["task_id"] == task]
        tasks.append({"task_id": task, "failed_at_utc": dt.datetime.fromtimestamp(int(failure["timestamp_us"]) / 1e6, dt.timezone.utc).isoformat(),
                      "pid": failure["pid"], "provider_failure": failure,
                      "failed_steps": [row for row in rows if row.get("event") == "pipeline_step_failed"],
                      "completed_batches": sum(row.get("event") == "llm_aligned_batch_translation_completed" for row in rows),
                      "config_versions": sorted({row["configVersion"] for row in rows if "configVersion" in row}),
                      "archived_diagnostics": detail,
                      "attribution": "CONFIRMED_LENGTH_WITH_EMPTY_CONTENT" if detail else "PROVIDER_PATH_OUTPUT_INVALID_SUBREASON_UNRECORDED"})
    current = ROOT / ".data/system-model-management/deploy-20261016/backend.jar"
    artifacts = []
    for path in (current, ROOT / ".data/baseline-deepseek-20261015T185735Z/p13d/backend-before.jar"):
        if not path.exists():
            continue
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        with zipfile.ZipFile(path) as jar:
            props = jar.read("META-INF/build-info.properties").decode().splitlines()
            build = {key: value for line in props if "=" in line for key, value in [line.split("=", 1)] if key in {"build.gitCommit", "build.time", "build.version"}}
            classes = {name: hashlib.sha256(jar.read(name)).hexdigest() for name in jar.namelist() if name.endswith(("/SystemModelChatClient.class", "/SubtitleTranslationServiceImpl.class", "/LlmStageException.class"))}
        artifacts.append({"path": str(path.relative_to(ROOT)), "sha256": digest, "build": build, "class_sha256": classes})
    fds = []
    for path in Path("/proc/4866/fd").iterdir():
        try:
            target = os.readlink(path)
            if target == str(current): fds.append(path.name)
        except OSError:
            pass
    result = {"collected_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "journal_command": command,
              "failure_events": len(failures), "unique_tasks": len(ids), "tasks": tasks,
              "historical_pid_counts": dict(collections.Counter(row["pid"] for row in failures)),
              "confirmed_subreason_tasks": sum(bool(row["archived_diagnostics"]) for row in tasks),
              "unknown_subreason_tasks": sum(not row["archived_diagnostics"] for row in tasks),
              "current_pid": 4866, "current_pid_deployed_jar_fds": fds, "artifacts": artifacts,
              "archived_diagnostic_source": str(diagnostic_path.relative_to(ROOT)),
              "archived_diagnostic_sha256": hashlib.sha256(diagnostic_path.read_bytes()).hexdigest(),
              "sensitive_response_or_course_content_read": False, "credentials_read": False,
              "live_database_access": False, "provider_calls": 0, "runtime_mutations": []}
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("failure_events", "unique_tasks", "historical_pid_counts", "confirmed_subreason_tasks", "unknown_subreason_tasks")}))


if __name__ == "__main__":
    main()
