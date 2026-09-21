#!/usr/bin/env python3
"""Destructive only to the disposable task created by accept-course-qa.py.

Run after browser acceptance; verifies cross-user access and deletion with a warm vector projection.
"""
import json
import re
import secrets
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '.data/l1-acceptance'
BASE = 'http://127.0.0.1:8080'


def main():
    auth = json.loads((OUT / 'session.local.json').read_text())
    report = json.loads((OUT / 'course-qa-report.json').read_text())
    task = report['task_id']
    assert re.fullmatch(r'task_[a-f0-9]{32}', task)
    owner = auth['session']['accessToken']

    def api(method, path, body=None, token=None, expected=200):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers=headers, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        payload = json.loads(response.read())
        assert response.status == expected, (response.status, payload.get('code'))
        return payload.get('data')

    credentials = {'email': f'l1-stranger-{secrets.token_hex(6)}@example.com',
                   'password': secrets.token_hex(16) + 'A1'}
    api('POST', '/api/auth/register', credentials)
    stranger = api('POST', '/api/auth/login', credentials)['accessToken']
    api('GET', f'/api/tasks/{task}/evidence', token=stranger, expected=404)
    api('POST', f'/api/tasks/{task}/qa', {'question': '课程有哪些内容？'}, stranger, expected=404)
    assert api('GET', '/api/evidence/changes', token=stranger) == []
    deletion = api('POST', '/api/tasks/batch-delete', {'taskIds': [task]}, owner)
    assert deletion['deletedCount'] == 1
    api('GET', f'/api/tasks/{task}/evidence', token=owner, expected=404)
    api('POST', f'/api/tasks/{task}/qa', {'question': '为什么程序需要停止条件？'}, owner, expected=404)
    again = api('POST', '/api/tasks/batch-delete', {'taskIds': [task]}, owner)
    assert again['deletedCount'] == 0
    summary = {'cross_user_evidence_404': True, 'cross_user_qa_404': True, 'cross_user_changes_empty': True,
               'deleted_task_evidence_404': True, 'deleted_task_qa_404': True, 'idempotent_delete': True}
    (OUT / 'lifecycle-report.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
