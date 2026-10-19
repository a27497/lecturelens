#!/usr/bin/env python3
"""Read-only recomputation of this acceptance package; no database required."""

import collections
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

REPORT = Path(__file__).resolve().parent
ROOT = REPORT.parents[1]


def load(name):
    return json.loads((REPORT / name).read_text())


def rows(name):
    return [json.loads(line) for line in (REPORT / name).read_text().splitlines()]


def outcome(row):
    state = row["after"]
    return "deleted" if state.get("deleted") else state["error_code"] or state["status"]


def summarize(group):
    times = sorted(row["recovery_ms"] for row in group)
    return {
        "n": len(group),
        "passed": sum(row["passed"] for row in group),
        "p50_ms": times[math.ceil(len(times) * 0.50) - 1],
        "p95_ms": times[math.ceil(len(times) * 0.95) - 1],
        "outcomes": dict(collections.Counter(map(outcome, group))),
    }


def junit(paths):
    cases = [case for path in paths for case in ET.parse(path).iter("testcase")]
    return cases, {
        "tests": len(cases),
        "failures": sum(case.find("failure") is not None for case in cases),
        "errors": sum(case.find("error") is not None for case in cases),
        "skipped": sum(case.find("skipped") is not None for case in cases),
    }


def main():
    matrix = rows("matrix-final/raw.jsonl")
    approval = rows("approval-decisions/raw.jsonl")
    published = load("RESULTS.json")
    assert len({(r["profile"], r["point"]) for r in matrix}) == len(matrix) == 523
    combinations = collections.Counter(
        (r["kind"], r["decision"], r["point"]) for r in approval
    )
    assert len(combinations) == 18 and set(combinations.values()) == {3}
    cap = [
        r
        for r in matrix
        if (r["profile"], r["point"]) == ("retry_cap", "SEARCH:three_crashes")
    ]
    assert len(cap) == 1
    for row in matrix + approval:
        assert row["passed"] and all(value is True for value in row["checks"].values())
        key = "three_injections" if row is cap[0] else "injection_reached"
        assert row["checks"][key] is True
    driver = ROOT / "scripts/eval/check-study-crash-matrix.py"
    expected_sha = load("verification-static-final.json")["source_sha256"][
        str(driver.relative_to(ROOT))
    ]
    assert hashlib.sha256(driver.read_bytes()).hexdigest() == expected_sha
    assert (
        'checks["three_injections"] = codes == [-signal.SIGKILL] * 3'
        in driver.read_text()
    )
    assert cap[0]["checks"]["persistent_cap"] is True
    for raw, saved, keys in (
        (matrix, load("matrix-final/summary.json"), ("profile", "point")),
        (
            approval,
            load("approval-decisions/summary.json"),
            ("kind", "decision", "point"),
        ),
    ):
        grouped = collections.defaultdict(list)
        for row in raw:
            grouped[tuple(row[k] for k in keys)].append(row)
        assert len(grouped) == len(saved)
        for entry in saved:
            computed = summarize(grouped[tuple(entry[k] for k in keys)])
            for key in ("n", "passed"):
                assert entry[key] == computed[key]
            for p in (50, 95):
                assert entry[f"recovery_p{p}_ms"] == computed[f"p{p}_ms"]
    m, a = summarize(matrix), summarize(approval)
    for label, computed in (("matrix", m), ("approval_repeats", a)):
        for key in ("n", "passed", "p50_ms", "p95_ms"):
            assert published[label][key] == computed[key]
    totals = summarize(matrix + approval)
    assert totals["n"] == totals["passed"] == published["all_planned_trials"] == 577
    assert (
        totals["outcomes"]["MODEL_OUTCOME_UNKNOWN"]
        == published["unknown_model_outcome"]
        == 96
    )
    assert totals["outcomes"]["succeeded"] == published["published_success"] == 456
    assert (
        totals["outcomes"]["APPROVAL_REJECTED"] == published["explicit_rejection"] == 18
    )
    cases, python = junit(sorted((REPORT / "tests").glob("group-*.xml")))
    collected = (REPORT / "tests/collected.txt").read_text().splitlines()
    actual = [
        c.attrib["classname"].replace(".", "/") + ".py::" + c.attrib["name"]
        for c in cases
    ]
    assert collections.Counter(actual) == collections.Counter(collected)
    assert len(set(actual)) == 727
    assert python == load("tests/verification.json")["full_python"]
    approval_tests = sum("test_study_approval" in c.attrib["classname"] for c in cases)
    assert approval_tests == 23
    _, java = junit(sorted((REPORT / "browser-evidence/java").glob("*.xml")))
    assert java == {"tests": 12, "failures": 0, "errors": 0, "skipped": 0}
    frontend = load("frontend-tests.json")
    assert frontend["numTotalTests"] == frontend["numPassedTests"] == 99
    assert frontend["numFailedTests"] == frontend["numPendingTests"] == 0
    browser_checks = (
        load("browser-final.json")["checks"]
        + load("browser-feedback-final.json")["checks"]
    )
    assert len(browser_checks) == sum(c["passed"] for c in browser_checks) == 7
    for entry in load("browser-evidence/manifest.json")["files"]:
        assert (
            hashlib.sha256((REPORT / entry["file"]).read_bytes()).hexdigest()
            == entry["sha256"]
        )
    print(
        json.dumps(
            {
                "matrix": m,
                "approval": a,
                "planned_trials": totals["n"],
                "passed": totals["passed"],
                "outcomes": totals["outcomes"],
                "main_distinct_points": len(matrix),
                "approval_combinations": len(combinations),
                "approval_trials_per_combination": 3,
                "retry_cap": {
                    "n": 1,
                    "same_run_sigkill_count_checked": 3,
                    "three_injections": cap[0]["checks"]["three_injections"],
                    "driver_sha256_matches_original": True,
                },
                "python": python,
                "approval_tests_in_full_suite": approval_tests,
                "java": java,
                "frontend_passed": 99,
                "browser_passed": 7,
                "saved_screenshots": 6,
                "summaries_match_raw": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
