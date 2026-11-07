"""Additive pre-live reference-locator correction; v13 behavior and task gate unchanged."""

import copy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(1, str(ROOT / "eval/tutor-v13-grounding-v1"))
import v13_contract as candidate  # noqa: E402 -- immutable v13 candidate and source fence

CANDIDATE, ENTRYPOINT = candidate.CANDIDATE, candidate.ENTRYPOINT
parent, bridge, data, digest = candidate.parent, candidate.bridge, candidate.data, candidate.digest
verify_candidate = candidate.verify_candidate


def verify():
    base, scripts, snapshot, _, protocol = candidate.verify()
    lock = data.read(HERE / "freeze-lock.json")
    if any(digest(HERE / p) != h for p, h in lock["files"].items()):
        raise ValueError("V13_V2_FROZEN_INPUT_CHANGED")
    patch = data.read(HERE / "reference-locators.json")
    if patch["base_freeze_sha256"] != digest(candidate.HERE / "freeze-lock.json"):
        raise ValueError("V13_V2_BASE_CHANGED")
    scripts = copy.deepcopy(scripts)
    sources = {s["course_id"]: s for s in data.read(candidate.HERE / "sources.json")["sources"]}
    for s in scripts:
        source = sources[s["course_id"]]
        raw = (candidate.HERE / source["local_path"]).read_text().splitlines()
        for n, task in enumerate(s["turns"], 1):
            key = f"{s['dialogue_id']}:{n}"
            if key not in patch["ranges"]:
                continue
            ranges = patch["ranges"][key]
            task["reference"]["source_ranges"] = ranges
            task["reference"]["quotes"] = [
                dict(
                    line_start=a,
                    line_end=b,
                    quote="\n".join(raw[a - 1 : b]),
                    locator=source["repository_source_url"] + f"#L{a}-L{b}",
                )
                for a, b in ranges
            ]
            task["reference"]["evidence_ids"] = (
                []
                if task["expected_insufficient"]
                else [
                    e["evidence_id"]
                    for e in snapshot["lectures"][s["lecture_id"]]["evidence"]
                    if any(e["line_start"] <= b and e["line_end"] >= a for a, b in ranges)
                ]
            )
    plan = data.read(HERE / "run-plan.json")
    if plan["candidate_sha256"] != verify_candidate() or plan["candidate"] != CANDIDATE:
        raise ValueError("V13_V2_IDENTITY_CHANGED")
    expected = bridge.module.expected_rows(snapshot, scripts)
    if [r["turn_key"] for r in expected] != base["turn_keys"] or plan["turn_keys"] != base["turn_keys"]:
        raise ValueError("V13_V2_SCOPE_CHANGED")
    if data.read(HERE / "grading-rules.json") != data.read(candidate.HERE / "grading-rules.json"):
        raise ValueError("V13_V2_GRADING_CHANGED")
    return plan, scripts, snapshot, expected, protocol
