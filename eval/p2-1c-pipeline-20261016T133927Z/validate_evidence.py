"""Validate integrity and declared scope; never treats a blocked acceptance suite as passing."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path('/home/dev/projects/lecturelens');PUBLIC=Path(__file__).resolve().parent


def main():
    candidate=json.loads((PUBLIC/'candidate-artifact.json').read_text())
    assert hashlib.file_digest(Path(candidate['jar_path']).open('rb'),'sha256').hexdigest()==candidate['jar_sha256']
    assert hashlib.sha256((PUBLIC/'candidate.patch').read_bytes()).hexdigest()==candidate['patch_sha256']
    for file,expected in candidate['source_files'].items():assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==expected,file
    tests=json.loads((PUBLIC/'tests.json').read_text())
    assert tests['total']==dict(tests=148,failures=0,errors=0,skipped=0)
    gates=json.loads((PUBLIC/'runtime-gates.json').read_text())
    assert len(gates['allowed_existing_keys'])==12
    assert set(x['key'] for x in gates['existing_keys'])<=set(gates['allowed_existing_keys'])
    assert gates['redis_gate']=='PASS_EXPLICIT_TWELVE_OWNED_KEYS_REUSE'
    assert gates['asr_gate']=='BLOCKED_ACCESS_DENIED_UNPURCHASED'
    assert gates['normal_trials_submitted']==gates['recovery_trials_submitted']==gates['sigkill_count']==0
    for directory in (PUBLIC,PUBLIC/'postfreeze-asr-preflight'):
        d=json.loads((directory/'asr-diagnostic.json').read_text())
        assert d['http_status']==403 and d['provider_error_code']=='AccessDenied.Unpurchased'
        assert d['physical_call_limit']==1 and d['retries']==0 and d['configuration_writes']==0
    supplement=json.loads((PUBLIC/'materials-supplement.json').read_text())
    assert supplement['fresh_full_chain'] is False and supplement['publication'] is False
    assert supplement['asr_calls']==supplement['translation_calls']==0
    assert supplement['candidate_jar_sha256']==candidate['jar_sha256']
    assert supplement['runtime_source_sha256']==hashlib.sha256((PUBLIC/'runtime/MaterialsSupplement.java').read_bytes()).hexdigest()
    for call in supplement['calls']:
        assert call['prompt_tokens']<=call['input_limit']<=8192*70//100
        assert call['estimated_input_tokens']<=call['input_limit']
        assert call['prompt_tokens']+call['max_output_tokens']+256<=8192
    assert not supplement['disk_violations']
    assert not subprocess.check_output(['ss','-Hltn','sport = :18091'],text=True).strip()
    print('INTEGRITY_PASS; FORMAL_10_PLUS_1_BLOCKED_ASR_ACCESS_DENIED; NOT_AN_ACCEPTANCE_PASS')


if __name__=='__main__':main()
