"""Count persisted task outcomes and existing MQ attempt log entries."""

import collections
import json
import re

from score import REPORT, records


def main():
    rows = [
        r for r in records(REPORT / "batch-v2/trials.jsonl") if r["phase"] == "finished"
    ]
    lines = (REPORT / "batch-v2/delivery-log.txt").read_text().splitlines()
    failures = []
    for row in rows:
        attempts = []
        for line in lines:
            match = re.search(
                r"event=outbox_delivery_failed .*taskId=(\S+) attempt=(\d+) exhausted=(\S+)",
                line,
            )
            if match and match[1] == row["task_id"]:
                attempts.append(int(match[2]))
        if row["task"].get("errorCode") == "MQ_DELIVERY_EXHAUSTED":
            assert sorted(attempts) == list(range(1, 9)), attempts
            failures.append(
                {
                    "trial_id": row["trial_id"],
                    "task_id": row["task_id"],
                    "outbox_delivery_attempts": len(attempts),
                    "outbox_retries_after_initial_attempt": len(attempts) - 1,
                    "task_retry_count": row["task"]["retryCount"],
                    "entered_asr": False,
                }
            )
    print(
        json.dumps(
            {
                "task_error_code_counts": dict(
                    collections.Counter(r["task"].get("errorCode") for r in rows)
                ),
                "task_terminal_message_counts": dict(
                    collections.Counter(r["task"].get("errorMessage") for r in rows)
                ),
                "exhausted_delivery_trials": failures,
                "broker_observation": "For the exhausted trial the broker rejected all deliveries with response-code=50001 and CL/CQ/INDEX disk usage 0.91. Host df measured 91% after the trials. No service configuration or disk cleanup was performed to hide or replace this failure.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
