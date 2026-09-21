#!/usr/bin/env python3
"""Local, opt-in Study Agent acceptance. Uses the configured provider; never starts a paid service.

Prepare with a real captioned course, run the agent, inspect the browser, then delete this harness's course.
Private credentials and full course-derived artifacts stay in the ignored output directory.
"""
import argparse
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['prepare', 'run', 'delete'], required=True)
    parser.add_argument('--video', type=Path, default=Path('.data/l1-acceptance/course-captioned.mp4'))
    parser.add_argument('--output', type=Path, default=Path('.data/l2-acceptance'))
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    private_path = args.output / 'session.local.json'
    state = json.loads(private_path.read_text()) if private_path.exists() else {}
    token = state.get('token', '')
    base = args.base_url.rstrip('/')
    if state.get('base_url', base) != base:
        raise ValueError('Existing course belongs to a different API endpoint')
    state['base_url'] = base

    def save():
        private_path.write_text(json.dumps(state))
        private_path.chmod(0o600)

    def api(method, path, body=None, expected=200, content_type='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(base + path, data=data, method=method, headers={
            'Content-Type': content_type, **({'Authorization': 'Bearer ' + token} if token else {})})
        try:
            response = urllib.request.urlopen(request, timeout=240)
        except urllib.error.HTTPError as error:
            response = error
        result = json.loads(response.read())
        assert response.status == expected, f'{path}: {response.status} {result.get("code")}'
        return result.get('data')

    if args.phase == 'prepare':
        if 'task_id' not in state:
            credentials = {'email': f'l2-{secrets.token_hex(6)}@example.com', 'password': secrets.token_hex(16) + 'A1'}
            api('POST', '/api/auth/register', credentials)
            token = api('POST', '/api/auth/login', credentials)['accessToken']
            state.update(token=token, credentials=credentials)
            save()
            video = args.video.read_bytes()
            size = 4 * 1024 * 1024
            count = (len(video) + size - 1) // size
            upload = api('POST', '/api/uploads/sessions', {'filename': args.video.name, 'sizeBytes': len(video),
                'chunkSizeBytes': size, 'totalChunks': count, 'fileMd5': hashlib.md5(video).hexdigest()})['uploadId']
            for i in range(count):
                boundary = 'study-' + secrets.token_hex(8)
                body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="chunk.bin"\r\n'
                    'Content-Type: application/octet-stream\r\n\r\n').encode() + video[i*size:(i+1)*size] + f'\r\n--{boundary}--\r\n'.encode()
                api('POST', f'/api/uploads/sessions/{upload}/chunks/{i}', body, content_type=f'multipart/form-data; boundary={boundary}')
            api('POST', f'/api/uploads/sessions/{upload}/complete')
            state['task_id'] = api('POST', '/api/tasks', {'uploadId': upload, 'sourceLanguage': 'en', 'targetLanguage': 'zh-CN'})['taskId']
            state['video_sha256'] = hashlib.sha256(video).hexdigest()
            save()
        task = state['task_id']
        deadline = time.monotonic() + 900
        previous = None
        while time.monotonic() < deadline:
            detail = api('GET', f'/api/tasks/{task}')
            assert detail['status'] not in ['FAILED', 'CANCELED'], detail.get('errorCode')
            if detail['status'] != previous:
                print('Pipeline', detail['status'], flush=True)
                previous = detail['status']
            if detail['status'] == 'SUCCEEDED':
                index = api('GET', f'/api/tasks/{task}/evidence/index-status')
                if index['status'] == 'READY':
                    state['index'] = index
                    save()
                    print('PASS real course indexed before any question or Evidence read', flush=True)
                    return
            time.sleep(2)
        raise TimeoutError('Course/index preparation exceeded 15 minutes')

    task = state['task_id']
    if args.phase == 'delete':
        assert api('POST', '/api/tasks/batch-delete', {'taskIds': [task]})['deletedCount'] == 1
        api('POST', f'/api/tasks/{task}/study/command', {'operation': 'READ', 'session_id': state['session_id'], 'run_id': state['run_id']}, expected=404)
        api('GET', f'/api/tasks/{task}/evidence/index-status', expected=404)
        print('PASS deleted course immediately denies Study/Evidence reads', flush=True)
        return

    endpoint = f'/api/tasks/{task}/study/command'
    session = api('POST', endpoint, {'operation': 'CREATE_SESSION', 'request_key': secrets.token_hex(12)})['session_id']
    command = {'operation': 'START', 'session_id': session, 'request_key': secrets.token_hex(12),
               'goal': '请解释课程里算法为什么需要停止条件，结合证据给我两道自测题。'}
    run = api('POST', endpoint, command)['run']
    assert api('POST', endpoint, command)['run']['run_id'] == run['run_id']
    state.update(session_id=session, run_id=run['run_id'])
    save()
    cursor = 0
    events = []
    started = time.monotonic()
    while time.monotonic() - started < 360:
        request = urllib.request.Request(base + f'/api/tasks/{task}/study/runs/{run["run_id"]}/events?sessionId={session}&after={cursor}', headers={'Authorization': 'Bearer ' + token, 'Accept': 'text/event-stream'})
        with urllib.request.urlopen(request, timeout=40) as stream:
            for line in stream:
                if line.startswith(b'data:'):
                    event = json.loads(line[5:])
                    assert event['sequence'] > cursor
                    cursor = event['sequence']; events.append(event)
                    print('Event', event['event_type'], event['payload'].get('tool', event['payload'].get('status', '')), flush=True)
        result = api('POST', endpoint, {'operation': 'READ', 'session_id': session, 'run_id': run['run_id']})
        if result['run']['status'] not in ['queued', 'running']:
            break
    report = {'run': result['run'], 'artifact': result.get('artifact'), 'events': events, 'elapsed_seconds': round(time.monotonic() - started, 2), 'review': 'source_provenance_checked; not a gold quality evaluation'}
    (args.output / 'study-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    assert result['run']['status'] == 'succeeded', result['run']['error_code']
    artifact = result['artifact']
    assert len(artifact['questions']) == 2 and all('answer' not in q for q in artifact['questions'])
    source = api('GET', f'/api/tasks/{task}/evidence?limit=200')
    canonical = {item['evidenceId']: item for item in source['items']}
    for citation in artifact['citations']:
        item = canonical[citation['evidence_id']]
        assert item['normalizedText'].startswith(citation['text'])
        assert item['startMs'] == citation['start_ms'] and item['endMs'] == citation['end_ms']
    assert api('POST', endpoint, {'operation': 'ANSWERS', 'session_id': session, 'run_id': run['run_id']})['questions'][0]['answer']
    tail = api('POST', endpoint, {'operation': 'EVENTS', 'session_id': session, 'run_id': run['run_id'], 'after': cursor})
    assert tail['events'] == []
    print('PASS model-selected tools, explanation + two questions, citations, hidden answers, idempotency and event replay', flush=True)


if __name__ == '__main__':
    main()
