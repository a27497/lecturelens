#!/usr/bin/env python3
"""One approved application start; ciphertext copy goes only through a pipe."""
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import resource
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import pymysql
from resources import ROOT, PUBLIC, PRIVATE, SCHEMA, DB_USER, DB_PORT, MYSQL_IMAGE, disk, identity, redis_empty, require, Gate, save

JAR=ROOT/'.data/p2-1c-20261016T155847Z/candidate/backend.jar'
JAR_HASH='35e8f63b6895e1d69fe45b51be45c196b4585c140b6a6c52b370a9922438d3b0'
OPTIONS=ROOT/'eval/p2-1c-20261016T155847Z/candidate-options.json'
SOURCE_SCHEMA='lecturelens_p21_20261016'
TABLES={'system_model_config_version':'version','system_model_provider':'id','system_model':'id',
        'system_model_binding':'feature_key','system_model_config_state':'id'}
MIGRATED=threading.Event()
STOP=threading.Event()
MARKERS=set()
CHILD=None


def utc(): return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def append(name,row):
    with (PUBLIC/name).open('a') as f: f.write(json.dumps(row)+'\n')


def target():
    app=json.loads((PRIVATE/'app-credentials.json').read_text())
    require(app['username']==DB_USER and app['port']==DB_PORT,'TARGET_CREDENTIAL_IDENTITY')
    return pymysql.connect(host='127.0.0.1',port=DB_PORT,user=DB_USER,password=app['password'],
                           database=SCHEMA,charset='utf8mb4',autocommit=False,
                           connect_timeout=5,read_timeout=10,write_timeout=5)


def query(c,sql,args=()):
    with c.cursor() as q: q.execute(sql,args);return q.fetchall()


