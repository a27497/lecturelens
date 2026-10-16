"""Read one earlier owned transcript; evaluate frozen prompt code without claiming a fresh pipeline run."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
from urllib.parse import urlsplit

ROOT=Path('/home/dev/projects/lecturelens')
PUBLIC=Path(__file__).resolve().parent
PRIVATE=ROOT/'.data'/PUBLIC.name
sys.path.insert(0,str(ROOT/'eval/p2-1b-pipeline-20261016T122904Z'))
from runtime_support import deployment,db,query,disk,utc


def main():
    assert not (PUBLIC/'materials-supplement.json').exists()
    env=deployment();frozen=json.loads((PUBLIC/'candidate-artifact.json').read_text())
    assert hashlib.file_digest(Path(frozen['jar_path']).open('rb'),'sha256').hexdigest()==frozen['jar_sha256']
    d=disk();assert d['percent']<=85 and d['available_bytes']>=2**31
    earlier=[json.loads(line) for line in (ROOT/'eval/p2-1b-pipeline-20261016T122904Z/trials.jsonl').read_text().splitlines()]
    trial=next(r for r in earlier if r.get('phase')=='terminal' and r['trial_id']=='normal-algorithms-1')
    c=db(env,'lecturelens_p21_20261016')
    source=query(c,'SELECT source_full_text,translated_full_text FROM task_full_text_result WHERE task_id=%s AND user_id=9 AND target_language=\'zh-CN\'',(trial['task_id'],))
    assert len(source)==1
    cfg=json.loads(query(c,'SELECT config_json FROM system_model_config_version WHERE version=10')[0]['config_json'])
    route=cfg['defaults']['LEARNING_PACKAGE']['route']
    assert route['model']=='lecturelens-local-qwen' and urlsplit(route['baseUrl']).hostname in ('127.0.0.1','localhost')
    payload=dict(baseUrl=route['baseUrl'],model=route['model'],source=source[0]['source_full_text'],translated=source[0]['translated_full_text'])
    intent=dict(utc=utc(),kind='SUPPLEMENTAL_MATERIALS_ONLY_REUSED_EVIDENCE',parent_trial=trial['trial_id'],
        parent_task_id=trial['task_id'],candidate_jar_sha256=frozen['jar_sha256'],
        source_sha256=hashlib.sha256(payload['source'].encode()).hexdigest(),translated_sha256=hashlib.sha256(payload['translated'].encode()).hexdigest(),
        runtime_source_sha256=hashlib.sha256((PUBLIC/'runtime/MaterialsSupplement.java').read_bytes()).hexdigest(),
        fresh_full_chain=False,worker_started=False,configuration_writes=0,asr_calls=0,translation_calls=0,disk_before=d)
    (PUBLIC/'materials-supplement-intent.json').write_text(json.dumps(intent,indent=2)+'\n')
    stopping=threading.Event();violations=[]
    args=['java','-Djava.io.tmpdir='+str(PRIVATE/'tmp'),'-cp',':'.join(str(PRIVATE/p) for p in ('runtime/extra','runtime/BOOT-INF/classes','runtime/BOOT-INF/lib/*')),
          'com.example.courselingo.learning.service.MaterialsSupplement',str(PRIVATE)]
    with (PRIVATE/'materials-supplement.log').open('w') as log:
        process=subprocess.Popen(args,env=env,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True,user='dev',group='dev')
        def monitor():
            while not stopping.wait(2):
                obs=disk()
                with (PRIVATE/'disk-observations.jsonl').open('a') as f:f.write(json.dumps(obs)+'\n')
                if obs['percent']>85:
                    violations.append(obs);process.terminate();return
        thread=threading.Thread(target=monitor,daemon=True);thread.start()
        try:process.communicate(json.dumps(payload),timeout=930)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=20)
        finally:stopping.set();thread.join(timeout=3)
    result=json.loads((PRIVATE/'supplement-summary.json').read_text())
    result.update(intent,exit_code=process.returncode,disk_after=disk(),disk_violations=violations)
    (PUBLIC/'materials-supplement.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:result.get(k) for k in ('exit_code','structured_valid','long_course_quality_valid','exception_class')}))
    print('PHYSICAL_LLM_CALLS',len(result['calls']))


if __name__=='__main__':main()
