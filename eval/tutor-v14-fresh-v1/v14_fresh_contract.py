"""Bind the unchanged v14 identity to sixteen new, source-reviewed development positions."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(1, str(ROOT / "eval/tutor-v14-offline-v1"))
import v14_contract as candidate  # noqa: E402 -- parent installs source/holdout fence

CANDIDATE, ENTRYPOINT = candidate.CANDIDATE, candidate.ENTRYPOINT
digest = candidate.digest
bridge, data = candidate.historical.bridge, candidate.historical.data


def verify_candidate():
    return candidate.verify_offline()


def verify():
    identity = verify_candidate()
    previous = ROOT / "eval/tutor-v14-offline-v1/VERIFICATION.json"
    record = json.loads(previous.read_text())
    raw = ROOT / record["raw_root"]
    if (
        record["tests"]["collected"] != 219
        or record["tests"]["passed"] != 219
        or any(record["tests"][k] for k in ("failed", "errors", "skipped"))
        or record["candidate_sha256"] != identity
        or digest(raw / "artifact-manifest.json") != record["raw_manifest_sha256"]
        or any(digest(raw / p) != h for p, h in data.read(raw / "artifact-manifest.json")["files"].items())
    ):
        raise ValueError("V14_OFFLINE_EVIDENCE_MISMATCH")
    lock = data.read(HERE / "freeze-lock.json")
    files = {
        "sources.json",
        "questions.json",
        "development.json",
        "snapshot.json",
        "grading-rules.json",
        "CONTENT_REVIEW.json",
        "run-plan.json",
        "adapter-lock.json",
        "run_fresh.py",
        "v14_fresh_contract.py",
        "test_fresh.py",
        "EXECUTION_SHEET.md",
    }
    if set(lock["files"]) != files or any(digest(HERE / p) != h for p, h in lock["files"].items()):
        raise ValueError("V14_FRESH_FREEZE_CHANGED")
    adapter = data.read(HERE / "adapter-lock.json")
    if (
        adapter["candidate_sha256"] != identity
        or adapter["parent_runner_sha256"] != digest(ROOT / "eval/tutor-v13-grounding-v2/trial_run_v2.py")
        or any(digest(HERE / p) != h for p, h in adapter["files"].items())
    ):
        raise ValueError("V14_FRESH_ADAPTER_CHANGED")
    plan = data.read(HERE / "run-plan.json")
    protocol = data.read(ROOT / "eval/tutor-v12-rerun-v1/protocol.json")
    if (
        plan["candidate"] != CANDIDATE
        or plan["candidate_sha256"] != identity
        or plan["protocol_sha256"] != digest(ROOT / "eval/tutor-v12-rerun-v1/protocol.json")
        or any(digest(HERE / p) != h for p, h in plan["original_inputs"].items())
    ):
        raise ValueError("V14_FRESH_PLAN_CHANGED")
    sources = data.read(HERE / "sources.json")["sources"]
    if len(sources) != 2 or {s["course_id"] for s in sources} != {
        "carpentries-python",
        "carpentries-spreadsheets",
    }:
        raise ValueError("V14_DEVELOPMENT_ONLY")
    source_by_course = {}
    for source in sources:
        if source["split"] != "development":
            raise ValueError("V14_NO_HOLDOUT")
        for p, h in (("local_path", "sha256"), ("license_local_path", "license_sha256")):
            if digest(HERE / source[p]) != source[h]:
                raise ValueError("V14_SOURCE_CHANGED")
        source_by_course[source["course_id"]] = (HERE / source["local_path"]).read_text().splitlines()
    snapshot = data.read(HERE / "snapshot.json")
    scripts = data.read(HERE / "development.json")["dialogues"]
    if set(snapshot["lectures"]) != set(source_by_course):
        raise ValueError("V14_SNAPSHOT_SCOPE_CHANGED")
    for script in scripts:
        for task in script["turns"]:
            for quote in task["reference"]["quotes"]:
                text = source_by_course[script["course_id"]]
                if quote["quote"] != "\n".join(text[quote["line_start"] - 1 : quote["line_end"]]):
                    raise ValueError("V14_REFERENCE_SOURCE_MISMATCH")
    expected = bridge.module.expected_rows(snapshot, scripts)
    if (
        len(scripts) != 4
        or len(expected) != 16
        or [e["turn_key"] for e in expected] != plan["turn_keys"]
        or sum(t["script"]["expected_insufficient"] for t in expected) != 4
    ):
        raise ValueError("V14_FRESH_SCOPE_CHANGED")
    return plan, scripts, snapshot, expected, protocol
