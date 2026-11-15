#!/usr/bin/env python3
"""Create/clean exactly this task's disposable MySQL resource; never adopt an existing one."""
import datetime as dt
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = Path(__file__).resolve().parent
NAME = 'lecturelens-translation-mysql-20261016T185217Z'
IMAGE = 'sha256:3466ba4a4828aa8d46fb7c3bc16b67b781c98413cf4ea0fac6feaa6e881faa26'
LABEL = 'translation-mysql-20261016T185217Z'
PORT = 33318


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=40).stdout.strip()


def disk():
    v = os.statvfs(ROOT)
    u, a = (v.f_blocks - v.f_bfree) * v.f_frsize, v.f_bavail * v.f_frsize
    assert u / (u + a) <= .85 and .85 * (u + a) - u >= 2 * 1024 ** 3, 'DISK_GATE_STOP'
    return dict(used_bytes=u, available_bytes=a)


def identity(cid):
    row = json.loads(run('docker', 'inspect', cid))[0]
    # Inspect only the newly-created container. Do not persist its environment.
    return dict(id=row['Id'], name=row['Name'], created=row['Created'], image=row['Image'],
                labels=row['Config']['Labels'], ports=row['HostConfig']['PortBindings'],
                mounts=row['HostConfig']['Binds'], tmpfs=row['HostConfig']['Tmpfs'],
                memory=row['HostConfig']['Memory'], nano_cpus=row['HostConfig']['NanoCpus'])


def save(name, value):
    path = PUBLIC / name
    assert not path.exists(), 'refuse evidence overwrite'
    path.write_text(json.dumps(value, indent=2) + '\n')


def create():
    before = disk()
    assert not (PUBLIC / 'mysql-created.json').exists()
    found = subprocess.run(['docker', 'container', 'inspect', NAME, '--format', '{{.Id}}'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    assert found.returncode != 0, 'container name occupied; stop'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', PORT))
    assert run('docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}') == IMAGE
    cid = run('docker', 'run', '--detach', '--name', NAME, '--restart=no',
              '--label', 'lecturelens.eval=' + LABEL, '--publish', f'127.0.0.1:{PORT}:3306',
              '--memory=1g', '--cpus=1', '--tmpfs', '/var/lib/mysql:rw,size=1073741824',
              '--env', 'MYSQL_ALLOW_EMPTY_PASSWORD=yes', '--env', 'MYSQL_ROOT_HOST=%',
              '--env', 'MYSQL_DATABASE=lecturelens_translation_test', IMAGE, '--skip-log-bin')
    own = identity(cid)
    save('mysql-created.json', dict(identity=own, disk_before=before))
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        probe = subprocess.run(['docker', 'exec', cid, 'mysqladmin', 'ping', '--host=127.0.0.1', '--user=root', '--silent'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        if probe.returncode == 0:
            assert identity(cid) == own
            version = run('docker', 'exec', cid, 'mysql', '-uroot', '-N', '-e', 'SELECT VERSION()')
            save('mysql-ready.json', dict(identity=own, version=version, at_utc=dt.datetime.now(dt.timezone.utc).isoformat(), disk=disk()))
            print('READY ' + NAME + ' MySQL ' + version)
            return
        time.sleep(1)
    raise RuntimeError('owned database readiness timed out; no restart attempted')


def cleanup():
    own = json.loads((PUBLIC / 'mysql-created.json').read_text())['identity']
    assert own['name'] == '/' + NAME and own['image'] == IMAGE
    assert own['labels'].get('lecturelens.eval') == LABEL
    assert identity(own['id']) == own, 'resource identity changed; stop'
    schemas = run('docker', 'exec', own['id'], 'mysql', '-uroot', '-N', '-e',
                  "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME LIKE 'lecturelens%'").splitlines()
    # Record leftovers even on a failed test; deleting this owned container removes only its tmpfs.
    run('docker', 'stop', '--time', '15', own['id'])
    assert identity(own['id']) == own
    run('docker', 'rm', own['id'])
    gone = subprocess.run(['docker', 'inspect', own['id']], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=10).returncode != 0
    assert gone
    save('mysql-cleanup.json', dict(id=own['id'], removed=gone, schemas_before_stop=schemas,
                                  fixture_schemas_all_dropped=schemas == ['lecturelens_translation_test'],
                                  at_utc=dt.datetime.now(dt.timezone.utc).isoformat(), disk=disk()))
    print('REMOVED ' + own['id'])


if __name__ == '__main__':
    assert sys.argv[1:] in (['create'], ['cleanup'])
    create() if sys.argv[1] == 'create' else cleanup()
