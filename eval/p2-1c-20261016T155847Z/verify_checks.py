#!/usr/bin/env python3
"""Verify archived mechanism records, including failed attempts, without invoking providers."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--final", required=True)
    args = parser.parse_args()
    checks = []
    for path in sorted(PUBLIC.glob(args.prefix + "*.json")):
        record = json.loads(path.read_text())
        if "suites" not in record:
            continue
        assert digest(ROOT / record["log_path"]) == record["log_sha256"], path
        folder = (ROOT / record["log_path"]).parent / (path.stem + "-reports")
        total = dict.fromkeys(("tests", "failures", "errors", "skipped"), 0)
        for suite in record["suites"]:
            report = folder / ("TEST-" + suite["suite"] + ".xml")
            assert digest(report) == suite["sha256"], report
            xml = ET.fromstring(report.read_bytes())
            for field in total:
                assert int(xml.attrib.get(field, 0)) == suite[field], report
                total[field] += suite[field]
        if "external_junit" in record:
            report=ROOT / record["external_junit"]["path"]
            assert digest(report)==record["external_junit"]["sha256"], report
            suites=list(ET.fromstring(report.read_bytes()).iter("testsuite"))
            total={field:sum(int(suite.attrib.get(field,0)) for suite in suites) for field in total}
        assert total == record["total"], path
        assert record["disk_before"]["allowed"] and record["disk_after"]["allowed"], path
        checks.append({"record": path.name, "exit_code": record["exit_code"], **total})
    final = next(check for check in checks if check["record"] == args.final)
    assert final["tests"] > 0, final
    assert final["exit_code"] == final["failures"] == final["errors"] == final["skipped"] == 0, final
    print(json.dumps({"checks": checks, "real_model_quality": False}, indent=2))


if __name__ == "__main__":
    main()
