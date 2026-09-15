#!/usr/bin/env python3
"""Small real-course HTTP acceptance run. Requires an already-running local stack.

Only use with an explicitly configured local/authorized model. Writes credentials to
an ignored private output directory, never to the checked-in report. This is not ASR eval.
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
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('.data/l1-acceptance'))
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    parser.add_argument('--reuse-task', help="Reuse this run's existing task and private local session")
    args = parser.parse_args()
    if args.base_url not in ('http://127.0.0.1:8080', 'http://localhost:8080'):
        parser.error('This pilot harness only targets the local development backend')
    args.output.mkdir(parents=True, exist_ok=True)
    token = ''

    def api(method, path, body=None, content_type='application/json', expected=200):
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        headers = {'Content-Type': content_type}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(args.base_url + path, data=data, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=240)
        except urllib.error.HTTPError as error:
            response = error
        result = json.loads(response.read())
        if response.status != expected:
            raise RuntimeError(f'{method} {path}: {response.status} {result.get("code")}')
        return result.get('data') if expected == 200 else result

    if args.reuse_task:
        saved = json.loads((args.output / 'session.local.json').read_text())
        token = saved['session']['accessToken']
        task = args.reuse_task
        video = args.video.read_bytes()
        api('GET', f'/api/tasks/{task}')
    else:
        credentials = {'email': f'l1-course-{secrets.token_hex(6)}@example.com',
                       'password': secrets.token_hex(16) + 'A1'}
        api('POST', '/api/auth/register', credentials)
        session = api('POST', '/api/auth/login', credentials)
        token = session['accessToken']
        private = args.output / 'session.local.json'
        private.write_text(json.dumps({'credentials': credentials, 'session': session}))
        private.chmod(0o600)
        video = args.video.read_bytes()
        chunk_size = 4 * 1024 * 1024
        count = (len(video) + chunk_size - 1) // chunk_size
        upload = api('POST', '/api/uploads/sessions', {'filename': args.video.name, 'sizeBytes': len(video),
                     'chunkSizeBytes': chunk_size, 'totalChunks': count,
                     'fileMd5': hashlib.md5(video).hexdigest()})['uploadId']
        for index in range(count):
            chunk = video[index * chunk_size:(index + 1) * chunk_size]
            boundary = 'l1-' + secrets.token_hex(12)
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="chunk.bin"\r\n'
                    'Content-Type: application/octet-stream\r\n\r\n').encode() + chunk + f'\r\n--{boundary}--\r\n'.encode()
            api('POST', f'/api/uploads/sessions/{upload}/chunks/{index}', body,
                content_type=f'multipart/form-data; boundary={boundary}')
        api('POST', f'/api/uploads/sessions/{upload}/complete')
        task = api('POST', '/api/tasks', {'uploadId': upload, 'sourceLanguage': 'en', 'targetLanguage': 'zh-CN'})['taskId']
    report = {'task_id': task, 'input_sha256': hashlib.sha256(video).hexdigest(),
              'transcript_mode': 'official_subtitles_embedded_in_real_video',
              'review_status': 'requires_source_review_not_a_gold_eval', 'questions': []}
    report_path = args.output / 'course-qa-report.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Created course task', task, flush=True)
    deadline, last = time.monotonic() + 900, None
    while True:
        state = api('GET', f'/api/tasks/{task}')
        if state['status'] != last:
            print('Pipeline', state['status'], flush=True)
            last = state['status']
        if state['status'] in ('FAILED', 'CANCELED'):
            raise RuntimeError(f'Pipeline failed: {state.get("errorCode")} {state.get("errorMessage")}')
        if state['status'] == 'SUCCEEDED':
            break
        if time.monotonic() > deadline:
            raise TimeoutError('Pipeline did not complete in 15 minutes')
        time.sleep(2)
    evidence, after = {}, ''
    while True:
        page = api('GET', f'/api/tasks/{task}/evidence?limit=200&after={after}')
        evidence.update({item['evidenceId']: item for item in page['items']})
        after = page['nextCursor']
        if not after:
            break
    assert evidence and not any('Welcome to the LectureLens local demo' in e['rawText'] for e in evidence.values())
    (args.output / 'canonical-evidence.json').write_text(json.dumps(list(evidence.values()), ensure_ascii=False, indent=2))
    cases = [
        ('fact', '老师把一个算法比作食谱时，指出它应包含哪三个组成部分？'),
        ('cross_language', '为什么一个程序需要停止条件？'),
        ('paraphrase', '只能完成固定用途的计算机，和可以装入不同程序的计算机有什么区别？'),
        ('time', '01:10 附近老师讲到了食谱的哪些要素？'),
        ('unanswerable', '这节课中，老师给出的 Kubernetes 生产集群节点数量是多少？'),
    ]
    for category, question in cases:
        started = time.monotonic()
        answer = api('POST', f'/api/tasks/{task}/qa', {'question': question})
        for item in answer['evidence']:
            source = evidence[item['evidenceId']]
            assert item['revision'] == source['revision']
            assert item['startTimeMillis'] == source['startMs'] and item['endTimeMillis'] == source['endMs']
            assert source['normalizedText'].startswith(item['snippet'])
        report['questions'].append({'category': category, 'question': question,
                                    'elapsed_ms': round((time.monotonic() - started) * 1000), 'response': answer})
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(category, answer['answer'], 'citations', len(answer['evidence']), flush=True)
    print('PASS HTTP workflow and citation provenance. Semantic/source review is still required.', flush=True)


if __name__ == '__main__':
    main()
