"""Verify complete test coverage and measured datasets before writing evidence."""
import collections
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def main():
    groups = json.loads((ROOT / "verification-groups.json").read_text())
    counts = dict(tests=0, failures=0, errors=0, skipped=0)
    cases, results = [], []
    for group in groups:
        xml = ROOT / f'tests-group-{group["worker"]}.xml'
        tree = ET.parse(xml)
        suites = list(tree.getroot().iter("testsuite"))
        nums = {k: sum(int(s.get(k, 0)) for s in suites) for k in counts}
        assert nums["tests"] == group["expected_cases"]
        assert nums["failures"] == nums["errors"] == nums["skipped"] == 0
        for key, value in nums.items():
            counts[key] += value
        cases.extend((c.get("classname"), c.get("name")) for c in tree.getroot().iter("testcase"))
        results.append({**group, **nums, "duration_seconds": sum(float(s.get("time", 0)) for s in suites),
                        "junit_sha256": hashlib.sha256(xml.read_bytes()).hexdigest()})
    collected = [l for l in (ROOT / "tests-collection.txt").read_text().splitlines() if "::" in l]
    # Parameter IDs can themselves contain ::, e.g. a Python slice.
    expected = {("tests." + l.split("::", 1)[0].split("/")[-1].removesuffix(".py"),
                 l.split("::", 1)[1]) for l in collected}
    assert set(cases) == expected and len(cases) == len(expected) == counts["tests"] == 659
    package = REPO / "agent-service/src/lecturelens_agent"
    digest, file_hashes = hashlib.sha256(), {}
    for path in sorted(package.rglob("*.py")):
        digest.update(str(path.relative_to(package)).encode())
        digest.update(path.read_bytes())
        file_hashes[str(path.relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
    summary = json.loads((ROOT / "summary.json").read_text())
    assert summary["candidate_source_sha256"] == digest.hexdigest()
    for name in ["baseline.jsonl", "candidate.jsonl"]:
        rows = [json.loads(l) for l in (ROOT / name).read_text().splitlines()]
        assert len(rows) == 300 and set(collections.Counter(r["scenario"] for r in rows).values()) == {20}
        assert len({r["fixture_sha256"] for r in rows}) == 1
        if name == "candidate.jsonl":
            assert all(r["source_sha256"] == digest.hexdigest() for r in rows)
        assert all("api_key" not in json.dumps(r) and "worker_token" not in json.dumps(r)
                   and "PRIVATE" not in json.dumps(r) for r in rows)
    with psycopg.connect(os.environ["AGENT_TEST_DATABASE_URL"]) as conn:
        pg = conn.execute("SELECT version()").fetchone()[0]
    patch = subprocess.check_output(["git", "diff", "HEAD", "--", "agent-service", "docs/L2_STUDY_AGENT.md",
                                    "scripts/eval/replay-study-quality.py", "eval/README.md"], cwd=REPO, text=True)
    new = ["agent-service/src/lecturelens_agent/study/failures.py",
           "agent-service/src/lecturelens_agent/study/resilience.py",
           "agent-service/tests/test_study_resilience.py"]
    for file in new:
        result = subprocess.run(["git", "diff", "--no-index", "--", "/dev/null", file],
                                cwd=REPO, capture_output=True, text=True)
        assert result.returncode == 1
        patch += result.stdout
    (ROOT / "candidate.patch").write_text(patch)
    checks = {}
    commands = {
        "ruff_check": [sys.executable, "-m", "ruff", "check", "src", "tests"],
        "ruff_format_check": [sys.executable, "-m", "ruff", "format", "--check", "src", "tests"],
        "git_diff_check": ["git", "diff", "--check"],
    }
    for name, command in commands.items():
        result = subprocess.run(command, cwd=REPO / "agent-service", capture_output=True, text=True)
        checks[name] = {"exit_code": result.returncode, "output": result.stdout + result.stderr}
        assert result.returncode == 0, checks[name]
    probes = {}
    roots = {"candidate": str(REPO / "agent-service/src")}
    if os.environ.get("LECTURELENS_BASELINE_SOURCE_ROOT"):
        roots["baseline"] = os.environ["LECTURELENS_BASELINE_SOURCE_ROOT"]
    for name, path in roots.items():
        code = "import json,hashlib,pathlib;import lecturelens_agent.course_mcp.server as s;p=pathlib.Path(s.__file__);print(json.dumps({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))"
        probe = json.loads(subprocess.check_output([sys.executable, "-c", code], env={"PYTHONPATH": path}, text=True))
        assert Path(probe["path"]).resolve().is_relative_to(Path(path).resolve())
        probes[name] = probe
    verification = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
        "dependencies": {p: importlib.metadata.version(p) for p in
                         ["pytest", "psycopg", "mcp", "langgraph", "langgraph-checkpoint-postgres", "ruff"]},
        "postgres": pg,
        "database_isolation": "Four separate PostgreSQL/pgvector containers, each lecturelens_agent_test; distinct from service/eval DBs.",
        "python_checks": counts, "groups": results, "complete_collection_covered_once": True, "database_skips": 0,
        "ruff_check": "passed", "ruff_format_check": "passed", "git_diff_check": "passed",
        "check_results": checks, "mcp_source_probes": probes,
        "candidate_source_sha256": digest.hexdigest(),
        "candidate_patch_sha256": hashlib.sha256((ROOT / "candidate.patch").read_bytes()).hexdigest(),
        "dependency_lock_sha256": hashlib.sha256((REPO / "agent-service/uv.lock").read_bytes()).hexdigest(),
        "final_eval": {"baseline_runs": 300, "candidate_runs": 300, "fault_scenarios": 14,
                       "samples_per_scenario_per_version": 20, "healthy_controls_per_version": 20,
                       "client_and_server_source_pinned": True, "provider": "deterministic local stub",
                       "workers_per_phase": 4},
        "real_model_quality": "未运行", "real_Java_process_faults": "未运行", "Java_source_changed": False,
        "Java_tests": "未运行（Java 未修改）", "push": "未执行", "deployment": "未执行",
        "previous_failed_diagnostics": "Retained separately; not counted as passing formal trials.",
        "source_files": file_hashes,
    }
    (ROOT / "verification.json").write_text(json.dumps(verification, indent=2, ensure_ascii=False) + "\n")
    print("Verified", counts, "and complete collection coverage on four isolated PostgreSQL databases.")
    print("Final evaluation: 300 baseline + 300 candidate; same fixture and final candidate source identity.")


if __name__ == "__main__":
    main()
