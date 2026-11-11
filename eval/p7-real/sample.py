"""Fixed-seed sample of ten generated cards, including exact source text."""

import argparse
import json
import random
from pathlib import Path


def sample(directory, seed=20261027):
    directory = Path(directory)
    cards = []
    for line in (directory / "generations.jsonl").read_text().splitlines():
        row = json.loads(line)
        cards.extend((row["task"]["task_id"], c) for c in row["cards"])
    chosen = random.Random(seed).sample(cards, min(10, len(cards)))
    text = [f"# P7 card sample (seed={seed}; {len(chosen)} cards)", ""]
    for i, (task, card) in enumerate(chosen, 1):
        text += [f"## {i}. {task}", "", card["front"], "", card["back"], ""]
        for e in card["citations"]:
            text += [
                f"Source: {e['evidence_id']} (page {e['page']})",
                "",
                e["text"],
                "",
            ]
    (directory / "sample.md").write_text("\n".join(text), encoding="utf-8")
    return len(chosen)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    sample(parser.parse_args().directory)
