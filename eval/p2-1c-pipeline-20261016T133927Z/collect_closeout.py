"""Preserve private test/provider evidence and safe closeout projections; no lifecycle mutations."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path('/home/dev/projects/lecturelens');PUBLIC=Path(__file__).resolve().parent;PRIVATE=ROOT/'.data'/PUBLIC.name
sys.path.insert(0,str(ROOT/'eval/p2-1b-pipeline-20261016T122904Z'))
from runtime_support import disk,utc


def main():
    supplement=json.loads((PUBLIC/'materials-supplement.json').read_text())
    assert supplement['exit_code'] is not None
    pattern='^java -Djava.io.tmpdir='+re.escape(str(PRIVATE/'tmp'))+' .*com.example.courselingo.learning.service.MaterialsSupplement'
    assert subprocess.run(['pgrep','-f',pattern],capture_output=True).returncode==1
    testdir=PRIVATE/'test-reports';testdir.mkdir(exist_ok=True)
    tests=json.loads((PUBLIC/'tests.json').read_text())
    for suite in tests['suites']:
        source=ROOT/'backend/target/surefire-reports'/('TEST-'+suite['suite']+'.xml')
        assert hashlib.sha256(source.read_bytes()).hexdigest()==suite['report_sha256']
        shutil.copyfile(source,testdir/source.name)
    for log in (ROOT/'.data').glob('p2-1c-*.log'):shutil.copyfile(log,PRIVATE/log.name)
    occupied=bool(subprocess.check_output(['ss','-Hltn','sport = :18091'],text=True).strip())
    assert not occupied
    observations=[]
    for path in PRIVATE.glob('*disk-observations*.jsonl'):
        observations.extend(json.loads(line) for line in path.read_text().splitlines())
    final=disk();observations.append(final)
    assert all(d['percent']<=85 for d in observations)
    closeout=dict(utc=utc(),worker_started=False,worker_stopped=True,port_18091_occupied=occupied,
        supplemental_process_exited=True,normal_trials_submitted=0,recovery_trials_submitted=0,sigkill_count=0,
        acceptance='BLOCKED_ASR_ACCESS_DENIED_UNPURCHASED',disk_samples=len(observations),
        disk_max_percent=max(d['percent'] for d in observations),disk_final=final,
        protected_container_lifecycle_commands=0,push=False,deploy=False)
    (PUBLIC/'execution-closeout.json').write_text(json.dumps(closeout,indent=2)+'\n')
    paths=[p for p in PRIVATE.rglob('*') if p.is_file() and p.suffix in ('.json','.jsonl','.log','.xml')
        and not any(part in ('runtime','tmp') for part in p.relative_to(PRIVATE).parts)]
    manifest=''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p)+'\n' for p in sorted(paths))
    (PRIVATE/'RAW_SHA256SUMS').write_text(manifest)
    (PUBLIC/'private-record-manifest.json').write_text(json.dumps(dict(private_directory=str(PRIVATE),record_count=len(paths),
        manifest_path=str(PRIVATE/'RAW_SHA256SUMS'),manifest_sha256=hashlib.sha256(manifest.encode()).hexdigest(),
        raw_content_committed=False),indent=2)+'\n')
    print('P21C_CLOSEOUT_COLLECTED',len(paths))


if __name__=='__main__':main()
