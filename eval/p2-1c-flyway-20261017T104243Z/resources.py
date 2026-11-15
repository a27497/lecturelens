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
MYSQL_OWNER = 'p2-1c-flyway-20261017T100358Z'
MYSQL_NAME = 'lecturelens-p21c-runtime-mysql-20261017'
MYSQL_IMAGE = 'sha256:3466ba4a4828aa8d46fb7c3bc16b67b781c98413cf4ea0fac6feaa6e881faa26'
REDIS_NAME = 'lecturelens-p21c-redis-20261017t104243z'
REDIS_IMAGE = 'sha256:234c902a2db49461a129e2d4aeff85b28cf20187ed274a67f6e50995fa713c7b'
SCHEMA = 'lecturelens_p21c_20261017_r2'
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
    require(result['Id']==cid and result['Config.Labels'].get('lecturelens.owner')==(MYSQL_OWNER if cid==json.loads((PUBLIC/'mysql-owner.json').read_text())['container_id'] else OWNER), 'RESOURCE_OWNER_MISMATCH')
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
    import shutil
    import pymysql
    os.umask(0o077);disk()
    require(not (PUBLIC/'mysql-owner.json').exists(),'ATTEMPT_EXISTS')
    PRIVATE.mkdir(parents=True,exist_ok=False)
    for name in ('tmp','workspace','extra','runtime'):
        (PRIVATE/name).mkdir()
    previous=ROOT/'eval'/MYSQL_OWNER
    previous_private=ROOT/'.data'/MYSQL_OWNER
    shutil.copyfile(previous/'mysql-owner.json',PUBLIC/'mysql-owner.json')
    shutil.copyfile(previous_private/'app-credentials.json',PRIVATE/'app-credentials.json')
    owner=json.loads((PUBLIC/'mysql-owner.json').read_text())
    info=identity(owner['container_id'])
    require(info['Image']==MYSQL_IMAGE and info['Name']=='/'+MYSQL_NAME,'MYSQL_IDENTITY')
    require(docker('inspect','--format','{{.State.Running}}',owner['container_id'])=='true','MYSQL_NOT_RUNNING')
    require(len(info['Mounts'])==1 and info['Mounts'][0]['Source']==str(previous_private/'mysql-data'),'MYSQL_DATA_MOUNT')
    require(info['HostConfig.PortBindings']=={'3306/tcp':[{'HostIp':'127.0.0.1','HostPort':str(DB_PORT)}]},'MYSQL_BINDING')
    require(info['HostConfig.Memory']==1024**3 and info['HostConfig.NanoCpus']==10**9,'MYSQL_LIMITS')
    require(info['Config.Cmd']==['--skip-log-bin'],'MYSQL_BINLOG_COMMAND')
    for port in (REDIS_PORT,18091):
        with socket.socket() as s: s.bind(('127.0.0.1',port))
    require(docker('image','inspect',REDIS_IMAGE,'--format','{{.Id}}')==REDIS_IMAGE,'LOCAL_REDIS_IMAGE')
    require(not docker('ps','-aq','--filter','name=^/'+REDIS_NAME+'$'),'REDIS_NAME_EXISTS')
    cid=owner['container_id']
    mysql=['exec','-i',cid,'mysql','--protocol=socket','--user=root','--batch','--silent','--skip-column-names']
    require(docker(*mysql,data="SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='"+SCHEMA+"';")== '0','NEW_SCHEMA_EXISTS')
    before=docker(*mysql,data='SELECT version,checksum,success FROM lecturelens_p21c_20261017.flyway_schema_history ORDER BY installed_rank;')
    save('failed-schema-before.json',dict(history_rows=before.splitlines(),sha256=hashlib.sha256(before.encode()).hexdigest()))
    sql=(f'CREATE DATABASE `{SCHEMA}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n'
         f"GRANT ALL PRIVILEGES ON `{SCHEMA}`.* TO '{DB_USER}'@'%';\n")
    require(not docker(*mysql,data=sql),'UNEXPECTED_CREATE_OUTPUT')
    app=json.loads((PRIVATE/'app-credentials.json').read_text())
    with pymysql.connect(host='127.0.0.1',port=DB_PORT,user=app['username'],password=app['password'],database=SCHEMA,charset='utf8mb4',connect_timeout=5,read_timeout=5) as conn:
        with conn.cursor() as q:
            q.execute('SELECT DATABASE(),@@log_bin,(SELECT default_collation_name FROM information_schema.schemata WHERE schema_name=DATABASE())')
            row=q.fetchone();require(row==(SCHEMA,0,'utf8mb4_unicode_ci'),'NEW_SCHEMA_DEFAULTS')
            q.execute('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()')
            require(q.fetchone()==(0,),'NEW_SCHEMA_NOT_EMPTY')
    after=docker(*mysql,data='SELECT version,checksum,success FROM lecturelens_p21c_20261017.flyway_schema_history ORDER BY installed_rank;')
    require(before==after,'FAILED_SCHEMA_CHANGED')
    save('mysql-resource.json',dict(identity=info,new_schema=SCHEMA,charset='utf8mb4',collation='utf8mb4_unicode_ci',tables_before=0,log_bin=False,failed_schema_unchanged=True,persistent_data_retained=True))
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
    print('R2_SCHEMA_AND_INDEPENDENT_REDIS_READY')


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
