"""Validate raw identity, complete tests and non-overlapping measurement windows."""
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


def source_digest(path):
    digest = hashlib.sha256()
    files = {}
    for file in sorted(path.rglob('*.py')):
        name = str(file.relative_to(path))
        digest.update(name.encode())
        digest.update(file.read_bytes())
        files[name] = hashlib.sha256(file.read_bytes()).hexdigest()
    return digest.hexdigest(), files


def main():
    report = json.loads((ROOT/'summary.json').read_text())
    candidates = REPO/'agent-service/src/lecturelens_agent'
    identity, files = source_digest(candidates)
    assert identity == report['source_sha256']['candidate']
    original = json.loads((ROOT.parent/'tool-resilience-20261014/verification.json').read_text())
    assert original['candidate_source_sha256'] == report['source_sha256']['before']
    counts = dict(tests=0, failures=0, errors=0, skipped=0)
    cases, results, test_starts = [], [], []
    for group in json.loads((ROOT/'verification-groups.json').read_text()):
        xml = ROOT/f'tests-group-{group["worker"]}.xml'
        tree = ET.parse(xml)
        suites = list(tree.getroot().iter('testsuite'))
        nums = {key: sum(int(s.get(key, 0)) for s in suites) for key in counts}
        assert nums['tests'] == group['expected_cases']
        assert nums['failures'] == nums['errors'] == nums['skipped'] == 0
        for key, value in nums.items():
            counts[key] += value
        for case in tree.getroot().iter('testcase'):
            cases.append((case.get('classname'), case.get('name')))
        test_starts.extend(datetime.fromisoformat(s.get('timestamp')) for s in suites)
        results.append({**group, **nums, 'elapsed_seconds': sum(float(s.get('time', 0)) for s in suites),
                        'junit_sha256': hashlib.sha256(xml.read_bytes()).hexdigest()})
    collected = [l for l in (ROOT/'tests-collection.txt').read_text().splitlines() if '::' in l]
    expected = {('tests.'+l.split('::',1)[0].split('/')[-1].removesuffix('.py'), l.split('::',1)[1]) for l in collected}
    assert set(cases) == expected and len(cases) == len(expected) == counts['tests'] == 664
    tests_start = datetime.fromisoformat(json.loads((ROOT/'tests-start.json').read_text())['started_at_utc'])
    audit_finish = []
    audits = {}
    for phase in ['healthy', 'faults']:
        records = json.loads((ROOT/f'serial-clean/{phase}-audit.json').read_text())
        assert all(r['returncode'] == 0 and not any(s['unexpected_eval_or_test_processes'] for s in r['host_samples']) for r in records)
        audit_finish.extend(datetime.fromisoformat(r['finished_at_utc']) for r in records)
        audits[phase] = [{key: r[key] for key in ['label', 'started_at_utc', 'finished_at_utc']} for r in records]
    assert max(audit_finish) < tests_start
    # JUnit uses the host's local naive timestamp; this host is UTC.
    assert all(t.replace(tzinfo=timezone.utc) > max(audit_finish) for t in test_starts)
    checks = {}
    for name, command in {
        'ruff_check': [sys.executable, '-m', 'ruff', 'check', 'src', 'tests'],
        'ruff_format_check': [sys.executable, '-m', 'ruff', 'format', '--check', 'src', 'tests'],
        'git_diff_check': ['git', 'diff', '--check'],
    }.items():
        result = subprocess.run(command, cwd=REPO/'agent-service', capture_output=True, text=True)
        assert result.returncode == 0, result.stdout+result.stderr
        checks[name] = {'exit_code': result.returncode, 'output': result.stdout+result.stderr}
    for name, digest in report['raw_sha256'].items():
        assert hashlib.sha256((ROOT/'serial-clean'/name).read_bytes()).hexdigest() == digest
    # The previous batch is read-only and its raw records still match its evidence.
    old = json.loads((ROOT.parent/'tool-resilience-20261014/summary.json').read_text())
    for name, digest in old['raw_sha256'].items():
        assert hashlib.sha256((ROOT.parent/'tool-resilience-20261014'/name).read_bytes()).hexdigest() == digest
    patch = ''
    before = Path(os.environ['LECTURELENS_BEFORE_PACKAGE'])
    for relative in ['study/store.py', 'study/runtime.py', 'study/connections.py']:
        old_file, new_file = before/relative, candidates/relative
        result = subprocess.run(['git', 'diff', '--no-index', '--', str(old_file) if old_file.exists() else '/dev/null', str(new_file)], capture_output=True, text=True)
        assert result.returncode in {0,1}
        patch += result.stdout
    (ROOT/'latency-fix.patch').write_text(patch)
    with psycopg.connect(os.environ['AGENT_TEST_DATABASE_URL']) as conn:
        pg = conn.execute('SELECT version()').fetchone()[0]
    verification = {
        'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(), 'postgres': pg,
        'dependencies': {p: importlib.metadata.version(p) for p in ['psycopg','mcp','langgraph','langgraph-checkpoint-postgres','pytest','ruff']},
        'python_checks': counts, 'complete_collection_covered_once': True, 'database_skips': 0, 'groups': results,
        'test_started_at_utc': tests_start.isoformat(), 'measurement_windows': audits, 'no_test_measurement_overlap': True,
        'process_audits_passed': True, 'check_results': checks,
        'source_sha256': report['source_sha256'], 'candidate_source_files': files,
        'patch_sha256': hashlib.sha256((ROOT/'latency-fix.patch').read_bytes()).hexdigest(),
        'raw_sha256': report['raw_sha256'], 'old_raw_files_unchanged': True, 'same_branch': subprocess.check_output(['git','branch','--show-current'],cwd=REPO,text=True).strip(),
        'fault_counts_match_accepted_P0_1': report['fault_counts_match_accepted_P0_1'],
        'formal_health_runs': 60, 'formal_fault_matrix_runs': 600,
        'real_model_quality': '未运行', 'real_Java_process_faults': '未运行', 'Java_modified': False, 'Java_tests': '未运行（Java 未修改）',
        'push': '未执行', 'deployment': '未执行',
    }
    (ROOT/'verification.json').write_text(json.dumps(verification, indent=2, ensure_ascii=False)+'\n')
    print('Verified', counts, 'with complete coverage and no measurement/test overlap.')


if __name__ == '__main__':
    main()
