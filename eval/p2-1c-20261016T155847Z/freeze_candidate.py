#!/usr/bin/env python3
"""Archive a locally built candidate; never loads runtime/provider configuration or starts services."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]
PUBLIC=Path(__file__).resolve().parent
PRIVATE=ROOT/".data"/PUBLIC.name


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    record=PUBLIC/"candidate-artifact.json"
    archive=PRIVATE/"candidate"/"backend.jar"
    if record.exists() or archive.exists():
        raise SystemExit("existing candidate identity must not be overwritten")
    for filename in ("stage4-backend-full-02.json","stage4-frontend-full-01.json"):
        result=json.loads((PUBLIC/filename).read_text())
        assert result["exit_code"]==0 and result["total"]["tests"]>0
        assert all(result["total"][field]==0 for field in ("failures","errors","skipped"))
    build=json.loads((PUBLIC/"stage4-package.json").read_text())
    assert build["exit_code"]==0
    changed=subprocess.check_output(["git","diff","HEAD","--name-only","--","backend/src/main","backend/pom.xml"],cwd=ROOT,text=True).splitlines()
    assert not changed, "commit production source before freezing"
    untracked=subprocess.check_output(["git","ls-files","--others","--exclude-standard","backend/src/main"],cwd=ROOT,text=True).splitlines()
    assert not untracked, "untracked production source must not enter an unrecorded candidate"
    source=ROOT/"backend/target/courselingo-backend-0.0.1-SNAPSHOT.jar"
    import os
    stat=os.statvfs(ROOT);used=(stat.f_blocks-stat.f_bfree)*stat.f_frsize;available=stat.f_bavail*stat.f_frsize
    assert used/(used+available)<=.85 and .85*(used+available)-used-source.stat().st_size>=2*1024**3, "DISK_GATE_STOP"
    test_patch=subprocess.check_output(["git","diff","HEAD","--","backend/src/test"],cwd=ROOT)
    (PUBLIC/"stage4-test-fixture.patch").write_bytes(test_patch)
    archive.parent.mkdir(parents=True,mode=0o700)
    shutil.copyfile(source,archive);archive.chmod(0o600)
    source_files=subprocess.check_output(["git","ls-files","backend/src/main","backend/pom.xml"],cwd=ROOT,text=True).splitlines()
    result={"at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "source_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
            "jar_path":str(archive.relative_to(ROOT)),"jar_sha256":digest(archive),"jar_bytes":archive.stat().st_size,
            "source_files":{name:digest(ROOT/name) for name in source_files},
            "intended_options_sha256":digest(PUBLIC/"candidate-options.json"),
            "test_fixture_patch_sha256":hashlib.sha256(test_patch).hexdigest(),
            "python_full_suite":"未测：等待独立 PostgreSQL 启动许可",
            "runtime_started":False,"real_trials_submitted":0,"full_acceptance":False}
    record.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({key:result[key] for key in ("source_commit","jar_sha256","jar_bytes","full_acceptance")},ensure_ascii=False))


if __name__=="__main__":
    main()
