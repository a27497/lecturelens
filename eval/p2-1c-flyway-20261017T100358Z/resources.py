#!/usr/bin/env python3
"""Manage this attempt's independently labelled dependencies only."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

ROOT = Path('/home/dev/projects/lecturelens')
PUBLIC = Path(__file__).resolve().parent
PRIVATE = ROOT / '.data' / PUBLIC.name
OWNER = PUBLIC.name
MYSQL_NAME = 'lecturelens-p21c-runtime-mysql-20261017'
MYSQL_IMAGE = 'sha256:3466ba4a4828aa8d46fb7c3bc16b67b781c98413cf4ea0fac6feaa6e881faa26'
REDIS_NAME = 'lecturelens-p21c-redis-20261017t100358z'
REDIS_IMAGE = 'sha256:234c902a2db49461a129e2d4aeff85b28cf20187ed274a67f6e50995fa713c7b'
SCHEMA = 'lecturelens_p21c_20261017'
DB_USER = 'p21c_app'
DB_PORT = 33319
REDIS_PORT = 33318


class Gate(Exception):
    pass


def require(ok, category):
    if not ok:
        raise Gate(category)


def save(name, value):
    with (PUBLIC / name).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def disk():
    s = os.statvfs(ROOT)
    u, a = (s.f_blocks-s.f_bfree)*s.f_frsize, s.f_bavail*s.f_frsize
    m = .85*(u+a)-u
    d = dict(at_utc=dt.datetime.now(dt.timezone.utc).isoformat(), used_bytes=u, available_bytes=a,
             usage_percent=100*u/(u+a), margin_to_85_bytes=m)
    with (PUBLIC/'disk.jsonl').open('a') as f:
        f.write(json.dumps(d)+'\n')
    require(u/(u+a) <= .85 and m >= 2*1024**3, 'DISK_GATE')
    return d


def docker(*args, data=None):
    p = subprocess.run(['docker', *args], input=data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       text=True, timeout=45)
    require(p.returncode == 0, 'OWNED_DOCKER_OPERATION_FAILED')
    return p.stdout.strip()


def identity(cid):
    fields = ('Id','Name','Image','Config.Labels','HostConfig.PortBindings','Mounts',
              'HostConfig.Memory','HostConfig.NanoCpus','HostConfig.RestartPolicy','Config.Cmd')
    values = docker('inspect', '--format', '\n'.join('{{json .'+f+'}}' for f in fields), cid).splitlines()
    result = dict(zip(fields, map(json.loads, values)))
    require(result['Id']==cid and result['Config.Labels'].get('lecturelens.owner')==OWNER, 'RESOURCE_OWNER_MISMATCH')
    return result


def command(sock, stream, *args):
    parts = [str(v).encode() for v in args]
    sock.sendall(b'*'+str(len(parts)).encode()+b'\r\n'+b''.join(b'$'+str(len(v)).encode()+b'\r\n'+v+b'\r\n' for v in parts))
    def read():
        line=stream.readline();kind,data=line[:1],line[1:-2]
        require(kind!=b'-','OWNED_REDIS_ERROR')
        if kind==b'*': return [read() for _ in range(int(data))]
        if kind==b'$':
            n=int(data);payload=stream.read(n);require(stream.read(2)==b'\r\n','REDIS_PROTOCOL');return payload.decode()
        return line.decode().strip()
    return read()


def redis_empty():
    owner=json.loads((PUBLIC/'redis-owner.json').read_text())
    require(identity(owner['container_id'])['Image']==REDIS_IMAGE,'REDIS_IMAGE')
    with socket.create_connection(('127.0.0.1',REDIS_PORT),timeout=3) as sock, sock.makefile('rb') as f:
        server=dict(line.split(':',1) for line in command(sock,f,'INFO','server').splitlines() if ':' in line and not line.startswith('#'))
        require(command(sock,f,'SELECT',15)=='+OK','REDIS_SELECT')
        for _ in range(2):
            require(command(sock,f,'DBSIZE')==':0','REDIS_NOT_EMPTY')
            require(command(sock,f,'SCAN',0,'COUNT',100)==['0',[]],'REDIS_NOT_EMPTY')
    return hashlib.sha256(server['run_id'].encode()).hexdigest()


def prepare():
    os.umask(0o077);disk()
    require(not (PUBLIC/'mysql-owner.json').exists(),'ATTEMPT_EXISTS')
    PRIVATE.mkdir(parents=True,exist_ok=False)
    for name in ('tmp','workspace','extra','runtime','mysql-data'):
        (PRIVATE/name).mkdir()
    for image in (MYSQL_IMAGE,REDIS_IMAGE):
        require(docker('image','inspect',image,'--format','{{.Id}}')==image,'LOCAL_IMAGE_MISMATCH')
    for name in (MYSQL_NAME,REDIS_NAME):
        require(not docker('ps','-aq','--filter','name=^/'+name+'$'),'DEPENDENCY_NAME_OCCUPIED')
    for port in (DB_PORT,REDIS_PORT,18091):
        with socket.socket() as s: s.bind(('127.0.0.1',port))
    cid=docker('run','--pull=never','-d','--name',MYSQL_NAME,'--restart=no','--label','lecturelens.owner='+OWNER,
               '--publish',f'127.0.0.1:{DB_PORT}:3306','--memory=1g','--cpus=1','--log-driver=none',
               '--mount',f'type=bind,src={PRIVATE / "mysql-data"},dst=/var/lib/mysql',
               '--env','MYSQL_ALLOW_EMPTY_PASSWORD=yes','--env','MYSQL_DATABASE='+SCHEMA,MYSQL_IMAGE,'--skip-log-bin')
    save('mysql-owner.json',dict(container_id=cid,name=MYSQL_NAME,owner=OWNER,data_dir=str(PRIVATE/'mysql-data')))
    require(identity(cid)['Image']==MYSQL_IMAGE,'MYSQL_IMAGE')
    until=time.monotonic()+100
    while True:
        disk()
        p=subprocess.run(['docker','exec',cid,'mysqladmin','ping','--protocol=socket','--user=root','--silent'],
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
        # Initialization also runs a temporary socket server. The final TCP
        # listener must exist before creating the application account.
        if p.returncode==0:
            try:
                with socket.create_connection(('127.0.0.1',DB_PORT),timeout=1): break
            except OSError: pass
        require(time.monotonic()<until,'MYSQL_READINESS_TIMEOUT');time.sleep(1)
    password=secrets.token_urlsafe(32)
    # New disposable root uses an empty password over the container socket only.
    # Neither an existing root password nor any environment file is read.
    sql=(f"CREATE USER '{DB_USER}'@'%' IDENTIFIED BY '{password}';\n"
         f"GRANT ALL PRIVILEGES ON `{SCHEMA}`.* TO '{DB_USER}'@'%';\n")
    require(not docker('exec','-i',cid,'mysql','--protocol=socket','--user=root','--batch','--silent',data=sql),'UNEXPECTED_MYSQL_OUTPUT')
    with (PRIVATE/'app-credentials.json').open('x') as f:
        json.dump(dict(username=DB_USER,password=password,port=DB_PORT),f)
    del password,sql
    info=identity(cid)
    require(info['HostConfig.PortBindings']=={'3306/tcp':[{'HostIp':'127.0.0.1','HostPort':str(DB_PORT)}]},'MYSQL_BINDING')
    require(info['HostConfig.Memory']==1024**3 and info['HostConfig.NanoCpus']==10**9,'MYSQL_RESOURCE_LIMIT')
    require(len(info['Mounts'])==1 and info['Mounts'][0]['Source']==str(PRIVATE/'mysql-data'),'MYSQL_MOUNT')
    save('mysql-resource.json',dict(identity=info,log_bin_disabled_by_command=True,persistent_data_retained=True,root_password_read=False))
    rid=docker('run','--pull=never','-d','--name',REDIS_NAME,'--label','lecturelens.owner='+OWNER,
               '--network','host','--read-only','--user',f'{os.getuid()}:{os.getgid()}',
               '--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','64',
               '--memory','256m','--cpus','1','--log-driver','none',
               '--tmpfs',f'/data:rw,noexec,nosuid,size=67108864,uid={os.getuid()},gid={os.getgid()},mode=0700',
               '--workdir','/data',REDIS_IMAGE,'redis-server','--bind','127.0.0.1','--port',str(REDIS_PORT),
               '--protected-mode','yes','--save','','--appendonly','no','--daemonize','no','--loglevel','warning')
    save('redis-owner.json',dict(container_id=rid,name=REDIS_NAME,owner=OWNER))
    time.sleep(1)
    runhash=redis_empty()
    save('redis-resource.json',dict(identity=identity(rid),database=15,dbsize=0,full_empty_scans=2,server_run_id_sha256=runhash))
    save('dependencies-ready.json',dict(ready=True,disk=disk(),mysql_schema=SCHEMA,mysql_port=DB_PORT,redis_port=REDIS_PORT))
    print('INDEPENDENT_DEPENDENCIES_READY')


def stop_redis():
    owner=json.loads((PUBLIC/'redis-owner.json').read_text())
    info=identity(owner['container_id']);require(info['Image']==REDIS_IMAGE,'REDIS_IMAGE')
    docker('stop','--time','20',owner['container_id']);docker('rm',owner['container_id'])
    save('redis-cleanup.json',dict(container_id=owner['container_id'],stopped=True,removed=True))
    print('OWNED_REDIS_REMOVED_MYSQL_RETAINED')


if __name__=='__main__':
    try:
        if sys.argv[1:]==['prepare']: prepare()
        elif sys.argv[1:]==['stop-redis']: stop_redis()
        else: raise Gate('ARGUMENTS')
    except BaseException as e:
        save('resource-stop.json',dict(category=str(e) if isinstance(e,Gate) else type(e).__name__))
        print('RESOURCE_STOP');sys.exit(1)
