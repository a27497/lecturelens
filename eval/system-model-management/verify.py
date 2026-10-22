"""Recompute the frozen P1-4 acceptance evidence; never calls providers or modifies a database."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import wave
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "eval/system-model-management"
RAW = ROOT / ".data/system-model-management/phase4"
COUNT_KEYS = ("tests", "failures", "errors", "skipped")
CANARIES = [
    b"synthetic-env-text-key-5531",
    b"synthetic-env-vision-key-6942",
    b"synthetic-provider-a-key-1984",
    b"synthetic-provider-b-key-2756",
    b"synthetic-http-test-key",
    b"test-only-opaque-model-secret-9347",
    b"test-only-database-secret-8472",
    b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    b"synthetic-asr-a-key-1264",
    b"synthetic-asr-b-key-9857",
    b"synthetic-probe-key-4268",
    b"private-probe-transcript",
    b"synthetic-browser-secret-2468",
    b"private-provider-key",
    b"model-management-test-secret-with-32-bytes",
]


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def counts(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {key: sum(int(s.get(key, "0")) for s in suites) for key in COUNT_KEYS}


def java_result(result: dict) -> list[dict]:
    text = (ROOT / result["log"]).read_text()
    assert "[INFO] BUILD SUCCESS" in text
    names = re.findall(r"^\[INFO\] Running (\S+)", text, re.M)
    suites = [
        {"name": name, **counts(ROOT / result["junit_xml"] / f"TEST-{name}.xml")}
        for name in names
    ]
    assert len(suites) == result["suite_count"]
    totals = {key: sum(s[key] for s in suites) for key in COUNT_KEYS}
    assert totals == {key: result[key] for key in COUNT_KEYS}
    matches = re.findall(
        r"^\[INFO\] Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)\s*$",
        text,
        re.M,
    )
    assert (
        len(matches) == 1
        and dict(zip(COUNT_KEYS, map(int, matches[0]), strict=True)) == totals
    )
    return suites


def scan_files() -> list[Path]:
    files = [
        RAW / name
        for name in (
            "backend-full-final.log",
            "backend-package-final.log",
            "frontend-full-final.log",
            "frontend-final.xml",
            "frontend-build-final.log",
            "python-final.log",
            "python-final.xml",
            "ruff-check-final.log",
            "ruff-format-final.log",
            "browser/results.json",
            "browser/check-final.log",
        )
    ]
    return (
        files
        + sorted((RAW / "full-final-reports").glob("TEST-*.xml"))
        + sorted((RAW / "observations-final").glob("*.jsonl"))
    )


def check_manifest(path: Path, commit: str | None = None) -> int:
    lines = path.read_text().splitlines()
    for line in lines:
        digest, name = line.split("  ", 1)
        data = (
            subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=ROOT)
            if commit
            else (ROOT / name).read_bytes()
        )
        assert hashlib.sha256(data).hexdigest() == digest, name
    return len(lines)


def verify(pre_commit: bool = False) -> dict:
    summary = read(PUBLIC / "results.json")
    phase = read(PUBLIC / "phase4/results.json")
    for entry in summary["stages"][:3]:
        old = read(PUBLIC / f"phase{entry['phase']}/results.json")
        java_result(old["backend_full"])
        assert (
            subprocess.check_output(
                ["git", "rev-parse", entry["commit"]], cwd=ROOT, text=True
            ).strip()
            == entry["commit"]
        )
        check_manifest(PUBLIC / f"phase{entry['phase']}/SHA256SUMS", entry["commit"])
        check_manifest(PUBLIC / f"phase{entry['phase']}/RAW_SHA256SUMS")
    suites = java_result(phase["backend_full"])
    assert [s for s in suites if ".systemmodel." in s["name"]] == phase[
        "system_model_suites"
    ]
    assert (
        sum(
            s["tests"]
            for s in suites
            if s["name"].endswith(
                (
                    "SystemModelMySqlIntegrationTest",
                    "SystemModelRuntimeMySqlTest",
                    "SystemModelAsrMySqlTest",
                    "SystemModelProbeMySqlTest",
                )
            )
        )
        == phase["real_mysql_tests"]
    )
    for field in ("frontend", "python"):
        assert counts(ROOT / phase[field]["junit_xml"]) == {
            key: phase[field][key] for key in COUNT_KEYS
        }
    assert (
        len(ET.parse(RAW / "frontend-final.xml").getroot().findall("testsuite"))
        == phase["frontend"]["test_files"]
    )
    assert (
        f"{phase['python']['tests']} passed, {phase['python']['warnings']} warning"
        in (RAW / "python-final.log").read_text()
    )
    frontend_cases = Counter(
        t.get("classname")
        for t in ET.parse(RAW / "frontend-final.xml").getroot().iter("testcase")
    )
    python_cases = Counter(
        t.get("classname")
        for t in ET.parse(RAW / "python-final.xml").getroot().iter("testcase")
    )
    assert (
        frontend_cases["src/views/ModelManagementView.test.ts"]
        == phase["personal_models"]["frontend_tests"]
    )
    assert python_cases["tests.test_models"] == phase["personal_models"]["python_tests"]
    assert "All checks passed!" in (RAW / "ruff-check-final.log").read_text()
    assert (
        f"{phase['ruff']['formatted_files']} files already formatted"
        in (RAW / "ruff-format-final.log").read_text()
    )
    assert "built in" in (RAW / "frontend-build-final.log").read_text()
    assert "[INFO] BUILD SUCCESS" in (RAW / "backend-package-final.log").read_text()
    observations = [
        json.loads(line)
        for line in (RAW / "observations-final/probes.jsonl").read_text().splitlines()
    ]
    assert observations == phase["probe_observations"]
    assert len(observations) == 3 and all(
        r["ok"] and r["category"] == "OK" for r in observations
    )
    assert {r["finalUrl"] for r in observations} == {
        "https://api.deepseek.com/chat/completions",
        "https://bailian.example/api/v1/services/aigc/multimodal-generation/generation",
        "https://silicon.example/v1/audio/transcriptions",
    }
    browser = read(RAW / "browser/results.json")
    assert {k: v for k, v in browser.items() if k != "calls"} == phase["browser"]
    assert len(browser["calls"]) == phase["browser_request_count"]
    assert browser["realProviderCalls"] == 0 and browser["manualProbeCount"] == 1
    assert (
        browser["noAutomaticProbes"]
        and browser["keyAbsentFromStorage"]
        and browser["keyClearedOnSaveAndReload"]
    )
    assert browser["userAdminRouteDenied"] and browser["unexpectedPageErrors"] == []
    fixture = ROOT / "backend/src/main/resources/system-model-probe/tone.wav"
    assert (
        hashlib.sha256(fixture.read_bytes()).hexdigest()
        == phase["asr_fixture"]["sha256"]
    )
    assert len(fixture.read_bytes()) == phase["asr_fixture"]["bytes"]
    with wave.open(str(fixture), "rb") as audio:
        assert audio.getframerate() == phase["asr_fixture"]["sample_rate"]
        assert audio.getnframes() == phase["asr_fixture"]["samples"]
        assert (
            audio.getnframes() / audio.getframerate()
            == phase["asr_fixture"]["duration_seconds"]
        )
    files = scan_files()
    assert len(files) == phase["credential_log_scan"]["files_scanned"]
    assert len(CANARIES) == phase["credential_log_scan"]["canary_count"]
    assert not [
        str(path) for path in files if any(key in path.read_bytes() for key in CANARIES)
    ]
    assert read(RAW / "checks.json") == phase["checks"]
    assert all(check["exit_code"] == 0 for check in phase["checks"])
    assert summary["final_results"] == {
        field: phase[field]
        for field in ("backend_full", "frontend", "python", "ruff", "personal_models")
    }
    source_files = check_manifest(PUBLIC / "SHA256SUMS")
    raw_files = check_manifest(PUBLIC / "phase4/RAW_SHA256SUMS")
    phase4_commit = None
    if not pre_commit:
        phase4_commit = subprocess.check_output(
            [
                "git",
                "log",
                "--diff-filter=A",
                "--format=%H",
                "--",
                "eval/system-model-management/VERIFY.md",
            ],
            cwd=ROOT,
            text=True,
        ).strip()
        assert re.fullmatch(r"[a-f0-9]{40}", phase4_commit)
        assert (
            subprocess.check_output(
                ["git", "rev-parse", f"{phase4_commit}^"], cwd=ROOT, text=True
            ).strip()
            == summary["stages"][2]["commit"]
        )
    return {
        "java": phase["backend_full"]["tests"],
        "frontend": phase["frontend"]["tests"],
        "python": phase["python"]["tests"],
        "mysql": phase["real_mysql_tests"],
        "source_files": source_files,
        "raw_phase4_files": raw_files,
        "phase4_commit": phase4_commit,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pre-commit",
        action="store_true",
        help="Only skip resolving this file's initial commit",
    )
    print(json.dumps(verify(parser.parse_args().pre_commit), indent=2))
