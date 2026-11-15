"""Project only own trial stage/timing records from an existing Java log."""

import argparse
import json
import re
from pathlib import Path


def project(lines, task_ids):
    selected = []
    for line in lines:
        match = re.search(
            r"event=pipeline_step_(completed|failed) taskId=(\S+) stepName=(\S+).*durationMillis=(\d+)",
            line,
        )
        if match and match[2] in task_ids:
            selected.append(
                {
                    "event": match[1],
                    "task_id": match[2],
                    "step": match[3],
                    "duration_ms": int(match[4]),
                }
            )
        match = re.search(
            r"ASR chunk failed, retrying: taskId=([^,]+), chunkIndex=(\d+)/(\d+), attempt=(\d+)",
            line,
        )
        if match and match[1] in task_ids:
            selected.append(
                {
                    "event": "asr_retry",
                    "task_id": match[1],
                    "chunk": int(match[2]),
                    "chunks": int(match[3]),
                    "attempt": int(match[4]),
                }
            )
        match = re.search(
            r"event=llm_aligned_batch_translation_(started|completed|failed) taskId=(\S+)",
            line,
        )
        if match and match[2] in task_ids:
            row = {"event": "translation_batch_" + match[1], "task_id": match[2]}
            for field in ("segmentCount", "durationMillis", "totalTokens", "attempt"):
                value = re.search(rf"\b{field}=(\d+)", line)
                if value:
                    row[field] = int(value[1])
            selected.append(row)
        match = re.search(r"event=llm_aligned_batch_semantic_retry taskId=(\S+)", line)
        if match and match[1] in task_ids:
            selected.append(
                {"event": "translation_semantic_retry", "task_id": match[1]}
            )
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--trials", type=Path, required=True)
    args = parser.parse_args()
    task_ids = {
        json.loads(line)["task_id"] for line in args.trials.read_text().splitlines()
    }
    for row in project(args.log.read_text().splitlines(), task_ids):
        print(json.dumps(row))


if __name__ == "__main__":
    main()
