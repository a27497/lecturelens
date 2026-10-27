"""Print N seeded dialogues, including canonical source text. No provider calls."""

import argparse
import json
import random
from pathlib import Path


def sample(directory, count=5):
    rows = [
        json.loads(line)
        for line in (Path(directory) / "dialogues.jsonl").read_text().splitlines()
    ]
    for d in random.Random(20261027).sample(rows, min(count, len(rows))):
        print(f"\n{d['dialogue_id']}")
        for t in d["turns"]:
            print(
                f"Learner: {t['learner_text']}\nTutor ({t['outcome']}): {t['answer']}"
            )
            if t.get("evaluation"):
                print("Feedback:", t["evaluation"])
            for c in t["citations"]:
                print(f"[{c['evidence_id']}] page {c.get('page', '?')}: {c['text']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory", nargs="?", type=Path, default=Path(__file__).parent
    )
    parser.add_argument("-n", type=int, default=5)
    args = parser.parse_args()
    sample(args.directory, args.n)
