#!/usr/bin/env python3
"""One read-only, non-root metadata session; emit only fixed safe projections."""
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import re
import resource
import sys
from urllib.parse import urlsplit, parse_qsl

ROOT = Path('/home/dev/projects/lecturelens')
PUBLIC = Path(__file__).resolve().parent
SCHEMA = 'lecturelens_p21_20261016'
FIELDS = {'MYSQL_JDBC_URL', 'MYSQL_USERNAME', 'MYSQL_PASSWORD'}
sys.path.append(str(ROOT / '.data/baseline-asr-20261015/.venv/lib/python3.12/site-packages'))


class Gate(Exception):
    pass


def require(ok, code):
    if not ok:
        raise Gate(code)


def selective_strings(stream):
    # Do not deserialize the configuration object. Unselected values are consumed
    # only by a bounded syntax scanner, never decoded, retained, logged or copied.
    def nonspace():
        while True:
            c = stream.read(1)
            require(bool(c), 'CONFIG_SYNTAX')
            if c not in b' \r\n\t':
                return c

    def string(keep):
        buf = bytearray(b'"') if keep else None
        escaped = False
        for _ in range(1048576):
            c = stream.read(1)
            require(bool(c), 'CONFIG_SYNTAX')
            if keep:
                buf.extend(c)
            if not escaped and c == b'"':
                return json.loads(buf) if keep else None
            escaped = not escaped and c == b'\\'
        raise Gate('CONFIG_VALUE_BOUND')

    def skip(c, depth=0):
        require(depth <= 16, 'CONFIG_DEPTH')
        if c == b'"':
            string(False)
            return nonspace()
        if c in (b'{', b'['):
            end = b'}' if c == b'{' else b']'
            c = nonspace()
            while c != end:
                c = skip(c, depth + 1)
                if c in (b',', b':'):
                    c = nonspace()
                else:
                    require(c == end, 'CONFIG_SYNTAX')
            return nonspace()
        for _ in range(1048576):
            if c in (b',', b'}', b']'):
                return c
            c = stream.read(1)
            require(bool(c), 'CONFIG_SYNTAX')
        raise Gate('CONFIG_VALUE_BOUND')

    require(nonspace() == b'{', 'CONFIG_SYNTAX')
    c = nonspace()
    result = {}
    while c != b'}':
        require(c == b'"', 'CONFIG_SYNTAX')
        key = string(True)
        require(nonspace() == b':', 'CONFIG_SYNTAX')
        c = nonspace()
        if key in FIELDS:
            require(c == b'"' and key not in result, 'CONFIG_FIELD_TYPE_OR_DUPLICATE')
            result[key] = string(True)
            c = nonspace()
        else:
            c = skip(c)
        require(c in (b',', b'}'), 'CONFIG_SYNTAX')
        if c == b',':
            c = nonspace()
    require(set(result) == FIELDS, 'CONFIG_FIELDS_MISSING')
    return result


def disk():
    s = os.statvfs(ROOT)
    used = (s.f_blocks - s.f_bfree) * s.f_frsize
    available = s.f_bavail * s.f_frsize
    margin = .85 * (used + available) - used
    require(used / (used + available) <= .85 and margin >= 2 * 1024**3, 'DISK_GATE')
    return dict(used_bytes=used, available_bytes=available,
                usage_percent=100 * used / (used + available), margin_to_85_bytes=margin)


