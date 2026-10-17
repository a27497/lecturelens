#!/usr/bin/env python3
"""Approved dev-unit adapter. Secrets and response bodies never leave process memory."""
import ast
import base64
import datetime as dt
import hashlib
import hmac
import html
import json
import os
from pathlib import Path
import pwd
import re
import resource
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import unicodedata
from urllib.parse import urlsplit, urlunsplit

ROOT = Path('/home/dev/projects/lecturelens')
PUBLIC = Path(__file__).resolve().parent
PRIVATE = ROOT / '.data' / PUBLIC.name
SCHEMA = 'lecturelens_p21_20261016'
TOPIC = 'lecturelens-p21-20261016T073754Z'
OPTIONS = ROOT / 'eval/p2-1c-20261016T155847Z/candidate-options.json'
ASR_YAML = Path('/home/dev/projects/lecturelens-asr-b/.data/asr-b-deploy/asr-bailian.yml')
# Read-only dependency reuse; no installation or changes to prior runtimes.
sys.path.append(str(ROOT / '.data/baseline-asr-20261015/.venv/lib/python3.12/site-packages'))
import httpx
import pymysql
from minio import Minio
from minio.error import S3Error
from num2words import num2words
from rapidfuzz.distance import Levenshtein

STOP = threading.Event()
CHILD = None
OWNED = []
LOG_LOCK = threading.Lock()


class Gate(Exception):
    pass


def require(ok, code):
    if not ok:
        raise Gate(code)


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save(name, value):
    path = PUBLIC / name
    require(not path.exists(), 'EVIDENCE_OVERWRITE')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def append(name, value):
    with LOG_LOCK, (PUBLIC / name).open('a') as f:
        f.write(json.dumps(value, ensure_ascii=False, default=str) + '\n')


