#!/usr/bin/env python3
"""Exercise the unchanged gate via an AST-extracted function and synthetic RESP."""
import ast
import io
import json
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'eval/p2-1c-run-20261016T191343Z/runtime_service.py'


def resp(value):
    if isinstance(value, list):
        return b'*' + str(len(value)).encode() + b'\r\n' + b''.join(map(resp, value))
    value = value.encode()
    return b'$' + str(len(value)).encode() + b'\r\n' + value + b'\r\n'


class Gate(Exception):
    pass


def require(ok, code):
    if not ok:
        raise Gate(code)


def main():
    expected = json.loads((ROOT / 'eval/p2-1b-pipeline-20261016T122904Z/redis-reuse-authorization.json').read_text())['allowed_existing_key']
    function = next(n for n in ast.parse(SOURCE.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'redis_gate')
    code = compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), 'exec')
    cases = [
        ('empty', 0, ['0', []], 'PASS', 0),
        ('one_authorized_complete', 1, ['0', [expected]], 'PASS', 1),
        ('one_unauthorized', 1, ['0', ['synthetic-unknown']], 'REDIS15_UNEXPECTED_KEYS', 1),
        ('one_authorized_nonzero_cursor', 1, ['1', [expected]], 'REDIS15_UNEXPECTED_KEYS', 1),
        ('duplicate_authorized_return', 1, ['0', [expected, expected]], 'REDIS15_UNEXPECTED_KEYS', 1),
        ('more_than_one_short_circuit', 2, ['0', [expected]], 'REDIS15_UNEXPECTED_KEYS', 0),
        ('expired_between_dbsize_and_scan', 1, ['0', []], 'REDIS15_UNEXPECTED_KEYS', 1),
    ]
    results = []
    for name, count, scan, wanted, wanted_scans in cases:
        calls = []

        class FakeSocket:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def makefile(self, *args): return io.BytesIO(b'+OK\r\n:' + str(count).encode() + b'\r\n' + resp(scan))
            def sendall(self, payload):
                calls.append(payload.split(b'\r\n')[2].decode())

        namespace = dict(socket=SimpleNamespace(create_connection=lambda *a, **k: FakeSocket()),
                         json=json, ROOT=ROOT, require=require)
        exec(code, namespace)
        try:
            namespace['redis_gate']({'REDIS_HOST': 'synthetic', 'REDIS_PORT': 1})
            outcome = 'PASS'
        except Gate as exc:
            outcome = str(exc)
        assert outcome == wanted and calls.count('SCAN') == wanted_scans, name
        results.append(dict(case=name, outcome=outcome, scan_commands=calls.count('SCAN'), passed=True))
    with (HERE / 'offline-gate-results.json').open('x') as f:
        json.dump(dict(kind='synthetic_gate_behavior_only', real_redis_access=False, cases=results), f, indent=2)
        f.write('\n')
    print(f'{len(results)}/{len(cases)} offline gate behavior checks passed; no live cause inferred')


if __name__ == '__main__':
    main()
