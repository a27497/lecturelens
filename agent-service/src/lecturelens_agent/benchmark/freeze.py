"""Freeze a new benchmark before the first scored query. Existing freezes are never replaced."""

import argparse
import json
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from .core import digest, validate_dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args()
    dataset = args.dataset.resolve()
    root = dataset.parents[1]
    validate_dataset(
        json.loads((dataset / "corpus.json").read_text()), json.loads((dataset / "cases.json").read_text())
    )
    files = [
        dataset / name
        for name in ("corpus.json", "cases.json", "config.json", "PROTOCOL.md", "pyproject.toml", "uv.lock")
    ]
    package = root / "agent-service/src/lecturelens_agent"
    files += sorted((package / "benchmark").glob("*.py"))
    files += [package / name for name in ("embedding.py", "retrieval.py", "contracts.py", "store.py")]
    frozen = {
        "id": "retrieval-phase-a-v1",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "files": {str(p.relative_to(root)): digest(p) for p in files},
        "packages": {
            p: version(p)
            for p in (
                "fastembed",
                "onnxruntime",
                "torch",
                "transformers",
                "psycopg",
                "numpy",
                "pydantic",
                "huggingface-hub",
                "tokenizers",
            )
        },
        "scope": "Fixed diagnostic on previously seen public course excerpts; not an independent holdout or Study Agent acceptance.",
    }
    with (dataset / "freeze.json").open("x") as output:
        output.write(json.dumps(frozen, indent=2) + "\n")
    print(digest(dataset / "freeze.json"))


if __name__ == "__main__":
    main()