def disk():
    s = os.statvfs(ROOT)
    used, available = (s.f_blocks-s.f_bfree)*s.f_frsize, s.f_bavail*s.f_frsize
    d = dict(at_utc=utc(), used_bytes=used, available_bytes=available,
             usage_percent=100*used/(used+available), margin_to_85_bytes=.85*(used+available)-used)
    append('disk.jsonl', d)
    require(used/(used+available) <= .85 and .85*(used+available)-used >= 2*1024**3, 'DISK_GATE')
    require(not STOP.is_set(), 'STOP_REQUESTED')
    return d


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def load_inside_unit():
    require(pwd.getpwuid(os.getuid()).pw_name == 'dev' and os.getuid() != 0, 'DEV_IDENTITY_REQUIRED')
    require(Path(os.environ.get('CREDENTIALS_DIRECTORY', '')).name == 'lecturelens-p21c-worker-20261017.service', 'CREDENTIAL_DIRECTORY_IDENTITY')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    before = json.loads((PUBLIC/'before.json').read_text())
    require(digest(ROOT/before['frozen']['jar_path']) == before['frozen']['jar_sha256'], 'FROZEN_HASH_MISMATCH')
    env = {k: v for k, v in os.environ.items() if k in ('PATH','HOME','LANG','USER','LOGNAME','CREDENTIALS_DIRECTORY',
        'SYSTEM_MODEL_CONFIG_ENABLED','FLYWAY_ENABLED','SYSTEM_MODEL_MASTER_KEY','SYSTEM_MODEL_PROBE_ALLOWED_ORIGINS')}
    # Only names referenced by immutable application configuration may be forwarded.
    app = PRIVATE/'runtime/BOOT-INF/classes/application.yml'
    config_text = app.read_text() + ASR_YAML.read_text()
    names = set(re.findall(r'\$\{([A-Z][A-Z0-9_]*)', config_text))
    names.update(re.findall(r'api-key-env-name:\s*[\"\x27]?([A-Z][A-Z0-9_]*)', config_text))
    names -= {'MYSQL_ROOT_PASSWORD','SYSTEM_MODEL_MASTER_KEY','SYSTEM_MODEL_CONFIG_ENABLED','FLYWAY_ENABLED'}
    cfg = json.loads((ROOT/'.data/live-access/runtime.json').read_text())
    for name in names:
        if name in cfg:
            require(isinstance(cfg[name], str), 'RUNTIME_CONFIG_TYPE')
            env[name] = cfg[name]
    del cfg
    supplied = json.loads((Path(os.environ['CREDENTIALS_DIRECTORY'])/'bailian-asr').read_text())
    for name in ('BAILIAN_ASR_API_KEY','BAILIAN_ASR_ENDPOINT','BAILIAN_ASR_MODEL'):
        require(isinstance(supplied.get(name), str) and bool(supplied[name].strip()), 'ASR_CREDENTIAL_SHAPE')
        env[name] = supplied[name]
    del supplied
    require(env['BAILIAN_ASR_MODEL'] == 'qwen-audio-3.1-asr-flash', 'ASR_MODEL_IDENTITY')
    require(env.get('SYSTEM_MODEL_CONFIG_ENABLED','').lower() == 'true' and env.get('FLYWAY_ENABLED','').lower() == 'true', 'SYSTEM_MODEL_ACTIVATION')
    require(bool(env.get('SYSTEM_MODEL_MASTER_KEY')), 'MASTER_KEY_NOT_INJECTED')
    require(bool(env.get('MYSQL_PASSWORD')) and env.get('MYSQL_USERNAME','').lower() != 'root', 'ISOLATED_APP_ACCOUNT_REQUIRED')
    original = urlsplit(env['MYSQL_JDBC_URL'][5:])
    require(original.scheme == 'mysql' and original.username is None and original.hostname is not None, 'JDBC_SHAPE')
    require(not re.search(r'(?i)(password|user)=', original.query), 'JDBC_INLINE_CREDENTIAL')
    env['MYSQL_JDBC_URL'] = 'jdbc:' + urlunsplit(original._replace(path='/'+SCHEMA))
    env.update(APP_PORT='18091', SERVER_ADDRESS='127.0.0.1', REDIS_DATABASE='15',
        REDIS_HOST='127.0.0.1', REDIS_PORT='33318', REDIS_PASSWORD='',
        DENSE_RETRIEVAL_ENABLED='false', STUDY_AGENT_ENABLED='false', ROCKETMQ_ANALYSIS_TOPIC=TOPIC,
        ROCKETMQ_PRODUCER_GROUP=TOPIC+'-producer', ROCKETMQ_CONSUMER_GROUP=TOPIC+'-consumer',
        ASR_PROVIDER='bailian', ASR_CHUNK_DURATION='180s', ASR_CHUNK_CONCURRENCY='2',
        ASR_MAX_AUDIO_FILE_SIZE='7MB', ASR_CHUNK_MAX_FILE_SIZE='6MB')
    require(all(env.get(k) for k in ('REDIS_HOST','REDIS_PORT','ROCKETMQ_ENDPOINT','STORAGE_MINIO_ENDPOINT',
        'STORAGE_MINIO_BUCKET','STORAGE_MINIO_ACCESS_KEY','STORAGE_MINIO_SECRET_KEY','JWT_ACCESS_SECRET')), 'RUNTIME_DEPENDENCY_MISSING')
    return env


def connect(env):
    uri = urlsplit(env['MYSQL_JDBC_URL'][5:])
    require(uri.path == '/'+SCHEMA and env['MYSQL_USERNAME'].lower() != 'root', 'DB_ISOLATION')
    return pymysql.connect(host=uri.hostname, port=uri.port or 3306, user=env['MYSQL_USERNAME'], password=env['MYSQL_PASSWORD'],
        database=SCHEMA, autocommit=True, charset='utf8mb4', connect_timeout=5, read_timeout=10,
        cursorclass=pymysql.cursors.DictCursor)


def query(c, sql, args=()):
    with c.cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.fetchall()


