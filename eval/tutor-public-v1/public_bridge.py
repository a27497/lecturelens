"""Reuse frozen synthetic-suite mechanisms without inheriting its dataset scope."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(1, str(ROOT / "eval/tutor-scale-v2"))
from records import execution_counts, failure_items
from review import bound_ratings, import_annotations
from shared import legacy, verify_tooling
from task_scores import summarize

__all__ = [
    "bound_ratings",
    "execution_counts",
    "failure_items",
    "import_annotations",
    "legacy",
    "summarize",
    "verify_tooling",
]
