"""Read-only final accounting; preserve original baseline DB rows and binding."""

import hashlib
import json
import pathlib
import re
import subprocess

from support import PRIVATE, PUBLIC, admin, disk, mq, save, sql, utc


def main():
    rows = [json.loads(x) for x in (PUBLIC / "trials.jsonl").read_text().splitlines()]
    finished = [r for r in rows if r["phase"] == "finished"]
    assert len(finished) == 10, "Do not finalize an incomplete measurement"
    ids = ",".join("'" + r["task_id"] + "'" for r in finished)
    calls = sql(
        f"SELECT JSON_OBJECT('task_id',task_id,'stage',stage,'status',status,'provider',provider,'model',model,'prompt_tokens',prompt_tokens,'completion_tokens',completion_tokens,'total_tokens',total_tokens,'error_code',error_code,'error_message',error_message,'retryable',retryable,'duration_millis',duration_millis) FROM courselingo.ai_call_record WHERE task_id IN ({ids}) ORDER BY task_id,id;"
    )
    save("database-call-diagnostics.json", calls)
    segments = {}
    for trial in finished:
        result = json.loads(
            (PRIVATE / "results" / f"{trial['trial_id']}.json").read_text()
        )
        segments[trial["trial_id"]] = {
            "source_segments": len(result.get("subtitles") or []),
            "persisted_translated_segments": len(result.get("translations") or []),
        }
    save("translation-segment-counts.json", segments)
    before = json.loads((PUBLIC / "original-baseline-db-before.json").read_text())
    original_ids = ",".join("'" + r["task_id"] + "'" for r in before)
    fields = "'schema','baseline_asr_20261015','task_id',a.id,'stage',a.current_stage,'status',a.status,'error_code',a.error_code,'error_message',a.error_message,'created_at',a.created_at,'finished_at',a.finished_at,'retry_count',a.retry_count,'deleted_at',a.deleted_at"
    after = sql(
        f"SELECT JSON_OBJECT({fields}) FROM baseline_asr_20261015.analysis_task a WHERE a.id IN ({original_ids}) ORDER BY a.id;"
    )
    save("original-baseline-db-after.json", after)
    assert before == after, "Original baseline DB state changed"
    bridge = admin()
    catalog = bridge.api("/admin/system-models/catalog")
    save("catalog-final.json", catalog)
    initial = json.loads((PUBLIC / "catalog-bound.json").read_text())
    assert (
        catalog["version"] == initial["version"] == 10
        and catalog["bindings"] == initial["bindings"]
    )
    assert (
        catalog["effective"]["TRANSLATION_FULL_TEXT"]["source"] == "DATABASE"
        and catalog["effective"]["TRANSLATION_FULL_TEXT"]["model"] == "deepseek-flash"
    )
    offsets = mq(["topicList", "-n", "rocketmq-namesrv:9876"])
    save("mq-topic-list-final.json", offsets)
    p = subprocess.run(
        [
            "docker",
            "exec",
            "lecturelens-demo-l2-rocketmq-broker-1",
            "cat",
            "/home/rocketmq/store/config/consumerOffset.json",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    saved = json.loads(re.sub(r"([{,]\s*)(\d+)(\s*:)", r'\1"\2"\3', p.stdout))
    save("mq-consumer-offsets-final.json", saved)
    retry = []
    for topic in offsets["stdout"].splitlines():
        if topic.startswith(("%RETRY%", "%DLQ%")) and any(
            s in topic for s in ["lecturelens", "courselingo", "baseline-asr"]
        ):
            retry.append(
                {
                    "topic": topic,
                    **mq(["topicStatus", "-n", "rocketmq-namesrv:9876", "-t", topic]),
                }
            )
    save("mq-retry-dead-offsets-final.json", retry)
    active = sql(
        "SELECT JSON_OBJECT('task_id',id,'status',status,'stage',current_stage) FROM courselingo.analysis_task WHERE status IN ('QUEUED','RUNNING') AND deleted_at IS NULL;"
    )
    runtime = json.loads((PUBLIC / "runtime-identity.json").read_text())
    same = {}
    for name, p in runtime["services"].items():
        f = pathlib.Path("/proc") / str(p["pid"]) / "stat"
        same[name] = (
            f.exists()
            and f.read_text().split(") ", 1)[1].split()[19] == p["start_ticks"]
        )
    with pathlib.Path(runtime["java_jar_path"]).open("rb") as f:
        jar = hashlib.file_digest(f, "sha256").hexdigest()
    assert jar == runtime["java_jar_sha256"] and all(same.values())
    checked = {
        "utc": utc(),
        "disk": disk(),
        "active_tasks": active,
        "original_baseline_db_unchanged": before == after,
        "services_unchanged": same,
        "jar_unchanged": jar == runtime["java_jar_sha256"],
        "binding_retained": True,
        "version": catalog["version"],
        "business_code_changed": False,
        "production_parameters_changed": False,
    }
    save("final-check.json", checked)
    save(
        "raw-locations.json",
        {
            "private_directory": str(PRIVATE),
            "results": str(PRIVATE / "results"),
            "task_logs": str(PRIVATE / "logs"),
            "driver_log": str(PRIVATE / "driver.log"),
            "response_observer_log": str(PRIVATE / "local-response-observer.log"),
            "pricing_html": str(PRIVATE / "deepseek-pricing.html"),
            "media_manifest": "eval/baseline-asr-20261015/assets.lock.json",
        },
    )
    print(json.dumps(checked, ensure_ascii=False))


if __name__ == "__main__":
    main()
