#!/usr/bin/env python3
"""One authorized dev process: Redis-only configuration projection and metadata."""
import collections
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import pwd
import re
import resource
import socket
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


class Gate(Exception):
    pass


def require(ok, code):
    if not ok:
        raise Gate(code)


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def project_json(path, wanted):
    """Decode only selected top-level values; discard other value characters.

    In particular, do not json.load the runtime file and then filter it: that
    would materialize unrelated business configuration and provider secrets.
    """
    class Reader:
        def __init__(self, stream):
            self.stream, self.pending, self.total = stream, None, 0

        def get(self):
            if self.pending is not None:
                ch, self.pending = self.pending, None
                return ch
            ch = self.stream.read(1)
            self.total += 1
            require(self.total <= 4 * 1024 * 1024, 'JSON_SIZE_LIMIT')
            return ch

        def unget(self, ch):
            self.pending = ch

        def nonspace(self):
            ch = self.get()
            while ch and ch.isspace():
                ch = self.get()
            return ch

        def value(self, first, capture):
            require(bool(first), 'JSON_SHAPE')
            chunks = [first] if capture else None
            quoted, escaped = first == '"', False
            stack = [first] if first in '{[' else []
            count = 1
            while True:
                if first == '"' and not quoted:
                    break
                ch = self.get()
                require(bool(ch), 'JSON_SHAPE')
                if not quoted and not stack and (ch.isspace() or ch in ',}'):
                    self.unget(ch)
                    break
                count += 1
                require(count <= 2 * 1024 * 1024, 'JSON_VALUE_LIMIT')
                if capture:
                    require(count <= 65536, 'SELECTED_JSON_VALUE_LIMIT')
                    chunks.append(ch)
                if quoted:
                    if escaped:
                        escaped = False
                    elif ch == '\\':
                        escaped = True
                    elif ch == '"':
                        quoted = False
                elif ch == '"':
                    quoted = True
                elif ch in '{[':
                    stack.append(ch)
                    require(len(stack) <= 64, 'JSON_DEPTH_LIMIT')
                elif ch in '}]':
                    require(bool(stack) and (stack.pop(), ch) in (('{', '}'), ('[', ']')), 'JSON_SHAPE')
                    if not stack:
                        break
            return json.loads(''.join(chunks)) if capture else None

    selected = {}
    with Path(path).open() as stream:
        r = Reader(stream)
        require(r.nonspace() == '{', 'JSON_OBJECT_REQUIRED')
        ch = r.nonspace()
        if ch == '}':
            return selected
        while True:
            require(ch == '"', 'JSON_KEY_SHAPE')
            key = r.value(ch, True)
            require(isinstance(key, str) and r.nonspace() == ':', 'JSON_SHAPE')
            keep = key in wanted
            value = r.value(r.nonspace(), keep)
            if keep:
                require(key not in selected, 'DUPLICATE_SELECTED_FIELD')
                selected[key] = value
            ch = r.nonspace()
            if ch == '}':
                require(r.nonspace() == '', 'JSON_TRAILING_DATA')
                return selected
            require(ch == ',', 'JSON_SHAPE')
            ch = r.nonspace()


def task_index():
    # Public archived task files only; no DB or private provider records.
    index = collections.defaultdict(list)
    for directory in sorted((ROOT / 'eval').glob('p2-1*-20261016T*')):
        for path in sorted((directory / 'runtime-evidence').glob('task_*.json')):
            if re.fullmatch(r'task_[a-f0-9]{32}\.json', path.name):
                index[path.stem.encode()].append(path)
    return index


