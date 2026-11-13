#!/usr/bin/env python3
"""No credentials, network, or service starts: instrument boundaries and selftests."""
import ast
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess

PUBLIC = Path(__file__).resolve().parent
ROOT = PUBLIC.parents[1]
PRIVATE = ROOT / '.data' / PUBLIC.name


def digest(path):
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()


def main():
    text = (PUBLIC / 'runtime_service.py').read_text()
    tree = ast.parse(text)
    assert not any(isinstance(n, ast.FunctionDef) and n.name in {'trial', 'api', 'token'} for n in tree.body)
    assert '/api/tasks' not in text and "'POST'" not in text
    rows = []
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'java', 'sanitized_stream', 'utc'}]
    selected += [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SAFE_KEYS' for t in n.targets)]
    scope = dict(PRIVATE=PRIVATE, OPTIONS=ROOT/'eval/p2-1c-20261016T155847Z/candidate-options.json',
        ASR_YAML=Path('/synthetic-only'), TOPIC='lecturelens-p21-20261016T073754Z', dt=dt, re=re, json=json,
        append=lambda name, row: rows.append((name, row)))
    exec(compile(ast.Module(body=selected, type_ignores=[]), 'synthetic-functions', 'exec'), scope)
    args = scope['java']({}, None)
    assert 'com.example.courselingo.systemmodel.P21StartupDiagnostics' in args
    assert 'com.example.courselingo.systemmodel.P21Bootstrap' in scope['java']({}, 'preflight')
    props = json.loads(scope['OPTIONS'].read_text())['properties']
    for key, value in props.items():
        assert '--'+key+'='+(str(value).lower() if isinstance(value, bool) else str(value)) in args
    markers = set()
    scope['sanitized_stream'](io.StringIO(
        'P21_STARTUP_CAUSE index=0 kind=BEAN_INSTANTIATION\n'
        'P21_STARTUP_CAUSE index=1 kind=SQL sqlState=28000 vendorCode=1045\n'
        'P21_STARTUP_CAUSE index=16 kind=SQL sqlState=28000 vendorCode=1045\n'
        'P21_STARTUP_CAUSE index=2 kind=SYNTHETIC_PRIVATE\n'
        'P21_STARTUP_CAUSE index=2 kind=SQL sqlState=28000 vendorCode=1 extra=SYNTHETIC_PRIVATE\n'
        'SYNTHETIC_PRIVATE_CONFIGURATION_MESSAGE\n'), markers)
    assert len(rows) == 2 and 'SYNTHETIC_PRIVATE' not in json.dumps(rows)
    assert rows[1][1]['vendorCode'] == 1045
    prior = ROOT / 'eval/p2-1c-independent-redis-20261017T062836Z'
    assert digest(PUBLIC/'P21Bootstrap.java') == digest(prior/'P21Bootstrap.java')
    assert digest(PUBLIC/'P21IsolationGate.java') == digest(prior/'P21IsolationGate.java')
    cp = ':'.join(str(PRIVATE/p) for p in ['extra', 'runtime/BOOT-INF/classes', 'runtime/BOOT-INF/lib/*'])
    tests = [
        ('P21Bootstrap', 'selftest', 'P21_SELFTEST_PASS'),
        ('P21StartupDiagnostics', 'selftest-startup-diagnostics', 'P21_STARTUP_DIAGNOSTICS_SELFTEST_PASS'),
    ]
    outputs = []
    for cls, mode, marker in tests:
        r = subprocess.run(['/usr/bin/java', '-Dp21.private='+str(PRIVATE), '-cp', cp,
                            'com.example.courselingo.systemmodel.'+cls, mode],
                           capture_output=True, text=True, timeout=15)
        assert r.returncode == 0 and r.stdout.startswith(marker) and not r.stderr
        outputs.append(marker)
    record = dict(no_task_submission_functions=True,all_frozen_options_preserved=True,
        original_bootstrap_unchanged=True,original_isolation_gate_unchanged=True,
        fixed_diagnostic_filter_passed=True,offline_java_selftests=outputs,
        source_sha256={f.name:digest(f) for f in PUBLIC.glob('*.py')},
        java_source_sha256={f.name:digest(f) for f in PUBLIC.glob('*.java')})
    with (PUBLIC/'offline-check.json').open('x') as f:
        json.dump(record,f,indent=2);f.write('\n')
    print('OFFLINE_CHECK_PASS no_submission,frozen_options,bootstrap_identity,diagnostic_filter,java_selftests')


if __name__ == '__main__':
    main()