def redis_gate(env):
    require(env['REDIS_HOST']=='127.0.0.1' and env['REDIS_PORT']=='33318' and not env.get('REDIS_PASSWORD'), 'INDEPENDENT_REDIS_TARGET')
    with socket.create_connection((env['REDIS_HOST'], int(env['REDIS_PORT'])), timeout=5) as sock:
        f = sock.makefile('rb')
        def command(*args):
            args = [str(v).encode() for v in args]
            sock.sendall(b'*'+str(len(args)).encode()+b'\r\n'+b''.join(b'$'+str(len(v)).encode()+b'\r\n'+v+b'\r\n' for v in args))
            def read():
                line=f.readline(); kind=line[:1]; value=line[1:-2]
                require(kind != b'-', 'REDIS_PERMISSION')
                if kind == b'*': return [read() for _ in range(int(value))]
                if kind == b'$':
                    size=int(value)
                    if size < 0: return None
                    data=f.read(size); f.read(2); return data.decode()
                return line.decode().strip()
            return read()
        if env.get('REDIS_PASSWORD'): require(command('AUTH',env['REDIS_PASSWORD']) == '+OK','REDIS_AUTH')
        require(command('SELECT',15)=='+OK','REDIS_SELECT')
        server=dict(line.split(':',1) for line in command('INFO','server').splitlines() if ':' in line and not line.startswith('#'))
        identity=json.loads((PUBLIC/'redis-resource.json').read_text())
        require(hashlib.sha256(server['run_id'].encode()).hexdigest()==identity['server_run_id_sha256'],'INDEPENDENT_REDIS_IDENTITY')
        counts=[]
        for _ in range(2):
            before=int(command('DBSIZE')[1:]);keys=set();cursor='0';pages=0
            while True:
                cursor,batch=command('SCAN',cursor,'COUNT',100);keys.update(batch);pages+=1
                require(pages<=10000,'REDIS_SCAN_LIMIT')
                if cursor=='0':break
            after=int(command('DBSIZE')[1:])
            require(before==after==len(keys)==0,'REDIS15_UNEXPECTED_KEYS')
            counts.append(dict(dbsize_before=before,dbsize_after=after,unique_count=len(keys),pages=pages))
        return dict(database=15,dbsize=0,scans=counts,identity_matches_owned_instance=True,values_read=False,deleted_keys=0)


def storage(env):
    uri=urlsplit(env['STORAGE_MINIO_ENDPOINT'])
    require(uri.scheme in ('http','https') and uri.hostname is not None,'STORAGE_ENDPOINT')
    return Minio(uri.netloc, access_key=env['STORAGE_MINIO_ACCESS_KEY'], secret_key=env['STORAGE_MINIO_SECRET_KEY'], secure=uri.scheme=='https')


def initial_gates(env):
    disk()
    with socket.socket() as s: s.bind(('127.0.0.1',18091))
    c=connect(env)
    require(query(c,'SELECT DATABASE() db')[0]['db']==SCHEMA,'DB_SCHEMA')
    require(query(c,'SELECT current_version FROM system_model_config_state WHERE id=1')[0]['current_version']==10,'CONFIG_VERSION')
    require(query(c,"SELECT COUNT(*) n FROM analysis_task WHERE status IN ('CREATED','QUEUED','RUNNING','RETRYING') AND deleted_at IS NULL")[0]['n']==0,'ISOLATED_PENDING_TASKS')
    require(query(c,"SELECT COUNT(*) n FROM task_outbox WHERE status IN ('PENDING','DELIVERING')")[0]['n']==0,'ISOLATED_PENDING_OUTBOX')
    refs=json.loads((ROOT/'.data/p2-1b-pipeline-20261016T122904Z/media-references.json').read_text())
    assets=json.loads((ROOT/'eval/baseline-asr-20261015/assets.lock.json').read_text())['sources']
    client=storage(env)
    for ref in refs:
        item=next(x for x in assets if x['id']==ref['source_id'])
        require(digest(ROOT/item['evaluation_video_file'])==ref['source_sha256'],'MEDIA_HASH')
        require(digest(ROOT/item['captions_file'])==item['captions_sha256'],'CAPTION_HASH')
        rows=query(c,"SELECT object_key FROM upload_session WHERE id=%s AND user_id=9 AND status='STORED'",(ref['upload_id'],))
        require(len(rows)==1,'UPLOAD_OWNERSHIP')
        client.stat_object(env['STORAGE_MINIO_BUCKET'],rows[0]['object_key'])
    save('source-gates.json',dict(at_utc=utc(),uid=os.getuid(),dev_identity=True,db_schema=SCHEMA,version=10,pending_tasks=0,
        pending_outbox=0,redis=redis_gate(env),media_count=len(refs),raw_media_read_only=True,
        derived_write_scope='new task UUIDs: artifacts/9/<task>/ and keyframes/9/<task>/',workspace=str(PRIVATE/'workspace'),supplier_calls=0))
    return c, refs, assets


