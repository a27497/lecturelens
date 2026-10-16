"""Private deployment references stay in process memory; evidence contains safe projections."""
import base64
import hashlib
import hmac
import json
import os
import re
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

import pymysql

ROOT = Path('/home/dev/projects/lecturelens')
PUBLIC = Path(__file__).resolve().parent
PRIVATE = ROOT / '.data' / PUBLIC.name
SCHEMA = 'lecturelens_p21_20261016'
TOPIC = 'lecturelens-p21-20261016T073754Z'
JAR = PRIVATE / 'frozen-candidate.jar'


def utc():
    return datetime.now(timezone.utc).isoformat()


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + '\n')


def append(path, obj):
    with Path(path).open('a') as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=str) + '\n')


def disk():
    s = os.statvfs(ROOT)
    used = (s.f_blocks - s.f_bfree) * s.f_frsize
    available = s.f_bavail * s.f_frsize
    return dict(utc=utc(), used_bytes=used, available_bytes=available,
                percent=100 * used / (used + available),
                headroom_below_85_bytes=.85 * (used + available) - used)


def guard():
    d = disk()
    append(PRIVATE / 'disk-observations.jsonl', d)
    if d['percent'] > 85:
        save(PRIVATE / 'STOP.json', dict(reason='DISK_ABOVE_85', disk=d))
        raise RuntimeError('DISK_ABOVE_85')
    return d


def deployment():
    # These are the existing deployment references, never /proc or a configuration dump.
    env = dict(os.environ)
    for line in (ROOT / '.data/system-model-management/deploy-20261016/system-models.env').read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            env[key] = value.strip().strip('"\'')
    env.update(json.loads((ROOT / '.data/live-access/runtime.json').read_text()))
    supplied = json.loads(Path('/run/credentials/lecturelens-live-backend.service/bailian-asr').read_text())
    for key in ('BAILIAN_ASR_API_KEY', 'BAILIAN_ASR_ENDPOINT', 'BAILIAN_ASR_MODEL'):
        assert supplied.get(key)
        env[key] = supplied[key]
    assert env['BAILIAN_ASR_MODEL'] == 'qwen-audio-3.1-asr-flash'
    env.update(ASR_PROVIDER='bailian', ASR_CHUNK_DURATION='180s', ASR_CHUNK_CONCURRENCY='2',
               ASR_MAX_AUDIO_FILE_SIZE='7MB', ASR_CHUNK_MAX_FILE_SIZE='6MB')
    for key in ('JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS'):
        env.pop(key, None)
    return env


def db(env, schema=None):
    match = re.search(r'jdbc:mysql://([^:/]+):(\d+)/([^?]+)', env['MYSQL_JDBC_URL'])
    return pymysql.connect(host=match[1], port=int(match[2]), user='root',
                           password=env['MYSQL_ROOT_PASSWORD'], database=schema,
                           autocommit=True, charset='utf8mb4',
                           cursorclass=pymysql.cursors.DictCursor)


def query(conn, sql, args=None):
    with conn.cursor() as c:
        c.execute(sql, args)
        return c.fetchall()


def redis_empty(env):
    sock = socket.create_connection((env['REDIS_HOST'], int(env['REDIS_PORT'])), timeout=5)
    f = sock.makefile('rb')
    def command(*args):
        args = [str(v).encode() for v in args]
        sock.sendall(b'*' + str(len(args)).encode() + b'\r\n' + b''.join(
            b'$' + str(len(v)).encode() + b'\r\n' + v + b'\r\n' for v in args))
        def read():
            result=f.readline();kind=result[:1];value=result[1:-2]
            if kind==b'-':raise RuntimeError('REDIS_COMMAND_REJECTED')
            if kind==b'*':return [read() for _ in range(int(value))]
            if kind==b'$':
                size=int(value)
                if size<0:return None
                data=f.read(size);f.read(2);return data.decode()
            return result.decode().strip()
        return read()
    if env.get('REDIS_PASSWORD'):
        assert command('AUTH', env['REDIS_PASSWORD']) == '+OK'
    assert command('SELECT', 15) == '+OK'
    count = int(command('DBSIZE')[1:])
    result = dict(checked_at_utc=utc(), host=env['REDIS_HOST'], port=int(env['REDIS_PORT']), database=15, dbsize=count)
    if count:
        authorization=PUBLIC/'redis-reuse-authorization.json'
        if not authorization.exists():raise RuntimeError('STOP_REDIS15_NONEMPTY')
        allowed=json.loads(authorization.read_text())['allowed_existing_key']
        scanned=command('SCAN',0,'COUNT',100)
        if count!=1 or scanned!=['0',[allowed]] or command('TYPE',allowed)!='+string':
            raise RuntimeError('STOP_REDIS15_UNEXPECTED_KEY')
        result.update(gate='PASS_EXPLICIT_OWNED_KEY_REUSE',existing_key=allowed,ttl_seconds=int(command('TTL',allowed)[1:]),values_read=False,keys_deleted=0)
    else:result['gate']='PASS_EMPTY'
    sock.close()
    save(PRIVATE / 'redis15-deployment-preflight.json', result)
    return result


def jwt(env, user):
    def b64(value):
        return base64.urlsafe_b64encode(value).decode().rstrip('=')
    now = int(time.time())
    header = b64(json.dumps(dict(alg='HS256', typ='JWT'), separators=(',', ':')).encode())
    payload = b64(json.dumps(dict(sub=str(user), type='access', role='ADMIN', status='ACTIVE',
                                 email='p21-eval@localhost.invalid', iat=now, exp=now+3600), separators=(',', ':')).encode())
    unsigned = header + '.' + payload
    return unsigned + '.' + b64(hmac.new(env['JWT_ACCESS_SECRET'].encode(), unsigned.encode(), hashlib.sha256).digest())


def isolated(env):
    out = dict(env)
    out.update(APP_PORT='18091', SERVER_ADDRESS='127.0.0.1', REDIS_DATABASE='15',
               DENSE_RETRIEVAL_ENABLED='false', STUDY_AGENT_ENABLED='false',
               MYSQL_JDBC_URL=re.sub(r'(/)[^/?]+(?=\?)', '/' + SCHEMA, env['MYSQL_JDBC_URL']),
               ROCKETMQ_ANALYSIS_TOPIC=TOPIC, ROCKETMQ_PRODUCER_GROUP=TOPIC+'-producer',
               ROCKETMQ_CONSUMER_GROUP=TOPIC+'-consumer',
               PIPELINE_TRANSLATION_V2_ENABLED='true', PIPELINE_TRANSLATION_CHECKPOINT_ENABLED='true',
               PIPELINE_TRANSLATION_ISOLATED_RUNTIME='true')
    return out
