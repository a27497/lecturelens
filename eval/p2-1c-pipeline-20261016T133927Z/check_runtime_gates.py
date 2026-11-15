"""Read-only disk, frozen model identity and explicitly authorized Redis-key gates."""
import json
from pathlib import Path
import socket
import sys

ROOT=Path('/home/dev/projects/lecturelens');PUBLIC=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'eval/p2-1b-pipeline-20261016T122904Z'))
from runtime_support import deployment,db,query,disk,utc


def main():
    env=deployment();d=disk()
    assert d['percent']<=85 and d['available_bytes']>=2**31
    prior=[json.loads(x) for x in (ROOT/'eval/p2-1b-pipeline-20261016T122904Z/trials.jsonl').read_text().splitlines()]
    owned={r['task_id'] for r in prior if r['phase']=='terminal'}|{'task_5b6b1585bf3d4b57b28d91fe9cdf68f2'}
    assert len(owned)==12
    allowed={'cl:t:progress:'+task for task in owned}
    sock=socket.create_connection((env['REDIS_HOST'],int(env['REDIS_PORT'])),timeout=5);f=sock.makefile('rb')
    def command(*args):
        args=[str(a).encode() for a in args]
        sock.sendall(b'*'+str(len(args)).encode()+b'\r\n'+b''.join(b'$'+str(len(a)).encode()+b'\r\n'+a+b'\r\n' for a in args))
        def read():
            line=f.readline();kind=line[:1];value=line[1:-2]
            if kind==b'-':raise RuntimeError('REDIS_COMMAND_REJECTED')
            if kind==b'*':return [read() for _ in range(int(value))]
            if kind==b'$':
                size=int(value)
                if size<0:return None
                data=f.read(size);f.read(2);return data.decode()
            return value.decode()
        return read()
    if env.get('REDIS_PASSWORD'):assert command('AUTH',env['REDIS_PASSWORD'])=='OK'
    assert command('SELECT',15)=='OK'
    size=int(command('DBSIZE'));cursor='0';keys=[]
    while True:
        cursor,part=command('SCAN',cursor,'COUNT',100);keys.extend(part)
        if cursor=='0':break
    assert size==len(keys) and set(keys)<=allowed,'STOP_REDIS15_UNEXPECTED_KEYS'
    existing=[]
    for key in sorted(keys):
        typ=command('TYPE',key);assert typ=='string'
        existing.append(dict(key=key,type=typ,ttl_seconds=int(command('TTL',key))))
    sock.close()
    state={}
    for schema in ('courselingo','lecturelens_p21_20261016'):
        state[schema]=query(db(env,schema),'SELECT current_version,config_sha256 FROM system_model_config_state s JOIN system_model_config_version v ON v.version=s.current_version WHERE s.id=1')[0]
        assert state[schema]['current_version']==10
        assert state[schema]['config_sha256']=='d02d9d3febf59420cac97c80f35e9e74a9572a85486b9e9baee255c2027fe3e4'
    asr=json.loads((PUBLIC/'postfreeze-asr-preflight/asr-diagnostic.json').read_text())
    result=dict(utc=utc(),disk=d,redis_database=15,redis_gate='PASS_EXPLICIT_TWELVE_OWNED_KEYS_REUSE',
        allowed_existing_keys=sorted(allowed),existing_keys=existing,values_read=False,keys_deleted=0,model_state=state,
        asr_gate='BLOCKED_ACCESS_DENIED_UNPURCHASED' if asr['http_status']==403 else 'REQUIRES_ASSESSMENT',
        worker_started=False,normal_trials_submitted=0,recovery_trials_submitted=0,sigkill_count=0)
    (PUBLIC/'runtime-gates.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['redis_gate'],len(existing),result['asr_gate'])


if __name__=='__main__':main()
