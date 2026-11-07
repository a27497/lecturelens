"""Reuse the pinned eight-turn runner without importing mixed-split authoring data."""

import ast
import hashlib
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "eval/tutor-public-v1"


def no_old_scope(*args, **kwargs):
    raise ValueError("MIXED_OR_OLD_SCOPE_LOADING_DISABLED")


def reject_holdout_open(event, args):
    if event != "open" or not isinstance(args[0], (str, bytes)):
        return
    path = Path(args[0].decode() if isinstance(args[0], bytes) else args[0]).resolve()
    if path.parent == PUBLIC and path.name in {
        "author_public.py",
        "snapshot.json",
        "holdout.json",
    }:
        raise PermissionError("NO_MIXED_AUTHORING_OR_HOLDOUT_READ")
    if path.parent == PUBLIC / "materials" and path.name.startswith("carpentries-sql"):
        raise PermissionError("NO_SQL_MATERIAL_READ")
    if path.parent == PUBLIC / "__pycache__" and path.name.startswith("author_public."):
        raise PermissionError("NO_MIXED_AUTHORING_IMPORT")


sys.addaudithook(reject_holdout_open)
# Public v1 imports all questions eagerly. Extract only its unchanged pure utilities,
# not author_public or project/load/select. Old selection fails before any source read.
pure = {"read", "digest", "object_hash", "write", "expected_rows"}
module = types.ModuleType("public_dataset")
module.__dict__.update(
    Path=Path,
    hashlib=hashlib,
    json=json,
    HERE=PUBLIC,
    ROOT=ROOT,
    VERSION="tutor-public-v1",
    select=no_old_scope,
    load=no_old_scope,
)
path = PUBLIC / "public_dataset.py"
if (
    hashlib.sha256(path.read_bytes()).hexdigest()
    != "99fce2f7532bf19801050516322818454b5cfe8471d5e1e68382a58612b67b7b"
):
    raise ValueError("PUBLIC_UTILITY_SOURCE_CHANGED")
tree = ast.parse(path.read_text())
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in pure]
if {n.name for n in functions} != pure:
    raise ValueError("PUBLIC_UTILITY_CONTRACT_CHANGED")
exec(  # noqa: S102 -- only pinned pure utility function AST nodes; no authoring imports
    compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"),
    module.__dict__,
)
sys.modules["public_dataset"] = module
sys.path.insert(1, str(ROOT / "eval/tutor-repair-v1"))
import repair_check
import repair_run
from public_bridge import execution_counts, failure_items, legacy, summarize
from public_mock import reconcile

__all__ = [
    "PUBLIC",
    "execution_counts",
    "failure_items",
    "legacy",
    "module",
    "reconcile",
    "repair_check",
    "repair_run",
    "summarize",
    "verify_candidate",
]


def verify_candidate():
    actual = repair_check.verify_candidate()
    if actual != "b7fe50df1854703cc05d4ad039dad3245cc62adc5d68c3af7b394f2407f0ec58":
        raise ValueError("NOT_FROZEN_V11")
    return actual
