"""Export a fixed, blinded ten-card human audit with authoritative cited text."""

import argparse
import json
import random
from pathlib import Path


def sample(directory, seed=20261028):
    directory = Path(directory)
    cards = []
    for line in (directory / "generations.jsonl").read_text().splitlines():
        row = json.loads(line)
        cards.extend(
            (f"{row['task']['task_id']}:{i}", c) for i, c in enumerate(row["cards"])
        )
    chosen = random.Random(seed).sample(cards, min(10, len(cards)))
    text = [f"# P7 hardening human audit (seed={seed}; n={len(chosen)})", ""]
    for i, (key, card) in enumerate(chosen, 1):
        text += [
            f"## {i}. {key}",
            "",
            "| Card key | Human verdict |",
            "| --- | --- |",
            f"| {key} | |",
            "",
            "Front:",
            "",
            card["front"],
            "",
            "Back:",
            "",
            card["back"],
            "",
        ]
        for source in card["citations"]:
            text += [
                f"Source: {source['evidence_id']} (page {source['page']})",
                "",
                source["text"],
                "",
            ]
    (directory / "sample.md").write_text("\n".join(text), encoding="utf-8")
    # Blank values are deliberately invalid until the human supplies a verdict.
    template = directory / "human-verdicts.template.json"
    if not template.exists():
        template.write_text(
            json.dumps(dict.fromkeys((key for key, _ in chosen), ""), indent=2) + "\n"
        )
    return len(chosen)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    sample(parser.parse_args().directory)
