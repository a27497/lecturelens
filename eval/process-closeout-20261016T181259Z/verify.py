#!/usr/bin/env python3
"""Verify archived results and hashes without signaling processes or starting services."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    result = json.loads((PUBLIC / "test-result.json").read_text())
    raw = json.loads((PUBLIC / "raw-files.json").read_text())
    for row in raw:
        assert digest(ROOT / row["path"]) == row["sha256"], row["path"]
    for name, value in result["source_sha256"].items():
        assert digest(ROOT / name) == value, name
    assert digest(ROOT / result["log_path"]) == result["log_sha256"]
    assert digest(ROOT / result["runner_record_path"]) == result["runner_record_sha256"]
    record = json.loads((ROOT / result["runner_record_path"]).read_text())
    assert record["status"] == "SUCCEEDED" and record["exit_code"] == 0
    assert record["cleanup"]["complete"] and not record["cleanup"]["remaining"]
    match = re.search(r"Ran (\d+) tests in ([\d.]+)s\n\nOK\s*$", (ROOT / result["log_path"]).read_text())
    assert match and int(match[1]) == result["tests"] and float(match[2]) == result["test_seconds"]
    assert result["failures"] == result["errors"] == result["skipped"] == 0
    legacy = json.loads((PUBLIC / "legacy-reproduction.json").read_text())
    assert all(row["probe_cleanup_complete"] and row["leftovers_before_probe_cleanup"] for row in legacy["cases"])
    closeout = json.loads((PUBLIC / "closeout-final.json").read_text())
    assert closeout["existing_chain_identity_and_state_unchanged"] and not closeout["existing_processes_signaled"]
    assert closeout["live_backend_identity_unchanged"] and closeout["candidate_jar_unchanged"]
    before = json.loads((PUBLIC / "before.json").read_text())
    assert digest(ROOT / ".data/p2-1c-20261016T155847Z/candidate/backend.jar") == before["candidate_jar_sha256"]
    print(json.dumps({"tests": result["tests"], "failures": 0, "errors": 0, "skipped": 0,
                      "legacy_defects_reproduced": len(legacy["cases"]), "hashes_verified": True,
                      "scope": "archived synthetic process checks; no existing process cleanup performed"}))


if __name__ == "__main__":
    main()
