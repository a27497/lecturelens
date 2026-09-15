#!/usr/bin/env python3
"""Browser acceptance against this run's locally created course; no mock HTTP responses.

Run after accept-course-qa.py with: uv run --no-project --with playwright python ...
The retrieval process to stop must be this run's tracked uvicorn process group.
"""
import json
import os
import signal
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '.data/l1-acceptance'


def main():
    report = json.loads((OUT / 'course-qa-report.json').read_text())
    auth = json.loads((OUT / 'session.local.json').read_text())
    task = report['task_id']
    summary = {}
    with sync_playwright() as p:
        installed = sorted((Path.home() / '.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))
        browser = p.chromium.launch(executable_path=str(installed[-1]) if installed else None,
                                    headless=True, args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1100})
        context.add_init_script('''localStorage.setItem('courselingo.accessToken', %s);
            localStorage.setItem('courselingo.refreshToken', %s);
            localStorage.setItem('courselingo.userEmail', %s);''' % (
            json.dumps(auth['session']['accessToken']), json.dumps(auth['session']['refreshToken']),
            json.dumps(auth['credentials']['email'])))
        page = context.new_page()
        page.goto(f'http://127.0.0.1:5173/tasks/{task}')
        page.get_by_role('button', name='课程问答', exact=True).click()
        field = page.get_by_placeholder('输入与当前课程有关的问题')
        field.fill('为什么一个程序需要停止条件？')
        with page.expect_response(lambda r: r.url.endswith(f'/api/tasks/{task}/qa'), timeout=210000) as response:
            page.get_by_role('button', name='提问', exact=True).click()
        result = response.value.json()['data']
        assert response.value.status == 200 and result['evidence']
        expect(page.locator('.qa-answer')).to_be_visible()
        assert result['answer'] in page.locator('.qa-answer').inner_text()
        page.get_by_role('button', name='跳到视频', exact=True).first.click()
        page.wait_for_function('(t) => {const v=document.querySelector("video");return v && Math.abs(v.currentTime-t)<2}',
                               arg=result['evidence'][0]['startTimeMillis'] / 1000, timeout=15000)
        summary['answer_rendered'] = True
        summary['video_seek_seconds'] = page.locator('video').evaluate('(v) => v.currentTime')
        page.screenshot(path=str(OUT / 'qa-and-citation.png'), full_page=True)

        # Stop only the Python service created by this acceptance run, leaving Java and LLM available.
        pid = json.loads((OUT / 'processes.json').read_text())['retrieval']
        command = Path(f'/proc/{pid}/cmdline').read_bytes()
        assert b'uvicorn' in command and b'lecturelens_agent.app:app' in command
        os.killpg(pid, signal.SIGTERM)
        import time
        import urllib.error
        import urllib.request
        for _ in range(30):
            try:
                urllib.request.urlopen('http://127.0.0.1:8090/healthz', timeout=1).close()
            except (OSError, urllib.error.URLError):
                break
            time.sleep(0.2)
        else:
            raise AssertionError('Retrieval did not stop')
        field.fill('老师讲的算法是什么？')
        with page.expect_response(lambda r: r.url.endswith(f'/api/tasks/{task}/qa'), timeout=20000) as failure:
            page.get_by_role('button', name='提问', exact=True).click()
        assert failure.value.status == 503
        assert failure.value.json()['code'] == 'RETRIEVAL_UNAVAILABLE'
        expect(page.get_by_text('课程检索暂不可用，请稍后重试', exact=True)).to_be_visible()
        expect(page.locator('.qa-answer')).to_have_count(0)
        summary['real_retrieval_outage_503'] = True
        summary['old_answer_cleared'] = True
        page.screenshot(path=str(OUT / 'retrieval-outage.png'), full_page=True)
        (OUT / 'browser-report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
        browser.close()
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
