"""Authorized 10 serial trials plus one independent worker recovery; immutable journal."""
import argparse
import signal
import subprocess
import threading
import traceback
import httpx
from prepare_runtime import command
from runtime_support import *

worker=None
worker_identity=None
stopping=threading.Event()


def identity(pid):
    p=Path('/proc')/str(pid)
    return dict(pid=pid,start_ticks=p.joinpath('stat').read_text().rsplit(')',1)[1].split()[19],
                cwd=str(p.joinpath('cwd').resolve()),jar_sha256=hashlib.file_digest(JAR.open('rb'),'sha256').hexdigest())


def signal_worker(sig, group=False):
    if worker is None or worker.poll() is not None:return
    assert identity(worker.pid)==worker_identity,'worker identity mismatch'
    if group:os.killpg(worker.pid,sig)
    else:os.kill(worker.pid,sig)
    append(PRIVATE/'process-events.jsonl',dict(utc=utc(),action=signal.Signals(sig).name,group=group,**worker_identity))


def monitor():
    while not stopping.wait(2):
        try:guard()
        except Exception:
            signal_worker(signal.SIGTERM,group=True)
            stopping.set()
            return


def start(env, label):
    global worker,worker_identity
    guard()
    args=command(env,'run')
    args.remove('run')
    args+=['--spring.config.additional-location=file:/home/dev/projects/lecturelens-asr-b/.data/asr-b-deploy/asr-bailian.yml']
    with (PRIVATE/'worker.log').open('a') as log:
        worker=subprocess.Popen(args,cwd=PRIVATE,env=isolated(env),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    worker_identity=identity(worker.pid)
    save(PRIVATE/'worker-identity.json',worker_identity)
    append(PRIVATE/'process-events.jsonl',dict(utc=utc(),action='START',label=label,**worker_identity))
    until=time.monotonic()+90
    with httpx.Client(trust_env=False,timeout=2) as client:
        while time.monotonic()<until:
            guard()
            if worker.poll() is not None:raise RuntimeError('ISOLATED_WORKER_START_FAILED')
            try:
                if client.get('http://127.0.0.1:18091/actuator/health').status_code==200:
                    print(json.dumps(dict(worker_ready=worker.pid,label=label)),flush=True);return
            except httpx.HTTPError:pass
            time.sleep(1)
    raise RuntimeError('WORKER_READINESS_TIMEOUT')


def api(client,env,method,path,**kwargs):
    guard()
    response=client.request(method,path,headers={'Authorization':'Bearer '+jwt(env,9)},**kwargs)
    if response.status_code>=400:
        save(PRIVATE/'last-api-error.json',dict(utc=utc(),path=path,http_status=response.status_code,code=response.json().get('code')))
        raise RuntimeError('LOCAL_API_HTTP_'+str(response.status_code)+' '+path)
    body=response.json()
    if body.get('code') not in ('OK','SUCCESS','0',0,200,None):raise RuntimeError('LOCAL_API_CODE_'+str(body['code']))
    return body.get('data',body)


def snapshot(c,task):
    out={}
    selects={
        'task':"SELECT id,status,current_stage,error_code,created_at,started_at,finished_at FROM analysis_task WHERE id=%s AND user_id=9",
        'policy':"SELECT snapshot_id,config_version,engine_version,policy_hash,prompt_hash,deadline FROM pipeline_policy_snapshot WHERE task_id=%s AND user_id=9",
        'routes':"SELECT id,config_version,JSON_UNQUOTE(JSON_EXTRACT(resolved_config_json,'$.routes.TRANSLATION_FULL_TEXT.source')) translation_source,JSON_UNQUOTE(JSON_EXTRACT(resolved_config_json,'$.routes.TRANSLATION_FULL_TEXT.model')) translation_model FROM system_model_execution_snapshot WHERE task_id=%s AND user_id=9 AND operation_type='PIPELINE'",
        'execution':"SELECT event_id,execution_epoch,resume_count,lease_until,completed_at FROM task_execution WHERE task_id=%s",
        'batches':"SELECT batch_no,config_version,parent_batch_no,child_ordinal,depth,source_hash,request_hash,status,result_hash,attempt_count,last_error_category FROM translation_batch WHERE task_id=%s ORDER BY batch_no",
        'attempts':"SELECT id,batch_no,attempt_no,execution_epoch,status,prompt_tokens,completion_tokens,total_tokens,finish_reason,error_category,duration_millis FROM translation_attempt WHERE task_id=%s ORDER BY batch_no,attempt_no",
        'calls':"SELECT id,feature,config_version,execution_epoch,translation_attempt_id,model,response_model_sha256,provider_fingerprint_sha256,status,http_status,prompt_tokens,completion_tokens,total_tokens,reasoning_tokens,cache_hit_tokens,cache_miss_tokens,finish_reason,error_category,validation_check,usage_status,duration_millis,price_card_id,price_tier,currency,cost_lower,cost_upper,audio_start_millis,audio_end_millis,timing_source,silence_plan_hash,silence_segmentation,created_at,completed_at FROM model_call_attempt WHERE task_id=%s AND user_id=9 ORDER BY created_at,id",
        'scheduler':"SELECT event_seq,event_time,execution_epoch,batch_no,attempt_no,old_window,new_window,inflight,window_epoch,success_streak,reason,cooldown_until_millis FROM translation_scheduler_event WHERE task_id=%s AND user_id=9 ORDER BY event_seq",
        'checkpoints':"SELECT step_name,source_fingerprint,result_hash,execution_epoch,completed_at FROM pipeline_step_checkpoint WHERE task_id=%s AND user_id=9 ORDER BY step_name",
        'outbox':"SELECT event_id,event_type,status,attempts,protocol_version,execution_epoch,created_at,completed_at FROM task_outbox WHERE task_id=%s ORDER BY created_at,event_id",
        'timing':"SELECT source_fingerprint,plan_hash,asr_attempt_count,clip_count,detected_silence_millis FROM transcript_timing_plan WHERE task_id=%s AND user_id=9",
        'publication':"SELECT target_language,source_fingerprint,config_version FROM transcript_alignment_publication WHERE task_id=%s AND user_id=9",
        'coverage':"SELECT COUNT(*) source_segments,SUM(t.id IS NOT NULL) translated_segments,SUM(t.translated_text IS NOT NULL AND CHAR_LENGTH(TRIM(t.translated_text))>0) nonempty_translations FROM subtitle_segment s LEFT JOIN subtitle_translation_segment t ON t.task_id=s.task_id AND t.user_id=s.user_id AND t.segment_index=s.segment_index AND t.target_language='zh-CN' WHERE s.task_id=%s AND s.user_id=9",
    }
    for key,sql in selects.items():out[key]=query(c,sql,(task,))
    return out


def events(task):
    out=[]
    for line in (PRIVATE/'worker.log').read_text(errors='replace').splitlines():
        if 'taskId='+task+' ' not in line:continue
        m=re.search(r'event=pipeline_step_(started|completed|failed).*stepName=(\S+).*',line)
        if m:
            row=dict(event=m[1],step=m[2])
            for key in ['durationMillis','started','completed']:
                value=re.search(r'\b'+key+r'=(\S+)',line)
                if value:row[key]=int(value[1]) if key=='durationMillis' else value[1]
            out.append(row)
    return out


def export(c,row):
    task=row['task_id']
    data=snapshot(c,task)
    save(PUBLIC/'runtime-evidence'/f'{task}.json',data)
    stage_events=events(task)
    save(PUBLIC/'runtime-evidence'/f'{task}-stages.json',stage_events)
    for r in query(c,'SELECT id,request_address,request_body_hash,request_body_bytes,request_summary,http_status,response_chars,response_truncated,private_error_excerpt FROM model_call_attempt WHERE task_id=%s AND user_id=9 AND http_status=400',(task,)):
        r['private_error_excerpt']=re.sub(r'(?i)bearer\s+\S+|sk-[A-Za-z0-9_-]+','[REDACTED]',r['private_error_excerpt'] or '')[:4000]
        save(PRIVATE/'errors'/f"{r['id']}.json",r)
    row.update(phase='terminal',status=data['task'][0]['status'],error_code=data['task'][0]['error_code'],stage_events=stage_events,
               config_version=data['policy'][0]['config_version'],policy_hash=data['policy'][0]['policy_hash'],engine_version=data['policy'][0]['engine_version'],
               full_chain_success=data['task'][0]['status']=='SUCCEEDED' and bool(data['publication']) and bool(data['coverage']) and data['coverage'][0]['source_segments']>0 and data['coverage'][0]['source_segments']==data['coverage'][0]['nonempty_translations'])
    append(PUBLIC/'trials.jsonl',row)
    print(json.dumps({k:row[k] for k in ['trial_id','status','error_code','elapsed_seconds','full_chain_success']},default=str),flush=True)
    return data


def trial(c,client,env,source,replica,kind):
    row=dict(trial_id=f'{kind.lower()}-{source["source_id"]}-{replica}',kind=kind,source_id=source['source_id'],repeat=replica,
             source_sha256=source['source_sha256'],submitted_at_utc=utc())
    append(PRIVATE/'submission-intents.jsonl',row)
    began=time.monotonic()
    created=api(client,env,'POST','/api/tasks',json=dict(uploadId=source['upload_id'],sourceLanguage='en',targetLanguage='zh-CN'))
    task=created['taskId'];row.update(task_id=task,phase='submitted')
    append(PUBLIC/'trials.jsonl',row)
    append(PUBLIC/'owned-objects.jsonl',dict(task_id=task,raw_upload_read_only=source['upload_id'],derived_prefixes=['artifacts/'+task+'/', 'keyframes/'+task+'/']))
    if kind=='RECOVERY':(PRIVATE/'recovery-armed').write_text(task)
    print(json.dumps(dict(submitted=row['trial_id'],task_id=task)),flush=True)
    last=None;recovered=False
    while True:
        guard()
        if stopping.is_set():raise RuntimeError('DISK_MONITOR_STOPPED')
        if worker.poll() is not None:raise RuntimeError('WORKER_DIED')
        info=api(client,env,'GET','/api/tasks/'+task)
        stage=(info.get('status'),info.get('currentStage'))
        if stage!=last:
            append(PRIVATE/'progress.jsonl',dict(utc=utc(),trial_id=row['trial_id'],task_id=task,status=stage[0],stage=stage[1]))
            print(json.dumps(dict(trial_id=row['trial_id'],status=stage[0],stage=stage[1])),flush=True);last=stage
        if kind=='RECOVERY' and not recovered and (PRIVATE/'recovery-barrier-reached').exists():
            assert (PRIVATE/'recovery-barrier-reached').read_text().strip()==task
            time.sleep(1)
            before=snapshot(c,task)
            save(PUBLIC/'recovery-before.json',before)
            assert sum(b['status']=='SUCCEEDED' for b in before['batches'])>=2
            assert any(b['status']!='SUCCEEDED' for b in before['batches'])
            save(PUBLIC/'recovery-process.json',dict(utc=utc(),**worker_identity))
            signal_worker(signal.SIGKILL)
            worker.wait(timeout=10)
            (PRIVATE/'recovery-armed').unlink()
            start(env,'recovery-restart')
            recovered=True
            row['fault_injected']=True
            print('RECOVERY_WORKER_RESTARTED_WAITING_ORIGINAL_LEASE',flush=True)
        if info['status'] in ['SUCCEEDED','FAILED','CANCELED']:
            break
        if time.monotonic()-began>=1800:
            api(client,env,'POST','/api/tasks/'+task+'/cancel')
            row['timeout_censored']=True
            break
        time.sleep(3)
    row['elapsed_seconds']=time.monotonic()-began
    row.setdefault('timeout_censored',False)
    if kind=='RECOVERY':row.setdefault('fault_injected',False)
    data=export(c,row)
    if kind=='RECOVERY':save(PUBLIC/'recovery-after.json',data)


def main():
    env=deployment();guard()
    assert not (PUBLIC/'trials.jsonl').exists(),'Never overwrite or replay a trial'
    redis_empty(env)
    c=db(env,SCHEMA)
    frozen=query(c,'SELECT current_version FROM system_model_config_state WHERE id=1')[0]['current_version']
    assert frozen==10
    before=query(db(env,'courselingo'),'SELECT current_version,config_sha256 FROM system_model_config_state s JOIN system_model_config_version v ON v.version=s.current_version WHERE s.id=1')
    save(PUBLIC/'production-identity-before.json',before)
    sources=json.loads((PRIVATE/'media-references.json').read_text())
    save(PUBLIC/'measurement-protocol.json',dict(started_at_utc=utc(),normal_trials=10,recovery_trials=1,order=[(s['source_id'],r) for s in sources for r in [1,2]],task_timeout_seconds=1800,translation_timeout_seconds=900,serial=True,ddof=1,normal_denominator=10,source_manifest='eval/baseline-asr-20261015/assets.lock.json',candidate_artifact='candidate-artifact.json',instrumentation='runtime/P21Bootstrap.java',translation_initial_window=1,translation_maximum_window=4,process_maximum_inflight=4,provider_credential_export=False))
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    try:
        start(env,'initial')
        with httpx.Client(base_url='http://127.0.0.1:18091',timeout=25,trust_env=False) as client:
            catalog=api(client,env,'GET','/api/admin/system-models/catalog')
            assert catalog['version']==10
            effective=catalog['effective']
            assert effective['TRANSLATION_FULL_TEXT']['source']=='DATABASE' and effective['TRANSLATION_FULL_TEXT']['model']=='deepseek-flash'
            projection={k:{field:v.get(field) for field in ['source','model','baseUrl','maxTokens','timeoutMillis','maxAttempts']} for k,v in effective.items()}
            save(PUBLIC/'isolated-route-preflight.json',dict(version=10,effective=projection,projection_sha256=hashlib.sha256(json.dumps(projection,sort_keys=True).encode()).hexdigest()))
            for source in sources:
                for replica in [1,2]:trial(c,client,env,source,replica,'NORMAL')
            trial(c,client,env,sources[2],1,'RECOVERY')
    except Exception as error:
        save(PRIVATE/'runner-error.json',dict(utc=utc(),type=type(error).__name__,message=str(error),traceback=traceback.format_exc()))
        print('P21_RUNNER_FAILED '+type(error).__name__+'; see private runner-error.json',flush=True)
        raise
    finally:
        signal_worker(signal.SIGTERM,group=True)
        if worker is not None:
            try:worker.wait(timeout=20)
            except subprocess.TimeoutExpired:signal_worker(signal.SIGTERM,group=True)
        stopping.set();thread.join(timeout=3)
        after=query(db(env,'courselingo'),'SELECT current_version,config_sha256 FROM system_model_config_state s JOIN system_model_config_version v ON v.version=s.current_version WHERE s.id=1')
        save(PUBLIC/'production-identity-after.json',after)
        save(PUBLIC/'runtime-closeout.json',dict(utc=utc(),worker_stopped=worker is None or worker.poll() is not None,production_config_unchanged=before==after,disk=guard()))


if __name__=='__main__':main()
