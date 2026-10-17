#!/usr/bin/env python3
"""Manage only the independently labelled Redis container created by this run."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

PUBLIC = Path(__file__).resolve().parent
ROOT = PUBLIC.parents[1]
PLAN = json.loads((PUBLIC / 'environment-delta.json').read_text())


def save(name, value):
    with (PUBLIC / name).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def docker(*args):
    return subprocess.check_output(['docker', *args], timeout=40, text=True, stderr=subprocess.DEVNULL).strip()


def inspect(cid):
    fields = ('Id', 'Config.Labels', 'Mounts', 'HostConfig.NetworkMode', 'HostConfig.ReadonlyRootfs', 'Image')
    values = docker('inspect', '--format', '\n'.join('{{json .' + f + '}}' for f in fields), cid).splitlines()
    return dict(zip(fields, map(json.loads, values)))


def command(sock, f, *args):
    parts = [str(v).encode() for v in args]
    sock.sendall(b'*' + str(len(parts)).encode() + b'\r\n' + b''.join(
        b'$' + str(len(v)).encode() + b'\r\n' + v + b'\r\n' for v in parts))
    def read():
        line = f.readline()
        kind, data = line[:1], line[1:-2]
        if kind == b'-': raise RuntimeError('REDIS_ERROR')
        if kind == b'*': return [read() for _ in range(int(data))]
        if kind == b'$':
            n = int(data); payload = f.read(n); assert f.read(2) == b'\r\n'; return payload.decode()
        return line.decode().strip()
    return read()


def main():
    if sys.argv[1] == 'create':
        s = os.statvfs(ROOT); u = (s.f_blocks - s.f_bfree) * s.f_frsize; a = s.f_bavail * s.f_frsize
        assert u / (u + a) <= .85 and .85 * (u + a) - u >= 2 * 1024**3, 'DISK_GATE'
        assert not (PUBLIC / 'redis-owner.json').exists(), 'ATTEMPT_ALREADY_EXISTS'
        assert not docker('ps', '-aq', '--filter', 'name=^/' + PLAN['redis_container'] + '$'), 'RESOURCE_EXISTS'
        with socket.socket() as probe: probe.bind(('127.0.0.1', PLAN['redis_port']))
        cid = docker('run', '-d', '--name', PLAN['redis_container'], '--label', 'lecturelens.owner=' + PLAN['owner_label'],
                     '--network', 'host', '--read-only', '--user', f'{os.getuid()}:{os.getgid()}',
                     '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--pids-limit', '64',
                     '--memory', '256m', '--cpus', '1', '--log-driver', 'none',
                     '--tmpfs', f'/data:rw,noexec,nosuid,size=67108864,uid={os.getuid()},gid={os.getgid()},mode=0700',
                     '--workdir', '/data', PLAN['redis_image'], 'redis-server', '--bind', '127.0.0.1',
                     '--port', str(PLAN['redis_port']), '--protected-mode', 'yes', '--save', '', '--appendonly', 'no',
                     '--daemonize', 'no', '--loglevel', 'warning')
        save('redis-owner.json', dict(container_id=cid, name=PLAN['redis_container'], owner=PLAN['owner_label']))
        identity = inspect(cid)
        assert identity['Id'] == cid and identity['Config.Labels']['lecturelens.owner'] == PLAN['owner_label']
        assert identity['Image'] == PLAN['redis_image'] and identity['HostConfig.ReadonlyRootfs']
        assert not identity['Mounts'], 'UNEXPECTED_DATA_MOUNT'
        until = time.monotonic() + 10
        while True:
            try:
                sock = socket.create_connection(('127.0.0.1', PLAN['redis_port']), timeout=2)
                break
            except ConnectionRefusedError:
                assert time.monotonic() < until, 'REDIS_READINESS_TIMEOUT'
                time.sleep(.2)
        with sock, sock.makefile('rb') as f:
            server = dict(line.split(':', 1) for line in command(sock, f, 'INFO', 'server').splitlines() if ':' in line and not line.startswith('#'))
            assert int(server['tcp_port']) == PLAN['redis_port']
            assert command(sock, f, 'SELECT', 15) == '+OK'
            snapshots = []
            for _ in range(2):
                count = int(command(sock, f, 'DBSIZE')[1:])
                scan = command(sock, f, 'SCAN', 0, 'COUNT', 100)
                assert count == 0 and scan == ['0', []], 'NEW_REDIS_NOT_EMPTY'
                snapshots.append(dict(dbsize=count, full_scan_unique_count=0, cursor_zero=True))
        save('redis-resource.json', dict(at_utc=dt.datetime.now(dt.timezone.utc).isoformat(), container=identity,
            server_run_id_sha256=hashlib.sha256(server['run_id'].encode()).hexdigest(), redis_version=server['redis_version'],
            database=15, empty_checks=snapshots, shared_host_volumes=False, persistence=False,
            historical_redis_connected=False, data_commands_sent=False))
        print('INDEPENDENT_REDIS_READY_EMPTY')
    elif sys.argv[1] == 'cleanup':
        owner = json.loads((PUBLIC / 'redis-owner.json').read_text()); identity = inspect(owner['container_id'])
        assert identity['Id'] == owner['container_id'] and identity['Config.Labels']['lecturelens.owner'] == PLAN['owner_label'], 'OWNER_MISMATCH'
        docker('stop', '--time', '30', owner['container_id'])
        docker('rm', owner['container_id'])
        assert not docker('ps', '-aq', '--filter', 'id=' + owner['container_id'])
        save('redis-cleanup.json', dict(at_utc=dt.datetime.now(dt.timezone.utc).isoformat(), container_id=owner['container_id'],
             stopped=True, removed=True, persistent_volumes_created=0, historical_redis_touched=False))
        print('OWNED_REDIS_REMOVED')
    else:
        raise RuntimeError('ACTION_NOT_ALLOWED')


if __name__ == '__main__':
    main()
