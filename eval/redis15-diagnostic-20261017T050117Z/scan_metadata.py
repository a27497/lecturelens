#!/usr/bin/env python3
"""Credential-free, DB-15-only metadata diagnosis; never fetch Redis values."""
import collections
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import resource
import socket
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
AUTHORIZED = ROOT / 'eval/p2-1b-pipeline-20261016T122904Z/redis-reuse-authorization.json'
ENDPOINT = ROOT / '.data/p2-1b-pipeline-20261016T122904Z/redis15-deployment-preflight.json'


class Stop(Exception):
    pass


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    endpoint = json.loads(ENDPOINT.read_text())
    authorization = json.loads(AUTHORIZED.read_text())
    assert endpoint['database'] == authorization['database'] == 15
    assert endpoint['host'] == 'localhost' and endpoint['port'] == 16379
    expected = authorization['allowed_existing_key'].encode()
    # HMAC secret exists only in memory; key identifiers cannot expose raw names.
    salt = os.urandom(32)
    result = dict(started_at_utc=utc(), endpoint=dict(host='localhost', port=16379, database=15),
                  connection_source='historical_safe_endpoint_metadata', authentication='NONE',
                  key_identifier='HMAC-SHA256 with non-persisted random secret',
                  values_read=False, mutation_commands=0, commands=collections.Counter(), scans=[])
    deadline = time.monotonic() + 45
    try:
        with socket.create_connection(('localhost', 16379), timeout=3) as sock:
            result['peer'] = list(sock.getpeername())
            with sock.makefile('rb') as stream:
                def read():
                    line = stream.readline(1024 * 1024)
                    if not line.endswith(b'\r\n'):
                        raise Stop('RESP_INCOMPLETE')
                    kind, data = line[:1], line[1:-2]
                    if kind == b'-':
                        # Server text and key names never enter diagnostic evidence.
                        code = data.split(b' ', 1)[0]
                        raise Stop({b'NOAUTH': 'REDIS_NOAUTH', b'NOPERM': 'REDIS_NOPERM'}.get(code, 'REDIS_ERROR'))
                    if kind == b'+': return data
                    if kind == b':': return int(data)
                    if kind == b'*':
                        count = int(data)
                        if count < 0 or count > 200000: raise Stop('RESP_ARRAY_LIMIT')
                        return [read() for _ in range(count)]
                    if kind == b'$':
                        count = int(data)
                        if count < 0: return None
                        if count > 1024 * 1024: raise Stop('RESP_BULK_LIMIT')
                        value = stream.read(count)
                        if len(value) != count or stream.read(2) != b'\r\n': raise Stop('RESP_INCOMPLETE')
                        return value
                    raise Stop('RESP_TYPE')

                def command(name, *args):
                    assert name in ('SELECT', 'DBSIZE', 'SCAN', 'TYPE', 'TTL')
                    assert name != 'SELECT' or args == (15,)
                    if time.monotonic() >= deadline: raise Stop('TIME_LIMIT')
                    parts = [x if isinstance(x, bytes) else str(x).encode() for x in (name, *args)]
                    result['commands'][name] += 1
                    sock.sendall(b'*' + str(len(parts)).encode() + b'\r\n' + b''.join(
                        b'$' + str(len(x)).encode() + b'\r\n' + x + b'\r\n' for x in parts))
                    return read()

                command('SELECT', 15)
                previous = None
                for _ in range(3):
                    scan = dict(started_at_utc=utc(), dbsize_before=command('DBSIZE'), complete=False,
                                pages=0, returned_items=0, duplicates=0)
                    result['scans'].append(scan)
                    keys = set()
                    cursor = b'0'
                    while True:
                        cursor, batch = command('SCAN', cursor, 'COUNT', 100)
                        scan['pages'] += 1
                        scan['returned_items'] += len(batch)
                        keys.update(batch)
                        if len(keys) > 100000 or scan['pages'] > 10000: raise Stop('SCAN_LIMIT')
                        if cursor == b'0': break
                    scan['complete'] = True
                    scan['unique_count'] = len(keys)
                    scan['duplicates'] = scan['returned_items'] - len(keys)
                    scan['authorized_history_key_present'] = expected in keys
                    scan['unexpected_unique_count'] = len(keys - {expected})
                    scan['matches_previous_key_set'] = None if previous is None else keys == previous
                    scan['keys'] = []
                    for key in sorted(keys):
                        kind, ttl = command('TYPE', key), command('TTL', key)
                        allowed_types = {b'string', b'list', b'set', b'zset', b'hash', b'stream', b'none', b'vectorset'}
                        scan['keys'].append(dict(id=hmac.new(salt, key, hashlib.sha256).hexdigest(),
                            authorized_history_match=key == expected,
                            type=kind.decode() if kind in allowed_types else 'OTHER', ttl_seconds=ttl))
                    scan['dbsize_after'] = command('DBSIZE')
                    scan['finished_at_utc'] = utc()
                    previous = keys
                result['code'] = 'COMPLETE_NONATOMIC_METADATA_SAMPLING'
    except Stop as exc:
        result['code'] = str(exc)
    except (OSError, ValueError, AssertionError, TypeError, KeyError):
        result['code'] = 'CONNECTION_OR_PROTOCOL_GATE'
    result['finished_at_utc'] = utc()
    target = OUT / 'redis-metadata.json'
    with target.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps(dict(code=result['code'], completed_scans=sum(s.get('complete', False) for s in result['scans']),
                          values_read=False, mutation_commands=0)))


if __name__ == '__main__':
    run()