def main():
    import pymysql
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    require(pwd.getpwuid(os.getuid()).pw_name == 'dev' and os.getuid() != 0, 'DEV_REQUIRED')
    result = dict(at_utc=dt.datetime.now(dt.timezone.utc).isoformat(), disk_before=disk(),
                  spring_application_started=False, writes_executed=False, supplier_calls=0)
    jar = ROOT / '.data/p2-1c-20261016T155847Z/candidate/backend.jar'
    with jar.open('rb') as f:
        jar_hash = hashlib.file_digest(f, 'sha256').hexdigest()
    require(jar_hash == '35e8f63b6895e1d69fe45b51be45c196b4585c140b6a6c52b370a9922438d3b0', 'FROZEN_HASH')
    result['frozen_jar_sha256'] = jar_hash
    with (ROOT / '.data/live-access/runtime.json').open('rb', buffering=0) as f:
        cfg = selective_strings(f)
    require(cfg['MYSQL_USERNAME'].lower() != 'root' and bool(cfg['MYSQL_PASSWORD']), 'NONROOT_REQUIRED')
    require(cfg['MYSQL_JDBC_URL'].startswith('jdbc:mysql://'), 'JDBC_SHAPE')
    uri = urlsplit(cfg['MYSQL_JDBC_URL'][5:])
    require(uri.scheme == 'mysql' and uri.hostname and uri.username is None and uri.password is None, 'JDBC_SHAPE')
    require(not any(re.search('user|password|socket|pipe', k, re.I) for k, _ in parse_qsl(uri.query)), 'JDBC_INLINE_CONFIG')
    # The existing endpoint is reused without fallback; the original schema is
    # never connected. No root connection or credential is available here.
    c = pymysql.connect(host=uri.hostname, port=uri.port or 3306,
                        user=cfg['MYSQL_USERNAME'], password=cfg['MYSQL_PASSWORD'],
                        database=SCHEMA, charset='utf8mb4', autocommit=False,
                        connect_timeout=5, read_timeout=10, write_timeout=5)
    del cfg
    try:
        with c.cursor() as q:
            q.execute('SET SESSION TRANSACTION READ ONLY')
            q.execute('START TRANSACTION READ ONLY')
            q.execute("SELECT DATABASE()=%s, SUBSTRING_INDEX(CURRENT_USER(),'@',1)<>'root'", (SCHEMA,))
            matched, nonroot = q.fetchone()
            require(matched and nonroot, 'SESSION_IDENTITY')
            result.update(database_matches=True, authenticated_account_nonroot=True, read_only_transaction=True)
            expected = {r['version'].removeprefix('V'): r['flyway_checksum'] for r in json.loads(
                (ROOT / 'eval/p2-1c-startup-diagnostic-20261017T064402Z/offline-migrations.json').read_text())['resources']}
            q.execute('SELECT installed_rank,version,checksum,success FROM flyway_schema_history ORDER BY installed_rank')
            result['history'] = [dict(installed_rank=r, version=v, checksum=s, success=bool(ok),
                                      frozen_checksum_matches=expected.get(v) == s if v in expected else None)
                                 for r, v, s, ok in q.fetchall()]
            tables = ('asr_scheduler_state', 'asr_chunk_checkpoint', 'asr_scheduler_event', 'asr_result_cache')
            q.execute('SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN (%s,%s,%s,%s)', tables)
            present = {r[0] for r in q.fetchall()}
            result['v32_tables'] = {name: name in present for name in tables}
            triggers = ('asr_state_immutable_input', 'asr_chunk_immutable_input')
            q.execute('SELECT trigger_name FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name IN (%s,%s)', triggers)
            present = {r[0] for r in q.fetchall()}
            result['v32_triggers_visible'] = {name: name in present for name in triggers}
            # Output only privilege names, not grantees, hosts, schemas or raw GRANT SQL.
            grantee = "CONCAT(CHAR(39),SUBSTRING_INDEX(CURRENT_USER(),'@',1),CHAR(39),'@',CHAR(39),SUBSTRING_INDEX(CURRENT_USER(),'@',-1),CHAR(39))"
            for label, view, predicate in [('schema', 'SCHEMA_PRIVILEGES', 'TABLE_SCHEMA=DATABASE() AND '),
                                            ('global', 'USER_PRIVILEGES', '')]:
                q.execute(f'SELECT PRIVILEGE_TYPE FROM information_schema.{view} WHERE {predicate}GRANTEE={grantee} ORDER BY PRIVILEGE_TYPE')
                result[label + '_grant_privilege_names'] = [r[0] for r in q.fetchall()]
            q.execute('SELECT @@log_bin, @@log_bin_trust_function_creators')
            log_bin, trust = q.fetchone()
            result.update(log_bin=bool(log_bin), log_bin_trust_function_creators=bool(trust))
        c.rollback()
    finally:
        c.close()
    result['disk_after'] = disk()
    with (PUBLIC / 'mysql-metadata.json').open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print('MYSQL_METADATA_READONLY_PASS')


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['selftest']:
            sample = {'ignored': {'nested': ['escaped\\"value', 1, None]},
                      'MYSQL_JDBC_URL': 'jdbc:mysql://example/unused', 'MYSQL_USERNAME': 'app',
                      'MYSQL_PASSWORD': 'synthetic-only', 'ignored2': 'synthetic-unselected'}
            assert selective_strings(io.BytesIO(json.dumps(sample).encode())) == {k: sample[k] for k in FIELDS}
            print('SELECTIVE_CONFIG_SELFTEST_PASS')
        else:
            require(not sys.argv[1:], 'ARGUMENTS')
            main()
    except BaseException as e:
        code = str(e) if isinstance(e, Gate) else 'MYSQL_METADATA_STOP'
        # Never emit third-party exception messages or tracebacks.
        value = {'category': code}
        if isinstance(getattr(e, 'args', None), tuple) and e.args and type(e.args[0]) is int:
            value['vendor_code'] = e.args[0]
        print(json.dumps(value))
        sys.exit(1)