def java(env, mode):
    cp=':'.join(str(PRIVATE/p) for p in ('extra','runtime/BOOT-INF/classes','runtime/BOOT-INF/lib/*'))
    args=['/usr/bin/java','-XX:ErrorFile=/dev/null','-Djdk.httpclient.HttpClient.log=', '-Djava.io.tmpdir='+str(PRIVATE/'tmp'),
        '-Dp21.private='+str(PRIVATE),'-Dp21.options='+str(OPTIONS),'-cp',cp,'com.example.courselingo.systemmodel.P21Bootstrap']
    if mode: args.append(mode)
    args += ['--spring.config.additional-location=file:'+str(ASR_YAML), '--server.address=127.0.0.1','--server.port=18091',
        '--spring.datasource.url=${MYSQL_JDBC_URL}','--spring.datasource.username=${MYSQL_USERNAME}','--spring.datasource.password=${MYSQL_PASSWORD}',
        '--courselingo.redis.database=15','--courselingo.mq.rocketmq.analysis-topic='+TOPIC,
        '--courselingo.redis.host=127.0.0.1','--courselingo.redis.port=33318','--courselingo.redis.password=',
        '--courselingo.mq.rocketmq.producer-group='+TOPIC+'-producer','--courselingo.mq.rocketmq.consumer-group='+TOPIC+'-consumer',
        '--courselingo.task.runner.workspace-dir='+str(PRIVATE/'workspace'),'--courselingo.retrieval.enabled=false',
        '--courselingo.study.enabled=false','--courselingo.storage.minio.bucket=${STORAGE_MINIO_BUCKET}',
        '--courselingo.storage.minio.endpoint=${STORAGE_MINIO_ENDPOINT}']
    for k,v in json.loads(OPTIONS.read_text())['properties'].items():args.append('--'+k+'='+str(v).lower() if isinstance(v,bool) else '--'+k+'='+str(v))
    return args


SAFE_KEYS=set('taskId stepName started completed durationMillis wallDurationMillis providerDurationMillis batchCount retryCount totalTokens '
    'httpStatus providerErrorCategory errorType responseFormatUsed attempt batchSegmentCount batchInputChars category oldWindow newWindow inflight '
    'window old_window new_window peakInflight physicalCalls clipCount originalClipCount mergedClipCount originalBytes outputBytes elapsedMillis '
    'cacheHits rateLimits decreases outputBytes inputBytes audioBytes sampleRate channels format'.split())


def sanitized_stream(stream, markers):
    for line in iter(stream.readline,''):
        marker=re.fullmatch(r'(P21_(?:FINAL_ISOLATION_GATE|CAPTURE_GATE)_(?:PASS|FAILED))(?: version=10 fingerprint_equal=true)?\s*',line)
        if marker:
            markers.add(marker[1]); append('events.jsonl',dict(at_utc=utc(),marker=marker[1])); continue
        failure=re.fullmatch(r'P21_CAPTURE_GATE_FAILED ([A-Za-z][A-Za-z0-9]{0,99})\s*',line)
        if failure:
            markers.add('P21_CAPTURE_GATE_FAILED');append('events.jsonl',dict(at_utc=utc(),marker='P21_CAPTURE_GATE_FAILED',error_type=failure[1]));continue
        name=re.search(r'\b(?:message=)?event=(pipeline_step_(?:started|completed|failed)|audio_extraction_observed|llm_(?:full_text_translation_completed|aligned_batch_translation_failed|aligned_batch_translation_completed))\b',line)
        if not name:continue
        row=dict(at_utc=utc(),event=name[1])
        for key,value in re.findall(r'\b([A-Za-z][A-Za-z0-9_]*)=([A-Za-z0-9_.:+-]+)',line):
            if key not in SAFE_KEYS:continue
            if key=='taskId' and not re.fullmatch(r'task_[a-f0-9]{32}|[a-f0-9-]{36}',value):continue
            if len(value)>100:continue
            row[key]=int(value) if value.isdigit() else value
        append('events.jsonl',row)


