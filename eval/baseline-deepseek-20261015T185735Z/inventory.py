"""Read-only failed-task inventory across existing LectureLens schemas."""

import json

from support import ROOT, disk, mq, save, sql, utc


def main():
    assert disk()["percent"] <= 85, "Disk above 85%; stop"
    baseline = [
        json.loads(x)
        for x in (ROOT / "eval/baseline-asr-20261015/batch-v2/trials.jsonl")
        .read_text()
        .splitlines()
    ]
    trial_ids = {
        x["task_id"]: x["trial_id"] for x in baseline if x["phase"] == "finished"
    }
    schemas = sql(
        "SELECT JSON_OBJECT('schema',table_schema) FROM information_schema.tables WHERE table_name='analysis_task' ORDER BY table_schema;"
    )
    failed, outbox, formal, active = [], [], [], []
    for item in schemas:
        name = item["schema"]
        assert name.replace("_", "").isalnum()
        fields = f"'schema','{name}','task_id',a.id,'stage',a.current_stage,'status',a.status,'error_code',a.error_code,'error_message',a.error_message,'created_at',a.created_at,'finished_at',a.finished_at,'retry_count',a.retry_count,'deleted_at',a.deleted_at"
        query = f"SELECT JSON_OBJECT({fields}) FROM `{name}`.analysis_task a WHERE a.status IN ('FAILED','DEAD') OR EXISTS(SELECT 1 FROM `{name}`.task_outbox o WHERE o.task_id=a.id AND o.status='DEAD') ORDER BY a.created_at,a.id;"
        rows = sql(query)
        for row in rows:
            row["p1_3_formal_baseline"] = row["task_id"] in trial_ids
            row["baseline_trial_id"] = trial_ids.get(row["task_id"])
        failed.extend(rows)
        outbox.extend(
            sql(
                f"SELECT JSON_OBJECT('schema','{name}','event_id',event_id,'task_id',task_id,'event_type',event_type,'status',status,'attempts',attempts,'available_at',available_at,'claim_until',claim_until,'last_error',last_error,'created_at',created_at,'completed_at',completed_at) FROM `{name}`.task_outbox WHERE status IN ('PENDING','DELIVERING','DEAD') ORDER BY created_at;"
            )
        )
        active.extend(
            sql(
                f"SELECT JSON_OBJECT('schema','{name}','task_id',id,'status',status,'stage',current_stage) FROM `{name}`.analysis_task WHERE status IN ('QUEUED','RUNNING') AND deleted_at IS NULL;"
            )
        )
        if name == "baseline_asr_20261015":
            selected = ",".join("'" + x + "'" for x in trial_ids)
            formal.extend(
                sql(
                    f"SELECT JSON_OBJECT({fields}) FROM `{name}`.analysis_task a WHERE a.id IN ({selected}) ORDER BY a.id;"
                )
            )
    save(
        "failed-task-inventory.json",
        {"utc": utc(), "tasks": failed, "outbox": outbox, "active_tasks": active},
    )
    save("original-baseline-db-before.json", formal)
    topics = mq(["topicList", "-n", "rocketmq-namesrv:9876"])
    save("mq-topic-list-before.json", topics)
    relevant = [
        x.strip()
        for x in topics["stdout"].splitlines()
        if x.startswith(("%RETRY%", "%DLQ%"))
        and any(v in x.lower() for v in ["lecturelens", "courselingo", "baseline-asr"])
    ]
    offsets = []
    for topic in relevant:
        offsets.append(
            {
                "topic": topic,
                **mq(["topicStatus", "-n", "rocketmq-namesrv:9876", "-t", topic]),
            }
        )
    save("mq-retry-dead-offsets-before.json", offsets)
    save(
        "dead-inventory-summary.json",
        {
            "utc": utc(),
            "failed_task_count": len(failed),
            "formal_baseline_count": sum(x["p1_3_formal_baseline"] for x in failed),
            "non_baseline_failed_count": sum(
                not x["p1_3_formal_baseline"] for x in failed
            ),
            "active_tasks": active,
            "outbox_states": outbox,
            "retry_dead_topics": relevant,
            "mutations": [],
        },
    )
    print(
        json.dumps(
            {
                "failed": len(failed),
                "formal_baseline": sum(x["p1_3_formal_baseline"] for x in failed),
                "active": active,
                "outbox": outbox,
                "offsets": offsets,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