def diagnose():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    result = dict(started_at_utc=utc(), values_read=False, mutation_commands=0,
                  configuration_values_emitted=False, key_identifiers='HMAC-SHA256; random secret never persisted',
                  commands=collections.Counter(), scans=[], database=15)
    salt = os.urandom(32)
    deadline = time.monotonic() + 45
    try:
        require(os.getuid() != 0 and pwd.getpwuid(os.getuid()).pw_name == 'dev', 'DEV_REQUIRED')
        s = os.statvfs(ROOT)
        used, available = (s.f_blocks - s.f_bfree) * s.f_frsize, s.f_bavail * s.f_frsize
        require(used / (used + available) <= .85 and .85 * (used + available) - used >= 2 * 1024**3, 'DISK_GATE')
        cfg = project_json(ROOT / '.data/live-access/runtime.json', {'REDIS_HOST', 'REDIS_PORT', 'REDIS_PASSWORD'})
        require(cfg.get('REDIS_HOST') in ('localhost', '127.0.0.1') and str(cfg.get('REDIS_PORT')) == '16379', 'TARGET_MISMATCH')
        require(isinstance(cfg.get('REDIS_PASSWORD', ''), str), 'REDIS_CONFIG_SHAPE')
        result['configured_target_matches_history'] = True
        old = project_json(ROOT / 'eval/p2-1b-pipeline-20261016T122904Z/redis-reuse-authorization.json',
                           {'allowed_existing_key', 'database'})
        require(old['database'] == 15, 'HISTORICAL_DB_MISMATCH')
        expected = old['allowed_existing_key'].encode()
        tasks = task_index()
        result['archived_task_evidence_identifiers'] = len(tasks)
        with socket.create_connection(('127.0.0.1', 16379), timeout=3) as sock:
            require(sock.getpeername() == ('127.0.0.1', 16379), 'PEER_MISMATCH')
            result['peer_matches_history'] = True
            with sock.makefile('rb') as stream:
                def read():
                    line = stream.readline(1024 * 1024)
                    require(line.endswith(b'\r\n'), 'RESP_INCOMPLETE')
                    kind, data = line[:1], line[1:-2]
                    if kind == b'-':
                        code = data.split(b' ', 1)[0]
                        raise Gate({b'NOAUTH': 'REDIS_NOAUTH', b'WRONGPASS': 'REDIS_AUTH_FAILED',
                                    b'NOPERM': 'REDIS_NOPERM'}.get(code, 'REDIS_ERROR'))
                    if kind == b'+': return data
                    if kind == b':': return int(data)
                    if kind == b'*':
                        count = int(data)
                        require(0 <= count <= 200000, 'RESP_ARRAY_LIMIT')
                        return [read() for _ in range(count)]
                    if kind == b'$':
                        count = int(data)
                        if count == -1: return None
                        require(0 <= count <= 1024 * 1024, 'RESP_BULK_LIMIT')
                        payload = stream.read(count)
                        require(len(payload) == count and stream.read(2) == b'\r\n', 'RESP_INCOMPLETE')
                        return payload
                    raise Gate('RESP_TYPE')

                def command(name, *args):
                    require(name in ('AUTH', 'SELECT', 'DBSIZE', 'SCAN', 'TYPE', 'TTL'), 'COMMAND_NOT_ALLOWED')
                    require(name != 'SELECT' or args == (15,), 'SELECT_NOT_ALLOWED')
                    require(time.monotonic() < deadline, 'TIME_LIMIT')
                    parts = [v if isinstance(v, bytes) else str(v).encode() for v in (name, *args)]
                    result['commands'][name] += 1
                    sock.sendall(b'*' + str(len(parts)).encode() + b'\r\n' + b''.join(
                        b'$' + str(len(v)).encode() + b'\r\n' + v + b'\r\n' for v in parts))
                    return read()

                if cfg.get('REDIS_PASSWORD'):
                    require(command('AUTH', cfg['REDIS_PASSWORD']) == b'OK', 'REDIS_AUTH_FAILED')
                del cfg
                require(command('SELECT', 15) == b'OK', 'REDIS_SELECT_FAILED')
                result['authentication_and_select_passed'] = True
                previous = None
                for _ in range(3):
                    scan = dict(started_at_utc=utc(), dbsize_before=command('DBSIZE'), complete=False,
                                pages=0, returned_items=0, keys=[])
                    result['scans'].append(scan)
                    keys, cursor = set(), b'0'
                    while True:
                        cursor, batch = command('SCAN', cursor, 'COUNT', 100)
                        require(isinstance(cursor, bytes) and cursor.isdigit() and isinstance(batch, list), 'SCAN_SHAPE')
                        require(all(isinstance(k, bytes) for k in batch), 'SCAN_KEY_SHAPE')
                        scan['pages'] += 1
                        scan['returned_items'] += len(batch)
                        if scan['pages'] == 1:
                            scan['first_page_cursor_zero'] = cursor == b'0'
                            scan['first_page_matches_legacy_expected'] = cursor == b'0' and batch == [expected]
                        keys.update(batch)
                        require(len(keys) <= 100000 and scan['pages'] <= 10000, 'SCAN_LIMIT')
                        if cursor == b'0': break
                    scan.update(complete=True, unique_count=len(keys), duplicates=scan['returned_items'] - len(keys),
                                authorized_history_key_present=expected in keys,
                                unexpected_unique_count=len(keys - {expected}),
                                matches_previous_key_set=None if previous is None else keys == previous)
                    for key in sorted(keys):
                        kind, ttl = command('TYPE', key), command('TTL', key)
                        allowed_types = {b'string', b'list', b'set', b'zset', b'hash', b'stream', b'none', b'vectorset'}
                        item = dict(id=hmac.new(salt, key, hashlib.sha256).hexdigest(),
                                    authorized_history_match=key == expected,
                                    type=kind.decode() if kind in allowed_types else 'OTHER', ttl_seconds=ttl,
                                    family='OTHER', ownership='UNKNOWN', evidence=[])
                        match = re.fullmatch(rb'cl:t:progress:(task_[a-f0-9]{32})', key)
                        if match:
                            item['family'] = 'TASK_PROGRESS'
                            for path in tasks.get(match[1], []):
                                meta = project_json(path, {'task_id', 'taskId', 'status'})
                                record_id_matches = any(isinstance(meta.get(f), str) and meta[f].encode() == match[1]
                                                        for f in ('task_id', 'taskId'))
                                item['evidence'].append(dict(group=path.parent.parent.name,
                                    record_sha256=hashlib.file_digest(path.open('rb'), 'sha256').hexdigest(),
                                    filename_task_id_match=True, record_task_id_match=record_id_matches))
                            if item['evidence']:
                                item['ownership'] = 'MATCH_ARCHIVED_TASK_IDENTIFIER'
                        scan['keys'].append(item)
                    scan['type_counts'] = dict(collections.Counter(k['type'] for k in scan['keys']))
                    scan['ttl_counts'] = dict(collections.Counter('PERSISTENT' if k['ttl_seconds'] == -1 else
                        'VANISHED' if k['ttl_seconds'] == -2 else 'EXPIRING' for k in scan['keys']))
                    scan['dbsize_after'] = command('DBSIZE')
                    scan['finished_at_utc'] = utc()
                    previous = keys
                result['code'] = 'COMPLETE_NONATOMIC_METADATA_SAMPLING'
    except Gate as exc:
        result['code'] = str(exc)
    except (OSError, ValueError, TypeError, KeyError):
        result['code'] = 'CONNECTION_OR_FORMAT_GATE'
    except Exception:
        # No traceback: frame locals and exception messages may contain secrets.
        result['code'] = 'UNEXPECTED_GATE'
    result['finished_at_utc'] = utc()
    with (HERE / 'redis-metadata.json').open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps(dict(code=result['code'], completed_scans=sum(s['complete'] for s in result['scans']),
                          values_read=False, mutation_commands=0)))
    return 0 if result['code'] == 'COMPLETE_NONATOMIC_METADATA_SAMPLING' else 2


if __name__ == '__main__':
    raise SystemExit(diagnose())
