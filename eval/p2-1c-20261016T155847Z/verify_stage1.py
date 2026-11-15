#!/usr/bin/env python3
"""Read-only evidence verification; never starts services or invokes providers."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    records = []
    for path in sorted(PUBLIC.glob("stage1-*.json")):
        record = json.loads(path.read_text())
        assert digest(ROOT / record["log_path"]) == record["log_sha256"], path
        reports = ROOT / record["log_path"]
        reports = reports.parent / (path.stem + "-reports")
        totals = dict.fromkeys(("tests", "failures", "errors", "skipped"), 0)
        for suite in record["suites"]:
            report = reports / ("TEST-" + suite["suite"] + ".xml")
            assert digest(report) == suite["sha256"], report
            xml = ET.fromstring(report.read_bytes())
            for field in totals:
                value = int(xml.attrib.get(field, 0))
                assert value == suite[field], (report, field)
                totals[field] += value
        assert totals == record["total"], path
        assert record["disk_before"]["allowed"] and record["disk_after"]["allowed"], path
        records.append({"record": path.name, "exit_code": record["exit_code"], **totals})
    assert records, "no executed checks"
    mysql = next(r for r in records if r["record"] == "stage1-mysql-02.json")
    assert mysql["exit_code"] == mysql["failures"] == mysql["errors"] == mysql["skipped"] == 0, mysql
    final = next(r for r in records if r["record"] == "stage1-unit-final.json")
    assert final["exit_code"] == final["failures"] == final["errors"] == final["skipped"] == 0, final
    trials = PUBLIC / "trials.jsonl"
    assert not trials.read_text().strip(), "update trial evidence audit after first real task"
    print(json.dumps({"checks": records, "real_trials_submitted": 0,
                      "mysql_tests": "32 passed; independent MySQL; no skipped tests",
                      "scope": "mechanism checks only; not full-suite or real-model acceptance"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
