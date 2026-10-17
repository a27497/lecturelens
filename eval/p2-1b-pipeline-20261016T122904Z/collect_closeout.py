"""Safe final projections and bounded private-record manifest; no lifecycle mutations."""
import hashlib
import subprocess
from runtime_support import *


def main():
    env=deployment();conn=db(env,SCHEMA)
    rows=[json.loads(line) for line in (PUBLIC/'trials.jsonl').read_text().splitlines()]
    tasks=[r['task_id'] for r in rows if r['phase']=='terminal']
    assert len(set(tasks))==11
    call_owners={}
    for task in tasks:
        evidence=json.loads((PUBLIC/'runtime-evidence'/f'{task}.json').read_text())
        for call in evidence['calls']:call_owners[call['id']]=task
    materials=[]
    other_errors=[]
    for path in sorted((PRIVATE/'errors').glob('*.json')):
        r=json.loads(path.read_text());excerpt=r.get('private_error_excerpt') or ''
        try:detail=json.loads(excerpt).get('error',{})
        except json.JSONDecodeError:detail={}
        summary=json.loads(r['request_summary']) if isinstance(r['request_summary'],str) else r['request_summary']
        item=dict(call_id=r['id'],task_id=call_owners[r['id']],http_status=r['http_status'],request_body_bytes=r['request_body_bytes'],
                              request_body_hash=r['request_body_hash'],request_max_tokens=summary.get('max_tokens'),
                              response_chars=r['response_chars'],response_truncated=bool(r['response_truncated']),
                              private_excerpt_sha256=hashlib.sha256(excerpt.encode()).hexdigest() if excerpt else None,
                              error_type=detail.get('type'),input_tokens=detail.get('n_prompt_tokens'),context_limit=detail.get('n_ctx'))
        if r['http_status']==400:materials.append(item)
        else:other_errors.append(item)
    save(PUBLIC/'materials-errors.json',materials)
    save(PUBLIC/'other-http-errors.json',other_errors)
    objects=[]
    for task in tasks:
        objects.append(dict(task_id=task,
                            artifact_objects=query(conn,'SELECT artifact_type,object_key FROM artifact_file WHERE task_id=%s AND user_id=9',(task,)),
                            keyframe_objects=query(conn,'SELECT object_key FROM video_keyframe WHERE task_id=%s AND user_id=9',(task,))))
    save(PUBLIC/'owned-objects-confirmed.json',dict(utc=utc(),objects=objects,source_objects_read_only=True,
                                                submission_prefixes_are_unverified_hints=True,no_object_cleanup_performed=True))
    ids=subprocess.check_output(['docker','ps','-q'],text=True).split()
    lines=subprocess.check_output(['docker','inspect','--format','{{.Name}} {{.Id}} {{.State.StartedAt}}',*ids],text=True).splitlines()
    live=subprocess.check_output(['systemctl','show','lecturelens-live-backend','-p','MainPID','-p','ExecMainStartTimestamp'],text=True).splitlines()
    before=json.loads((PUBLIC/'protected-services-before.json').read_text())
    save(PUBLIC/'protected-services-after.json',dict(utc=utc(),containers=lines,live_backend=live,
          protected_container_identities_unchanged=sorted(before['containers'])==sorted(lines),
          live_backend_identity_unchanged=before['live_backend']==live))
    events=[json.loads(line) for line in (PRIVATE/'process-events.jsonl').read_text().splitlines()]
    observations=[json.loads(line) for line in (PRIVATE/'disk-observations.jsonl').read_text().splitlines()]
    save(PUBLIC/'execution-closeout.json',dict(utc=utc(),sigkill_count=sum(e['action']=='SIGKILL' for e in events),
          starts=sum(e['action']=='START' for e in events),process_events=events,
          disk_samples=len(observations),disk_max_percent=max(d['percent'] for d in observations),
          disk_final=disk(),normal_terminal_trials=10,recovery_terminal_trials=1,
          occupied_18091=bool(subprocess.check_output(['ss','-Hltn','sport = :18091'],text=True).strip())))
    private_files=[p for p in PRIVATE.rglob('*') if p.is_file() and p.suffix in ['.json','.jsonl','.log']
                   and not any(part in ['runtime','tmp'] for part in p.relative_to(PRIVATE).parts)]
    manifest=''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p)+'\n' for p in sorted(private_files))
    (PRIVATE/'RAW_SHA256SUMS').write_text(manifest)
    save(PUBLIC/'private-record-manifest.json',dict(private_directory=str(PRIVATE),record_count=len(private_files),
          raw_manifest_path=str(PRIVATE/'RAW_SHA256SUMS'),raw_manifest_sha256=hashlib.sha256(manifest.encode()).hexdigest(),
          private_content_committed=False))
    print('P21B_CLOSEOUT_COLLECTED')


if __name__=='__main__':main()