def source_readonly():
    spec=importlib.util.spec_from_file_location('approved_mysql_reader',ROOT/'eval/p2-1c-flyway-20261017T093741Z/mysql_metadata.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with (ROOT/'.data/live-access/runtime.json').open('rb',buffering=0) as f:
        cfg=module.selective_strings(f)
    require(cfg['MYSQL_USERNAME'].lower()!='root','SOURCE_NONROOT_REQUIRED')
    require(cfg['MYSQL_JDBC_URL'].startswith('jdbc:mysql://'),'SOURCE_JDBC')
    uri=urlsplit(cfg['MYSQL_JDBC_URL'][5:])
    require(uri.hostname and uri.username is None and uri.password is None,'SOURCE_JDBC')
    require(not re.search(r'(?i)(password|user|socket|pipe)=',uri.query),'SOURCE_JDBC_INLINE_CONFIG')
    c=pymysql.connect(host=uri.hostname,port=uri.port or 3306,user=cfg['MYSQL_USERNAME'],password=cfg['MYSQL_PASSWORD'],
                      database=SOURCE_SCHEMA,charset='utf8mb4',autocommit=False,connect_timeout=5,read_timeout=10,write_timeout=5)
    del cfg
    with c.cursor() as q:
        q.execute('SET SESSION TRANSACTION READ ONLY')
        q.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
        q.execute("SELECT DATABASE()=%s,SUBSTRING_INDEX(CURRENT_USER(),'@',1)<>'root'",(SOURCE_SCHEMA,))
        require(q.fetchone()==(1,1),'SOURCE_IDENTITY')
        q.execute('SELECT current_version FROM system_model_config_state WHERE id=1')
        require(q.fetchone()==(10,),'SOURCE_VERSION')
    return c


def row_hash(h,row):
    data=json.dumps(list(row),ensure_ascii=False,separators=(',',':'),default=str).encode()
    h.update(len(data).to_bytes(8,'big'));h.update(data)


def verify_migrations(c):
    require(query(c,'SELECT DATABASE(),@@log_bin,@@log_bin_trust_function_creators')[0][0:2]==(SCHEMA,0),'TARGET_BINLOG_OR_SCHEMA')
    expected={r['version'].removeprefix('V'):r['flyway_checksum'] for r in json.loads(
        (ROOT/'eval/p2-1c-startup-diagnostic-20261017T064402Z/offline-migrations.json').read_text())['resources']}
    history=query(c,'SELECT version,checksum,success FROM flyway_schema_history ORDER BY installed_rank')
    require(len(history)==32 and all(v in expected and expected[v]==h and ok==1 for v,h,ok in history),'FROZEN_MIGRATIONS')
    tables=('asr_scheduler_state','asr_chunk_checkpoint','asr_scheduler_event','asr_result_cache')
    triggers=('asr_state_immutable_input','asr_chunk_immutable_input')
    require(len(query(c,'SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN (%s,%s,%s,%s)',tables))==4,'V32_TABLES')
    require(len(query(c,'SELECT trigger_name FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name IN (%s,%s)',triggers))==2,'V32_TRIGGERS')
    return dict(versions=32,all_success=True,all_frozen_checksums_match=True,v32_tables=4,v32_triggers=2,log_bin=False)


def copy_config():
    disk()
    owner=json.loads((PUBLIC/'mysql-owner.json').read_text())
    require(identity(owner['container_id'])['Image']==MYSQL_IMAGE,'TARGET_CONTAINER_IDENTITY')
    source=source_readonly();dest=target();pipe=None
    try:
        migrations=verify_migrations(dest)
        require(query(dest,'SELECT current_version FROM system_model_config_state WHERE id=1')==((0,),),'TARGET_INITIAL_STATE')
        require(query(dest,'SELECT COUNT(*) FROM system_model_config_version')==((1,),),'TARGET_INITIAL_VERSIONS')
        for table in ('system_model_provider','system_model','system_model_binding'):
            require(query(dest,f'SELECT COUNT(*) FROM `{table}`')==((0,),),'TARGET_NOT_EMPTY')
        dest.rollback()
        pipe=subprocess.Popen(['docker','exec','-i',owner['container_id'],'mysql','--protocol=socket','--user=root',
                               '--default-character-set=utf8mb4','--batch','--silent',SCHEMA],
                              stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True)
        def send(sql): pipe.stdin.write(sql+';\n')
        send("SET SESSION sql_mode='STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'")
        send('START TRANSACTION')
        # Only this newly migrated isolated target is changed. Copy version zero
        # too, including its original timestamp, so complete row hashes agree.
        send('DELETE FROM system_model_config_state')
        send('DELETE FROM system_model_config_version')
        hashes={};counts={};columns={}
        for table,pk in TABLES.items():
            disk()
            cols=[r[0] for r in query(source,'SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s ORDER BY ORDINAL_POSITION',(table,))]
            require(cols and all(re.fullmatch(r'[a-zA-Z0-9_]+',x) for x in cols),'COLUMN_IDENTIFIERS')
            columns[table]=cols;select=','.join('`'+x+'`' for x in cols)
            where=' WHERE version<=10' if table=='system_model_config_version' else ''
            h=hashlib.sha256();count=0
            with source.cursor(pymysql.cursors.SSCursor) as cursor:
                cursor.execute(f'SELECT {select} FROM `{table}`{where} ORDER BY `{pk}`')
                for row in cursor:
                    row_hash(h,row);count+=1
                    require(count<=10000,'CONFIG_COPY_BOUND')
                    values=','.join(pymysql.converters.escape_item(value,'utf8mb4') for value in row)
                    send(f'INSERT INTO `{table}` ({select}) VALUES ({values})')
            hashes[table]=h.digest();counts[table]=count
        send('COMMIT');pipe.stdin.close()
        require(pipe.wait(timeout=20)==0,'CONFIG_PIPE_IMPORT_FAILED')
        result={}
        for table,pk in TABLES.items():
            h=hashlib.sha256();count=0
            select=','.join('`'+x+'`' for x in columns[table])
            for row in query(dest,f'SELECT {select} FROM `{table}` ORDER BY `{pk}`'):
                row_hash(h,row);count+=1
            same=count==counts[table] and h.digest()==hashes[table]
            require(same,'CONFIG_HASH_MISMATCH')
            result[table]=dict(rows=count,content_hash_equal=same)
        require(query(dest,'SELECT current_version FROM system_model_config_state WHERE id=1')==((10,),),'TARGET_VERSION')
        require(query(dest,'SELECT COUNT(*) FROM analysis_task')==((0,),),'TARGET_TASKS')
        require(query(dest,'SELECT COUNT(*) FROM task_outbox')==((0,),),'TARGET_OUTBOX')
        save('config-copy.json',dict(version=10,tables=result,source_readonly=True,direct_pipe=True,sql_written_to_disk=False))
        save('migration-result.json',migrations)
        (PRIVATE/'copy.complete').write_text('VERIFIED')
    finally:
        if pipe is not None and pipe.poll() is None:
            if pipe.stdin and not pipe.stdin.closed: pipe.stdin.close()
            try: pipe.wait(timeout=10)
            except subprocess.TimeoutExpired: pipe.terminate();pipe.wait(timeout=5)
        source.rollback();source.close();dest.close()


def sanitized_stream(stream):
    allowed={'P21_FINAL_ISOLATION_GATE_PASS','P21_FINAL_ISOLATION_GATE_FAILED','P21_MIGRATIONS_COMPLETE','P21_CAPTURE_GATE_PASS'}
    for line in iter(stream.readline,''):
        value=line.strip()
        if value in allowed:
            MARKERS.add(value);append('events.jsonl',dict(at_utc=utc(),marker=value))
            if value=='P21_MIGRATIONS_COMPLETE': MIGRATED.set()
        match=re.fullmatch(r'P21_STARTUP_CAUSE index=(\d{1,2}) kind=(SQL|FLYWAY|STARTUP)(?: sqlState=([A-Z0-9]{5}))?(?: vendorCode=(-?\d{1,11}))?',value)
        if match:
            row=dict(index=int(match[1]),kind=match[2])
            if match[3]: row['sqlState']=match[3]
            if match[4]: row['vendorCode']=int(match[4])
            append('startup-causes.jsonl',row)


def java():
    cp=':'.join(str(PRIVATE/p) for p in ('extra','runtime/BOOT-INF/classes','runtime/BOOT-INF/lib/*'))
    args=['/usr/bin/java','-XX:ErrorFile=/dev/null','-Djdk.httpclient.HttpClient.log=',
          '-Djava.io.tmpdir='+str(PRIVATE/'tmp'),'-Dp21.private='+str(PRIVATE),'-Dp21.options='+str(OPTIONS),
          '-cp',cp,'com.example.courselingo.systemmodel.P21HealthBootstrap',
          '--spring.config.additional-location=file:/home/dev/projects/lecturelens-asr-b/.data/asr-b-deploy/asr-bailian.yml',
          '--server.address=127.0.0.1','--server.port=18091','--spring.datasource.url=${MYSQL_JDBC_URL}',
          '--spring.datasource.username=${MYSQL_USERNAME}','--spring.datasource.password=${MYSQL_PASSWORD}',
          '--spring.flyway.enabled=true','--spring.flyway.validate-on-migrate=true','--spring.flyway.baseline-on-migrate=false',
          '--courselingo.redis.host=127.0.0.1','--courselingo.redis.port=33318','--courselingo.redis.database=15','--courselingo.redis.password=',
          '--courselingo.task.runner.workspace-dir='+str(PRIVATE/'workspace'),
          '--courselingo.retrieval.enabled=false','--courselingo.study.enabled=false',
          '--courselingo.storage.minio.bucket=${STORAGE_MINIO_BUCKET}','--courselingo.storage.minio.endpoint=${STORAGE_MINIO_ENDPOINT}']
    topic='lecturelens-p21-20261016T073754Z'
    for name,suffix in [('analysis-topic',''),('producer-group','-producer'),('consumer-group','-consumer')]:
        args.append('--courselingo.mq.rocketmq.'+name+'='+topic+suffix)
    for key,value in json.loads(OPTIONS.read_text())['properties'].items():
        args.append('--'+key+'='+(str(value).lower() if isinstance(value,bool) else str(value)))
    return args


def main():
    global CHILD
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    require(pwd.getpwuid(os.getuid()).pw_name=='dev' and os.getuid()!=0,'DEV_REQUIRED')
    require(Path(os.environ.get('CREDENTIALS_DIRECTORY','')).name=='lecturelens-p21c-health-20261017t104243z.service','UNIT_CREDENTIAL_IDENTITY')
    require(digest(JAR)==JAR_HASH,'FROZEN_JAR_HASH')
    disk();redis_empty()
    owner=json.loads((PUBLIC/'mysql-owner.json').read_text());require(identity(owner['container_id'])['Image']==MYSQL_IMAGE,'MYSQL_OWNER')
    with target() as c:
        require(query(c,'SELECT @@log_bin')==((0,),),'BINLOG_MUST_BE_OFF')
        require(query(c,'SELECT default_collation_name FROM information_schema.schemata WHERE schema_name=DATABASE()')==(('utf8mb4_unicode_ci',),),'SCHEMA_COLLATION')
        require(query(c,'SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()')==((0,),),'SCHEMA_MUST_BE_EMPTY')
    with socket_probe(): pass
    save('start-permit-consumed.json',dict(at_utc=utc(),approved_application_start=2,maximum_starts_without_further_approval=1))
    # Forward only the established service-manager references, not the caller's
    # general environment or a deserialized runtime configuration.
    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','LOGNAME','LANG','CREDENTIALS_DIRECTORY',
         'SYSTEM_MODEL_CONFIG_ENABLED','FLYWAY_ENABLED','SYSTEM_MODEL_MASTER_KEY','SYSTEM_MODEL_PROBE_ALLOWED_ORIGINS')}
    CHILD=subprocess.Popen(java(),env=env,cwd=PRIVATE,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    thread=threading.Thread(target=sanitized_stream,args=(CHILD.stdout,),daemon=True);thread.start()
    ticks=Path(f'/proc/{CHILD.pid}/stat').read_text().rsplit(')',1)[1].split()[19]
    save('java-identity.json',dict(pid=CHILD.pid,start_ticks=ticks,uid=os.getuid(),frozen_jar_sha256=JAR_HASH))
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    until=time.monotonic()+180;copied=False;attempts=0
    while True:
        disk();require(not STOP.is_set(),'STOP_REQUESTED')
        if CHILD.poll() is not None:
            thread.join(timeout=5);raise Gate('APPLICATION_START_FAILED')
        if MIGRATED.is_set() and not copied:
            copy_config();copied=True
        if copied:
            attempts+=1
            try:
                with opener.open('http://127.0.0.1:18091/actuator/health',timeout=2) as response:
                    body=response.read(65536)
                    if response.status==200 and json.loads(body).get('status')=='UP':
                        require({'P21_FINAL_ISOLATION_GATE_PASS','P21_MIGRATIONS_COMPLETE','P21_CAPTURE_GATE_PASS'}<=MARKERS,'STARTUP_GATES')
                        with target() as c:
                            require(query(c,'SELECT current_version FROM system_model_config_state WHERE id=1')==((10,),),'FINAL_VERSION')
                            require(query(c,'SELECT COUNT(*) FROM analysis_task')==((0,),),'FINAL_TASK_COUNT')
                        save('health.json',dict(at_utc=utc(),url='http://127.0.0.1:18091/actuator/health',http_status=200,status='UP',
                                               response_sha256=hashlib.sha256(body).hexdigest(),attempts=attempts))
                        save('startup-result.json',dict(result='HEALTHY',health='UP',markers=sorted(MARKERS),course_tasks_submitted=0,application_starts=1))
                        return
            except (urllib.error.URLError,TimeoutError,ConnectionError): pass
        require(time.monotonic()<until,'APPLICATION_READINESS_TIMEOUT');time.sleep(1)


def socket_probe():
    import socket
    s=socket.socket();s.bind(('127.0.0.1',18091));return s


if __name__=='__main__':
    signal.signal(signal.SIGTERM,lambda *_:STOP.set());signal.signal(signal.SIGINT,lambda *_:STOP.set())
    category='COMPLETED'
    try: main()
    except Gate as e: category=str(e)
    except pymysql.MySQLError as e: category='MYSQL_ERROR_'+str(e.args[0]) if e.args and type(e.args[0]) is int else 'MYSQL_ERROR'
    except BaseException as e: category='RUNTIME_'+type(e).__name__.upper()
    finally:
        if CHILD is not None and CHILD.poll() is None:
            CHILD.terminate()
            try: CHILD.wait(timeout=45)
            except subprocess.TimeoutExpired: category='JAVA_TERM_INCOMPLETE'
        save('closeout-service.json',dict(at_utc=utc(),category=category,java_exit=CHILD.poll() if CHILD else None,
                                          application_starts=1 if CHILD else 0,used_sigkill=False,mysql_data_retained=True))
    print(category);sys.exit(0 if category=='COMPLETED' else 1)
