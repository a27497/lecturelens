"""Compare filled human verdicts with the conservative two-pass reviewer verdict."""

import argparse
import json
from pathlib import Path

VERDICTS = {"supported", "unsupported", "unclear"}


def agreement(directory, human):
    directory = Path(directory)
    keys = set()
    for line in (directory / "generations.jsonl").read_text().splitlines():
        row = json.loads(line)
        keys.update(f"{row['task']['task_id']}:{i}" for i in range(len(row["cards"])))
    reviewer = dict.fromkeys(keys, "unclear")
    for line in (directory / "reviews.jsonl").read_text().splitlines():
        row = json.loads(line)
        passes = [
            {c["index"]: c["verdict"] for c in p["checks"]} for p in row["passes"]
        ]
        for key in keys:
            task_id, index = key.rsplit(":", 1)
            if task_id != row["task_id"]:
                continue
            verdicts = [p.get(int(index)) for p in passes]
            if (
                len(verdicts) == 2
                and verdicts[0] in VERDICTS
                and verdicts[0] == verdicts[1]
            ):
                reviewer[key] = verdicts[0]
    if (
        not isinstance(human, dict)
        or not human
        or any(k not in keys or v not in VERDICTS for k, v in human.items())
    ):
        raise ValueError(
            "Expected nonempty {card_key: supported|unsupported|unclear} for this run"
        )
    matches = sum(v == reviewer[k] for k, v in human.items())
    return {
        "n": len(human),
        "matches": matches,
        "human_vs_reviewer_agreement": matches / len(human),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("human_verdicts", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            agreement(args.directory, json.loads(args.human_verdicts.read_text()))
        )
    )
