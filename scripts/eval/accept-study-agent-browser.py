#!/usr/bin/env python3
"""Real browser smoke test after the local Study Agent run succeeds. No mocked HTTP."""
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '.data/l2-acceptance'


def main():
    auth = json.loads((OUT / 'session.local.json').read_text())
    report = json.loads((OUT / 'study-report.json').read_text())
    assert report['run']['status'] == 'succeeded'
    with sync_playwright() as p:
        installed = sorted((Path.home() / '.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))
        browser = p.chromium.launch(executable_path=str(installed[-1]) if installed else None, headless=True, args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1100})
        context.add_init_script("localStorage.setItem('courselingo.accessToken', %s); localStorage.setItem('courselingo.userEmail', %s);" % (json.dumps(auth['token']), json.dumps(auth['credentials']['email'])))
        page = context.new_page()
        page.goto('http://127.0.0.1:5173/tasks/' + auth['task_id'])
        page.get_by_role('button', name='学习助手', exact=True).click()
        expect(page.locator('.study-artifact')).to_be_visible(timeout=30000)
        expect(page.locator('.practice-question')).to_have_count(2)
        expect(page.locator('.answer')).to_have_count(0)
        assert report['artifact']['explanation'] in page.locator('.explanation').inner_text()
        page.get_by_text('查看课程证据', exact=True).click()
        citation_index = next(i for i, item in enumerate(report['artifact']['citations']) if item['start_ms'] > 0)
        expected = report['artifact']['citations'][citation_index]['start_ms'] / 1000
        page.locator('.citation button').nth(citation_index).click()
        page.wait_for_function('(t) => {const v=document.querySelector("video"); return v && Math.abs(v.currentTime-t)<2}', arg=expected, timeout=15000)
        page.screenshot(path=str(OUT / 'study-artifact.png'), full_page=True)
        # Remount through a page reload; restore the same session/run/artifact from the API.
        page.reload()
        page.get_by_role('button', name='学习助手', exact=True).click()
        expect(page.locator('.study-artifact')).to_be_visible(timeout=30000)
        expect(page.locator('.answer')).to_have_count(0)
        page.get_by_role('button', name='查看参考答案与自查要点', exact=True).click()
        expect(page.locator('.answer')).to_have_count(2, timeout=15000)
        page.set_viewport_size({'width': 390, 'height': 844})
        page.screenshot(path=str(OUT / 'study-mobile.png'), full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
        browser.close()
    summary = {'restored_after_reload': True, 'two_questions': True, 'answers_hidden_until_requested': True,
               'canonical_video_seek_seconds': expected, 'mobile_no_horizontal_overflow': True}
    (OUT / 'browser-report.json').write_text(json.dumps(summary, indent=2))
    print('PASS real Study UI, restored session, private answers, citation seek and mobile layout')


if __name__ == '__main__':
    main()
