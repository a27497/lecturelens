#!/usr/bin/env python3
"""No-key HTTP smoke test against isolated Docker infrastructure; owns only its backend child process."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import tempfile
import zipfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env.demo.local')
    parser.add_argument('--project', required=True, help='Isolated Compose project used for database assertions')
    args = parser.parse_args()
    import re
    assert re.fullmatch(r'lecturelens-demo-[a-z0-9-]{1,32}', args.project), 'Expected an isolated demo project'
    env = os.environ.copy()
    for line in args.env_file.read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            key, value = line.split('=', 1)
            env[key] = value
    for key in ('MOCK_ASR_ENABLED', 'DEMO_MOCK_LLM_ENABLED'):
        assert env.get(key) == 'true', f'{key} must be true for no-key smoke test'
    for key in ('SILICONFLOW_ASR_ENABLED', 'OPENAI_COMPATIBLE_ENABLED', 'LANGCHAIN4J_OPENAI_ENABLED',
                'COURSELINGO_VISION_ANALYSIS_ENABLED'):
        assert env.get(key, 'false') == 'false', f'{key} must be false for no-key smoke test'
    # Hosted CI can take longer than the production default during client initialization.
    env.setdefault('ROCKETMQ_SEND_TIMEOUT_MS', '10000')
    base = f"http://127.0.0.1:{env.get('APP_PORT', '8080')}"
    # Refuse to run assertions against another process accidentally occupying the requested port.
    import socket
    with socket.socket() as sock:
        assert sock.connect_ex(('127.0.0.1', int(env.get('APP_PORT', '8080')))) != 0, 'Backend port already occupied'
    token = ''

    def sql(query):
        command = ['docker', 'compose', '--project-name', args.project, '--env-file', str(args.env_file),
                   'exec', '-T', 'mysql', 'sh', '-c',
                   'MYSQL_PWD="$MYSQL_PASSWORD" mysql --batch --skip-column-names -u"$MYSQL_USER" "$MYSQL_DATABASE" -e "$1"',
                   'mysql-check', query]
        return subprocess.check_output(command, cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()


    def api(method, path, body=None, expected=200, content_type='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        headers = {'Content-Type': content_type}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as error:
            response = error
        payload = json.loads(response.read())
        assert response.status == expected, f'{method} {path}: status={response.status} code={payload.get("code")}'
        if expected == 200:
            assert str(payload['code']) == '0', f'{path}: {payload.get("code")}'
        return payload.get('data')

    logs = ROOT / '.demo'
    logs.mkdir(exist_ok=True)
    subprocess.run(['bash', str(ROOT / 'scripts/demo/generate-sample-video.sh')], check=True, stdout=subprocess.DEVNULL)
    video = (logs / 'lecturelens-sample.mp4').read_bytes()
    jar = ROOT / 'backend/target/courselingo-backend-0.0.1-SNAPSHOT.jar'
    with (logs / 'mock-e2e-backend.log').open('w') as log:
        # Broker registration does not guarantee that the client's gRPC route is ready.
        # Reuse the packaged SDK and dependencies so this probes the actual client protocol.
        with tempfile.TemporaryDirectory(prefix='lecturelens-mq-readiness-') as directory:
            with zipfile.ZipFile(jar) as archive:
                for entry in archive.infolist():
                    if entry.filename.startswith('BOOT-INF/lib/') and entry.filename.endswith('.jar'):
                        (Path(directory) / Path(entry.filename).name).write_bytes(archive.read(entry))
            subprocess.run(['java', '--class-path', str(Path(directory) / '*'),
                            str(ROOT / 'scripts/ci/RocketMqReadiness.java'),
                            env.get('ROCKETMQ_ENDPOINT', '127.0.0.1:18081'),
                            env.get('ROCKETMQ_ANALYSIS_TOPIC', 'courselingo-analysis-task'),
                            env.get('ROCKETMQ_SSL_ENABLED', 'false'), env['ROCKETMQ_SEND_TIMEOUT_MS']],
                           env=env, stdout=log, stderr=log, check=True, timeout=120)
        print('PASS RocketMQ-client-readiness', flush=True)
        process = subprocess.Popen(['java', '-jar', str(jar)], cwd=ROOT / 'backend', env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 150
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Backend exited; inspect .demo/mock-e2e-backend.log')
                try:
                    with urllib.request.urlopen(base + '/actuator/health', timeout=2) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    pass
                assert time.monotonic() < deadline, 'Backend startup timeout; inspect .demo/mock-e2e-backend.log'
                time.sleep(1)
            assert sql('SELECT COUNT(*) FROM flyway_schema_history WHERE success=0') == '0'
            print('PASS backend-started-with-Flyway', flush=True)
            credentials = {'email': f'cleanup-{secrets.token_hex(8)}@example.com', 'password': secrets.token_hex(16) + 'A1'}
            api('POST', '/api/auth/register', credentials)
            token = api('POST', '/api/auth/login', credentials)['accessToken']
            upload = api('POST', '/api/uploads/sessions', {
                'filename': 'cleanup-smoke.mp4', 'sizeBytes': len(video), 'chunkSizeBytes': len(video),
                'totalChunks': 1, 'fileMd5': hashlib.md5(video).hexdigest()})['uploadId']
            boundary = 'cleanup-' + secrets.token_hex(16)
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="chunk.bin"\r\n'
                    'Content-Type: application/octet-stream\r\n\r\n').encode() + video + f'\r\n--{boundary}--\r\n'.encode()
            api('POST', f'/api/uploads/sessions/{upload}/chunks/0', body, content_type=f'multipart/form-data; boundary={boundary}')
            api('POST', f'/api/uploads/sessions/{upload}/complete')
            task = api('POST', '/api/tasks', {'uploadId': upload, 'sourceLanguage': 'en', 'targetLanguage': 'zh-CN'})['taskId']
            deadline = time.monotonic() + 180
            while True:
                state = api('GET', f'/api/tasks/{task}')
                assert state['status'] not in ('FAILED', 'CANCELED'), f'Pipeline failed: {state.get("errorCode")} {state.get("errorMessage")}'
                if state['status'] == 'SUCCEEDED':
                    break
                assert time.monotonic() < deadline, f'Pipeline timeout: {state["status"]}'
                time.sleep(1)
            assert re.fullmatch(r'task_[a-f0-9]{32}', task)
            deadline = time.monotonic() + 10
            while sql(f"SELECT COUNT(*) FROM task_execution WHERE task_id='{task}' AND completed_at IS NOT NULL") != '1':
                assert time.monotonic() < deadline, 'Worker did not close its completed execution lease'
                time.sleep(0.2)
            assert sql(f"SELECT source_language FROM analysis_task WHERE id='{task}'") == 'en'
            result = api('GET', f'/api/tasks/{task}/results')
            assert result['subtitles'] and result['translations'] and result['learningPackage'] and result['artifacts']
            print('PASS upload-MQ-FFmpeg-mock-ASR-translation-learning-artifacts', flush=True)
            api('POST', f'/api/tasks/{task}/chapters/generate')
            snapshot = api('GET', f'/api/tasks/{task}/evidence?limit=1')
            assert snapshot['items'] and snapshot['nextCursor']
            page2 = api('GET', f'/api/tasks/{task}/evidence?revision={snapshot["revision"]}&after={snapshot["nextCursor"]}&limit=100')
            assert page2['items'] and page2['revision'] == snapshot['revision']
            canonical = {item['evidenceId']: item for item in snapshot['items'] + page2['items']}
            qa = api('POST', f'/api/tasks/{task}/qa', {'question': '这节课程主要讲了什么？'})
            assert qa['answer'] and qa['evidence'], 'Mock QA must return grounded citations'
            for item in qa['evidence']:
                source = canonical[item['evidenceId']]
                assert item['revision'] == snapshot['revision']
                assert source['normalizedText'].startswith(item['snippet'])
            api('GET', f'/api/tasks/{task}/evidence?revision={snapshot["revision"]}')
            print('PASS canonical-evidence-pagination-QA-citation-provenance', flush=True)
            first_token = token
            stranger = {'email': f'cleanup-{secrets.token_hex(8)}@example.com', 'password': secrets.token_hex(16) + 'A1'}
            api('POST', '/api/auth/register', stranger)
            token = api('POST', '/api/auth/login', stranger)['accessToken']
            api('GET', f'/api/tasks/{task}/evidence', expected=404)
            assert api('GET', '/api/evidence/changes') == []
            token = first_token
            deleted = api('POST', '/api/tasks/batch-delete', {'taskIds': [task]})
            assert deleted['deletedCount'] == 1
            api('GET', f'/api/tasks/{task}/evidence?revision={snapshot["revision"]}', expected=404)
            changes = api('GET', '/api/evidence/changes')
            assert any(event['task_id'] == task and event['change_type'] == 'DELETE' for event in changes)
            again = api('POST', '/api/tasks/batch-delete', {'taskIds': [task]})
            assert again['deletedCount'] == 0
            deadline = time.monotonic() + 30
            while sql(f"SELECT COUNT(*) FROM task_outbox WHERE task_id='{task}' AND status<>'SENT'") != '0':
                assert time.monotonic() < deadline, 'Durable cleanup did not complete'
                time.sleep(1)
            for table in ('course_evidence', 'course_evidence_snapshot', 'video_keyframe'):
                assert sql(f"SELECT COUNT(*) FROM {table} WHERE task_id='{task}'") == '0', f'{table} cleanup failed'
            print('PASS ownership-isolation-delete-tombstone-idempotent-delete-durable-cleanup', flush=True)
            print('PASS C0-C3 mock infrastructure E2E (OCR/VLM quality and real model behavior are not exercised)', flush=True)
        finally:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
