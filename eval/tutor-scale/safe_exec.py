"""Start a clean Python interpreter with the existing socket fence (PG only)."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if len(sys.argv) < 3:
    raise SystemExit("usage: safe_exec.py NETWORK_RECORD_DIRECTORY SCRIPT [args...]")
records = Path(sys.argv[1]).resolve()
records.mkdir(parents=True, exist_ok=False)
env = {k: os.environ[k] for k in ("PATH", "HOME", "USER", "LANG", "LC_ALL") if k in os.environ}
env.update(
    PYTHONPATH=os.pathsep.join(
        [
            str(ROOT / "scripts/eval/preflight_network_guard"),
            str(ROOT / "agent-service/src"),
        ]
    ),
    PYTHONNOUSERSITE="1",
    LECTURELENS_PREFLIGHT_DB_PORT="25841",
    LECTURELENS_PREFLIGHT_NETWORK_RECORDS=str(records),
)
# Startup assertion fails closed if sitecustomize cannot install its fence.
code = "import os,runpy,sys; assert os.environ.get('LECTURELENS_PREFLIGHT_GUARDED')=='1'; p=sys.argv[1]; sys.argv=sys.argv[1:]; sys.path.insert(0,os.path.dirname(os.path.abspath(p))); runpy.run_path(p,run_name='__main__')"
os.execve(sys.executable, [sys.executable, "-c", code, *sys.argv[2:]], env)
