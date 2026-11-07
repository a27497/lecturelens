"""Import immutable v1 evaluation components, never a product factory."""

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT / "eval/tutor-scale"
sys.path.insert(0, str(BASE))
import run as legacy  # noqa: E402
from blind import validate_rating as validate_citations  # noqa: E402
from dataset import digest, load, write  # noqa: E402
from scoring import agreement  # noqa: E402
from scoring import metrics as citation_metrics  # noqa: E402

__all__ = [
    "BASE",
    "HERE",
    "ROOT",
    "legacy",
    "digest",
    "load",
    "write",
    "validate_citations",
    "agreement",
    "citation_metrics",
    "object_hash",
    "read",
    "jsonl",
    "verify_tooling",
]


def object_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def jsonl(path):
    path = Path(path)
    return (
        [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    )


def verify_tooling():
    legacy.preflight(False, None)
    frozen = read(HERE / "candidate.json")
    for name, expected in frozen["files"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("V2_FROZEN_INPUT_CHANGED")
    return digest(HERE / "candidate.json")