def bootstrap_preflight(env):
    markers=set()
    p=subprocess.Popen(java(env,'preflight'),env=env,cwd=PRIVATE,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    t=threading.Thread(target=sanitized_stream,args=(p.stdout,markers)); t.start()
    try: code=p.wait(timeout=60)
    except subprocess.TimeoutExpired:
        p.terminate();p.wait(timeout=15);raise Gate('BOOTSTRAP_PREFLIGHT_TIMEOUT')
    finally:t.join(timeout=5)
    save('bootstrap-preflight.json',dict(at_utc=utc(),exit_code=code,markers=sorted(markers),supplier_calls=0))
    require(code==0 and 'P21_FINAL_ISOLATION_GATE_PASS' in markers and 'P21_CAPTURE_GATE_PASS' in markers,'BOOTSTRAP_PREFLIGHT_FAILED')


def token(env):
    def b64(b):return base64.urlsafe_b64encode(b).decode().rstrip('=')
    now=int(time.time())
    h=b64(b'{"alg":"HS256","typ":"JWT"}')
    p=b64(json.dumps(dict(sub='9',type='access',role='ADMIN',status='ACTIVE',email='p21-eval@localhost.invalid',iat=now,exp=now+3600),separators=(',',':')).encode())
    unsigned=h+'.'+p
    return unsigned+'.'+b64(hmac.new(env['JWT_ACCESS_SECRET'].encode(),unsigned.encode(),hashlib.sha256).digest())


def api(client,env,method,path,**kwargs):
    disk()
    require(path.startswith('/api/tasks') or path=='/api/admin/system-models/catalog','API_SCOPE')
    r=client.request(method,path,headers={'Authorization':'Bearer '+token(env)},**kwargs)
    require(r.status_code not in (401,403),'LOCAL_API_PERMISSION')
    require(r.status_code<400,'LOCAL_API_HTTP_FAILURE')
    value=r.json();require(value.get('code') in ('OK','SUCCESS','0',0,200,None),'LOCAL_API_CODE')
    return value.get('data',value)


SELECTS={
    'task':"SELECT id,status,current_stage,error_code,created_at,started_at,finished_at FROM analysis_task WHERE id=%s AND user_id=9",
    'calls':"SELECT id,feature,model,status,http_status,prompt_tokens,completion_tokens,total_tokens,reasoning_tokens,cache_hit_tokens,cache_miss_tokens,finish_reason,error_category,validation_check,usage_status,duration_millis,price_card_id,currency,cost_lower,cost_upper,created_at,completed_at FROM model_call_attempt WHERE task_id=%s AND user_id=9 ORDER BY created_at,id",
    'asr':"SELECT window_size,peak_in_flight,physical_calls,cache_hits,rate_limits,decreases FROM asr_scheduler_state WHERE task_id=%s AND user_id=9",
    'clips':"SELECT chunk_no,start_millis,end_millis,sources_json,attempt_count,status FROM asr_chunk_checkpoint WHERE task_id=%s ORDER BY chunk_no",
    'timing':"SELECT clip_count,asr_attempt_count,detected_silence_millis FROM transcript_timing_plan WHERE task_id=%s AND user_id=9",
    'batches':"SELECT batch_no,depth,parent_batch_no,status,attempt_count,last_error_category FROM translation_batch WHERE task_id=%s ORDER BY batch_no",
    'attempts':"SELECT id,batch_no,status,prompt_tokens,completion_tokens,total_tokens,finish_reason,error_category,duration_millis FROM translation_attempt WHERE task_id=%s ORDER BY batch_no,attempt_no",
    'policy':"SELECT config_version,engine_version,policy_hash,deadline FROM pipeline_policy_snapshot WHERE task_id=%s AND user_id=9",
    'coverage':"SELECT COUNT(*) source_segments,SUM(t.id IS NOT NULL AND CHAR_LENGTH(TRIM(t.translated_text))>0) translated_segments FROM subtitle_segment s LEFT JOIN subtitle_translation_segment t ON t.task_id=s.task_id AND t.user_id=s.user_id AND t.segment_index=s.segment_index AND t.target_language='zh-CN' WHERE s.task_id=%s AND s.user_id=9",
    'publication':"SELECT config_version FROM transcript_alignment_publication WHERE task_id=%s AND user_id=9",
}


def cer(c,task,asset):
    # Identical normalize/caption_text implementations, loaded as functions only; no old harness execution.
    text=(ROOT/'eval/baseline-asr-20261015/score.py').read_text()
    nodes=[n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name in ('normalize','caption_text')]
    scope=dict(unicodedata=unicodedata,html=html,re=re,num2words=num2words)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<frozen-cer-functions>','exec'),scope)
    hypothesis='\n'.join(r['text'] for r in query(c,'SELECT text FROM subtitle_segment WHERE task_id=%s AND user_id=9 ORDER BY segment_index',(task,)))
    if not hypothesis:return dict(status='未测')
    ref=scope['normalize'](scope['caption_text'](ROOT/asset['captions_file'])); hyp=scope['normalize'](hypothesis)
    return dict(edit_distance=Levenshtein.distance(ref,hyp),reference_characters=len(ref),hypothesis_characters=len(hyp),cer=Levenshtein.distance(ref,hyp)/len(ref))


def trial(c,client,env,source,replica,kind,assets):
    row=dict(kind=kind,trial_id=kind.lower()+'-'+source['source_id']+'-'+str(replica),source_id=source['source_id'],repeat=replica,submitted_at_utc=utc())
    append('submission-intents.jsonl',row)
    started=time.monotonic();value=api(client,env,'POST','/api/tasks',json=dict(uploadId=source['upload_id'],sourceLanguage='en',targetLanguage='zh-CN'))
    task=value['taskId'];require(re.fullmatch(r'task_[a-f0-9]{32}',task) is not None,'TASK_ID_SHAPE');OWNED.append(task)
    row.update(task_id=task,phase='submitted');append('trials.jsonl',row)
    last=None;asr403=False
    while True:
        disk();require(CHILD.poll() is None,'JAVA_EXITED')
        calls=query(c,"SELECT http_status FROM model_call_attempt WHERE task_id=%s AND user_id=9 AND feature='ASR_TRANSCRIPTION'",(task,))
        if any(v['http_status']==403 for v in calls):
            asr403=True;api(client,env,'POST','/api/tasks/'+task+'/cancel');break
        info=api(client,env,'GET','/api/tasks/'+task)
        status=info['status']
        if (status,info.get('currentStage'))!=last:
            last=(status,info.get('currentStage'));append('progress.jsonl',dict(at_utc=utc(),trial_id=row['trial_id'],status=status,stage=last[1]))
        if status in ('SUCCEEDED','FAILED','CANCELED'):break
        if time.monotonic()-started>=1800:
            api(client,env,'POST','/api/tasks/'+task+'/cancel');row['timeout_censored']=True;break
        time.sleep(2)
    data={name:query(c,sql,(task,)) for name,sql in SELECTS.items()}
    save('tasks/'+task+'.json',data)
    asr=[r for r in data['calls'] if r['feature']=='ASR_TRANSCRIPTION']
    known=[r for r in asr if r['prompt_tokens'] is not None and r['completion_tokens'] is not None]
    estimate=sum((r['prompt_tokens']*.8+r['completion_tokens']*2.7)/1e6 for r in known)
    row.update(phase='terminal',status=data['task'][0]['status'],error_code=data['task'][0]['error_code'],elapsed_seconds=time.monotonic()-started,
        full_chain_success=data['task'][0]['status']=='SUCCEEDED' and bool(data['publication']) and data['coverage'][0]['source_segments']>0 and data['coverage'][0]['source_segments']==data['coverage'][0]['translated_segments'],
        asr_calls=len(asr),asr_usage_unknown_calls=len(asr)-len(known),asr_cost_cny_directory_estimate=estimate if len(known)==len(asr) and asr else None,
        asr_known_usage_cost_cny_directory_estimate=estimate,cost_label='目录价估算',cer=cer(c,task,next(x for x in assets if x['id']==source['source_id'])))
    append('trials.jsonl',row)
    if asr403:raise Gate('ASR_403_STOP')
    require(asr and all(r['http_status']==200 for r in asr) and data['coverage'][0]['source_segments']>0,'ASR_SMOKE_OR_TRIAL_GATE_FAILED')
    require(not any(r['http_status'] in (401,403) for r in data['calls']),'PROVIDER_PERMISSION')
    if data['asr']:require(data['asr'][0]['cache_hits']==0,'CACHE_OFF_VIOLATION')
    return row


def main():
    global CHILD
    env=load_inside_unit();c,refs,assets=initial_gates(env);bootstrap_preflight(env)
    markers=set();CHILD=subprocess.Popen(java(env,None),env=env,cwd=PRIVATE,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    thread=threading.Thread(target=sanitized_stream,args=(CHILD.stdout,markers),daemon=True);thread.start()
    stat=Path('/proc')/str(CHILD.pid)/'stat'
    save('java-identity.json',dict(pid=CHILD.pid,start_ticks=stat.read_text().rsplit(')',1)[1].split()[19],uid=os.getuid(),frozen_jar_sha256=json.loads((PUBLIC/'before.json').read_text())['frozen']['jar_sha256']))
    with httpx.Client(base_url='http://127.0.0.1:18091',timeout=25,trust_env=False) as client:
        until=time.monotonic()+90
        while True:
            disk();require(CHILD.poll() is None,'APPLICATION_START_FAILED')
            try:
                if client.get('/actuator/health',timeout=2).status_code==200:break
            except httpx.HTTPError:pass
            require(time.monotonic()<until,'APPLICATION_READINESS_TIMEOUT');time.sleep(1)
        require('P21_FINAL_ISOLATION_GATE_PASS' in markers and 'P21_CAPTURE_GATE_PASS' in markers,'APPLICATION_GATES_MISSING')
        catalog=api(client,env,'GET','/api/admin/system-models/catalog')
        require(catalog['version']==10,'CATALOG_VERSION')
        effective=catalog['effective']
        require(effective['TRANSLATION_FULL_TEXT']['source']=='DATABASE' and effective['TRANSLATION_FULL_TEXT']['model']=='deepseek-flash','TRANSLATION_ROUTE')
        save('runtime-ready.json',dict(at_utc=utc(),port=18091,uid=os.getuid(),version=10,cache=False,streamingTranslation=False,materialsParallel=False))
        trial(c,client,env,refs[0],1,'SMOKE',assets)
        for source in refs:
            for replica in (1,2):trial(c,client,env,source,replica,'NORMAL',assets)
        save('completed.json',dict(at_utc=utc(),smoke=1,formal_submitted=10))


def handle_signal(signum,frame):
    STOP.set()


if __name__=='__main__':
    signal.signal(signal.SIGTERM,handle_signal);signal.signal(signal.SIGINT,handle_signal)
    code='COMPLETED'
    try:main()
    except Gate as e:code=str(e)
    except PermissionError:code='PERMISSION_STOP'
    except pymysql.MySQLError as e:code='MYSQL_ERROR_'+str(e.args[0]) if e.args and isinstance(e.args[0],int) else 'MYSQL_ERROR'
    except S3Error as e:code='STORAGE_'+(e.code if e.code in ('AccessDenied','NoSuchBucket','NoSuchKey','InvalidAccessKeyId','SignatureDoesNotMatch') else 'ERROR')
    except BaseException as e:code='RUNTIME_'+type(e).__name__.upper()
    finally:
        if CHILD is not None and CHILD.poll() is None:
            CHILD.terminate()
            try:CHILD.wait(timeout=45)
            except subprocess.TimeoutExpired:code='JAVA_TERM_INCOMPLETE'
        save('closeout-service.json',dict(at_utc=utc(),code=code,owned_tasks=OWNED,java_exit=CHILD.poll() if CHILD else None,used_sigkill=False))
    print(code,flush=True)
    sys.exit(0 if code=='COMPLETED' else 1)
