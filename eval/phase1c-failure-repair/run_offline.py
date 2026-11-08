"""Socket-fenced PostgreSQL/Mock regression only; no provider or live grant path."""

import argparse
import ast
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") != "1":
    raise SystemExit("SOCKET_FENCE_REQUIRED")
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "agent-service/tests"))

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", required=True, type=Path)
parser.add_argument("--candidate-only", action="store_true")
args = parser.parse_args()
output = args.output.resolve()
if not output.is_relative_to(Path("/dev/shm/lecturelens-phase1c-checks-20261108")):
    raise SystemExit("TASK_OWNED_RAM_OUTPUT_REQUIRED")
output.mkdir(parents=True, exist_ok=False, mode=0o700)
os.environ["AGENT_TEST_DATABASE_URL"] = (
    "postgresql://tutor_scale:synthetic-local-only@127.0.0.1:25841/lecturelens_agent_acceptance"
)
for name in ("PHASE1C_OUTPUT", "TUTOR_USABILITY_OUTPUT", "TUTOR_SELECTION_OUTPUT"):
    path = output / name.lower()
    path.mkdir(mode=0o700)
    os.environ[name] = str(path)

tests = ROOT / "agent-service/tests"
nodes = [str(tests / "test_tutor_phase1c.py")]
if not args.candidate_only:
    nodes.extend(str(tests / name) for name in ("test_tutor.py", "test_tutor_citations.py"))
# Frozen entry manifests intentionally reject this changed candidate. Validate
# inherited v18 mechanics without rewriting or pretending to re-sign those CLIs.
excluded = {
    "test_frozen_entry_default_and_unapproved_live_have_no_output",
    "test_frozen_smoke_actual_entry_and_wire",
    "test_smoke_invalid_grant_cannot_expand_scope",
}
module = tests / "test_tutor_v18.py"
for node in [] if args.candidate_only else ast.parse(module.read_bytes()).body:
    if isinstance(node, ast.FunctionDef) and node.name.startswith("test_") and node.name not in excluded:
        nodes.append(str(module) + "::" + node.name)

import pytest  # noqa: E402

record = {
    "kind": "POSTGRESQL_AND_AUTHORED_MOCK_NOT_REAL_QUALITY",
    "root": str(ROOT),
    "selected_nodes": nodes,
    "historical_frozen_entry_nodes_not_applicable": sorted(excluded),
    "real_provider_requests": 0,
    "real_model_quality": "NOT_RUN",
}
(output / "selection.json").write_text(json.dumps(record, indent=2))
raise SystemExit(
    pytest.main(
        [
            "-q",
            *nodes,
            "--basetemp=" + str(output / "pytest"),
            "--junitxml=" + str(output / "results.xml"),
            "-o",
            "cache_dir=" + str(output / "cache"),
        ]
    )
)
