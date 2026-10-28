"""Isolated browser + signed Python API + PostgreSQL. Java business/auth are fixtures."""
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import uvicorn
from psycopg.conninfo import conninfo_to_dict

from lecturelens_agent.app import create_app
from lecturelens_agent.store import VectorStore
from lecturelens_agent.study.provider import MockProvider
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyError, StudyStore

ROOT = Path(__file__).resolve().parents[2]
SECRET = 'p7-local-fixture-signing-secret-only-32-bytes'
dsn = os.environ['AGENT_TEST_DATABASE_URL']
config = conninfo_to_dict(dsn)
assert config['host'] == '127.0.0.1' and config['port'] == '25701' and config['dbname'].endswith('_test')
for port in (25702, 25703):
    with socket.socket() as check:
        check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        check.bind(('127.0.0.1', port))
original_connect = socket.socket.connect


def local_only(sock, address):
    if isinstance(address, tuple) and address[0] not in {'127.0.0.1', '::1'}:
        raise AssertionError('Mock external socket forbidden')
    return original_connect(sock, address)


socket.socket.connect = local_only


class Authority:
    def read(self, scope, action='CHECK', **arguments):
        if scope['owner_id'] != 427 or not scope['course_id'].startswith('p7-browser-') or scope['revision'] != 1:
            raise StudyError('COURSE_UNAVAILABLE_OR_CHANGED', 404)
        keys = arguments.get('evidence_ids', ['e1', 'e2', 'e3'])
        return {k: scope[k] for k in ('owner_id','course_id','revision')} | {'evidence': [] if action == 'CHECK' else [
            {'evidence_id': key, 'text': 'Binary search halves the remaining interval.',
             'start_ms': int(key[1:])*1000, 'end_ms': (int(key[1:])+1)*1000, 'source_type': 'SUBTITLE'}
            for key in keys
        ]}


VectorStore(dsn).initialize()
runtime = StudyRuntime(StudyStore(dsn), Authority(), MockProvider())
app = create_app(SimpleNamespace(embedder=SimpleNamespace(index_version='mock-offline')), SECRET, runtime)
server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=25702, log_level='warning', access_log=False))
thread = threading.Thread(target=server.run)
thread.start()
try:
    deadline = time.monotonic()+30
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError('Isolated API did not start')
        time.sleep(.1)
    subprocess.run(['/opt/node/bin/node', 'frontend/tests/browser/flashcards.mjs'], cwd=ROOT, check=True)
finally:
    server.should_exit = True
    thread.join(timeout=40)
    assert not thread.is_alive()
