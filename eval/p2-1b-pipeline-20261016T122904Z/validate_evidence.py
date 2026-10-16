"""Check real evidence consistency; integrity PASS never changes failed acceptance outcomes."""
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

PUBLIC=Path(__file__).resolve().parent
ROOT=PUBLIC.parents[1]


def main():
    report=json.loads((PUBLIC/'summary.json').read_text())
    journal=[json.loads(line) for line in (PUBLIC/'trials.jsonl').read_text().splitlines()]
    submitted=[r for r in journal if r['phase']=='submitted']
    terminal=[r for r in journal if r['phase']=='terminal']
    assert len(submitted)==len(terminal)==11
    assert len({r['task_id'] for r in submitted})==11
    assert Counter(r['kind'] for r in terminal)==dict(NORMAL=10,RECOVERY=1)
    normal=[r for r in terminal if r['kind']=='NORMAL']
    assert [(r['source_id'],r['repeat']) for r in normal]==[(s,i) for s in ['algorithms','calculus','economics','linear','probability'] for i in [1,2]]
    all_ids=[];asr=[];translation=[]
    for row in normal:
        d=json.loads((PUBLIC/'runtime-evidence'/f"{row['task_id']}.json").read_text())
        assert d['policy'][0]['config_version']==10 and d['policy'][0]['engine_version']=='translation-v2.5'
        assert d['routes'][0]['translation_source']=='DATABASE' and d['routes'][0]['translation_model']=='deepseek-flash'
        coverage=d['coverage'][0]
        assert coverage['source_segments']>0 and coverage['source_segments']==int(coverage['nonempty_translations'])
        assert len(d['publication'])==1 and d['publication'][0]['config_version']==10
        assert row['status']=='FAILED' and not row['full_chain_success']
        local_asr=[c for c in d['calls'] if c['feature']=='ASR_TRANSCRIPTION']
        local_translation=[c for c in d['calls'] if c['feature']=='TRANSLATION_FULL_TEXT']
        assert len(local_asr)==d['timing'][0]['asr_attempt_count']==d['timing'][0]['clip_count']
        assert all(c['http_status']==200 and c['status']=='FINISHED' for c in local_asr+local_translation)
        assert all(b['status']=='SUCCEEDED' and b['attempt_count']<=1 for b in d['batches'])
        seq=[e['event_seq'] for e in d['scheduler']]
        assert seq==sorted(set(seq))
        assert all(1<=e['new_window']<=4 and 0<=e['inflight']<=4 for e in d['scheduler'])
        for c in local_asr+local_translation:
            assert c['prompt_tokens'] is not None and c['completion_tokens'] is not None
            assert c['total_tokens']==c['prompt_tokens']+c['completion_tokens']
        all_ids.extend(c['id'] for c in d['calls']);asr+=local_asr;translation+=local_translation
    assert len(all_ids)==len(set(all_ids))
    assert len(asr)==884 and len(translation)==527
    asr_reference=sum((Decimal(c['prompt_tokens'])*Decimal('.8')+Decimal(c['completion_tokens'])*Decimal('2.7'))/1_000_000 for c in asr)
    translation_lower=sum(Decimal(c['cost_lower']) for c in translation)
    assert abs(asr_reference-Decimal(str(report['normal_totals']['asr_catalog_reference_cny'])))<Decimal('1e-10')
    assert abs(translation_lower-Decimal(str(report['normal_totals']['translation_known_lower_usd'])))<Decimal('1e-10')
    assert len(report['normal_materials_failures'])==10
    assert all(e['error_type']=='exceed_context_size_error' and e['input_tokens']>e['context_limit']==8192 for e in report['normal_materials_failures'])
    recovery=report['recovery']
    assert not recovery['trial']['fault_injected'] and not recovery['proof']['recovery_demonstration_completed']
    assert recovery['proof']['asr_http_200']==69 and recovery['proof']['asr_http_403']==1
    assert recovery['proof']['network_outcome_unknown']==1 and recovery['proof']['translation_calls']==0
    close=json.loads((PUBLIC/'execution-closeout.json').read_text())
    assert close['sigkill_count']==0 and close['starts']==1 and not close['occupied_18091']
    assert close['disk_max_percent']<85
    runtime=json.loads((PUBLIC/'runtime-closeout.json').read_text())
    assert runtime['worker_stopped'] and runtime['production_config_unchanged']
    assert json.loads((PUBLIC/'protected-services-after.json').read_text())['live_backend_identity_unchanged']
    for f in ['candidate-artifact.json','instrumentation-artifact.json']:
        artifact=json.loads((PUBLIC/f).read_text())
        if f=='candidate-artifact.json':
            assert hashlib.file_digest(Path(artifact['jar_path']).open('rb'),'sha256').hexdigest()==artifact['jar_sha256']
            assert all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==h for path,h in artifact['source_files'].items())
        else:assert all(hashlib.sha256((PUBLIC/path).read_bytes()).hexdigest()==h for path,h in artifact['files'].items())
    reviews=json.loads((PUBLIC/'quality-reviews.json').read_text())
    assert len(reviews)==10 and sum(r['sample_count'] for r in reviews)==30
    result=dict(integrity='PASS',normal_full_chain_acceptance='FAILED_0_OF_10',
                translation_publication='10_OF_10',recovery_acceptance='NOT_DEMONSTRATED_ASR_403',
                recomputed_normal_asr_catalog_reference_cny=str(asr_reference),
                recomputed_normal_translation_known_lower_usd=str(translation_lower),
                failed_trials_preserved=True,protected_container_list_equality=False,
                container_discrepancy_record='container-identity-reconciliation.json')
    (PUBLIC/'evidence-integrity.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
