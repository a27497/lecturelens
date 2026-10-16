#!/usr/bin/env python3
"""Archive only fresh Surefire reports; emit aggregate counts and diagnostic hashes."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = Path(__file__).resolve().parent
PRIVATE = ROOT / '.data' / PUBLIC.name


def main():
    name = sys.argv[1]
    assert name.startswith('translation-mysql-') and '/' not in name
    record = json.loads((PRIVATE / name / 'run.json').read_text())
    assert record['status'] not in {'RUNNING', 'STARTING'}
    start = dt.datetime.fromisoformat(record['started_at_utc']).timestamp()
    destination = PRIVATE / (name + '-reports')
    destination.mkdir(exist_ok=False)
    totals = dict(tests=0, failures=0, errors=0, skipped=0)
    suites = []
    hashes = {}
    for path in sorted((ROOT / 'backend/target/surefire-reports').glob('TEST-*.xml')):
        if path.stat().st_mtime < start:
            continue
        archived = destination / path.name
        shutil.copy2(path, archived)
        suite = ET.parse(archived).getroot()
        counts = {key: int(suite.get(key, 0)) for key in totals}
        for key in totals:
            totals[key] += counts[key]
        suites.append(dict(name=suite.get('name'), **counts))
        hashes[str(archived.relative_to(ROOT))] = hashlib.sha256(archived.read_bytes()).hexdigest()
    # A compiler failure may legitimately produce no new test reports.
    for path in (PRIVATE / name / 'run.json', PRIVATE / name / 'output.log'):
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = dict(name=name, status=record['status'], exit_code=record['exit_code'],
                  totals=totals, suites=suites, sha256=hashes, cleanup=record['cleanup'])
    output = PUBLIC / (name + '-check.json')
    assert not output.exists()
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(name=name, **totals, status=record['status'], cleanup=record['cleanup']['complete'])))


if __name__ == '__main__':
    main()
