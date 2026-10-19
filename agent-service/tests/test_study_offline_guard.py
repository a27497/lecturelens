"""The offline preflight fence fails closed before external/provider connections."""

import json
import os
import subprocess
import sys
from pathlib import Path


def test_guard_denies_external_dns_and_production_ports_in_an_inherited_child(tmp_path):
    root = Path(__file__).resolve().parents[2]
    environment = dict(os.environ)
    environment.update(
        PYTHONPATH=str(root / "scripts/eval/preflight_network_guard"),
        LECTURELENS_PREFLIGHT_DB_PORT="25459",
        LECTURELENS_PREFLIGHT_NETWORK_RECORDS=str(tmp_path),
    )
    code = """
import json,socket,sitecustomize
for action in (
 lambda:socket.getaddrinfo('api.deepseek.com',443),
 lambda:socket.socket().connect(('203.0.113.1',443)),
 lambda:socket.socket().connect(('127.0.0.1',15439)),
):
 try: action()
 except PermissionError: pass
 else: raise AssertionError('offline fence allowed a forbidden connection')
print(json.dumps(sitecustomize.COUNTS))
"""
    result = subprocess.run(
        [sys.executable, "-c", code], env=environment, capture_output=True, text=True, timeout=10, check=True
    )
    assert json.loads(result.stdout)["denied_connections"] == 3
    record = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert record["denied_connections"] == 3
