// Real Chromium + decoded local media; all business/Agent responses below are fixtures.
import { chromium, expect } from '@playwright/test';
import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { readFile, stat, mkdir } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
import { parseArgs } from 'node:util';

const { values: args } = parseArgs({ options: {
  dist: { type: 'string' }, media: { type: 'string' }, long: { type: 'string' },
  only: { type: 'string' }, chromium: { type: 'string' }, output: { type: 'string' }, baseline: { type: 'boolean' },
} });
if (!args.dist || !args.media || !args.long || !args.output) throw Error('Require --dist, --media, --long, --output (see docs/COURSE_POSITION.md)');
const dist = resolve(args.dist), output = resolve(args.output);
await mkdir(output, { recursive: true });
const errors = [], forbidden = [], commands = [];
const citation = { evidence_id: 'course:fixture:subtitle:7:r1', text: 'Second original passage', start_ms: 2000, end_ms: 3000, source_type: 'SUBTITLE' };
const attempt = { attempt_id: 'answer-1', artifact_id: 'artifact', question_index: 0, version: 1, answer_text: 'Saved answer', created_at: '2026-10-01T00:00:00Z' };
const feedback = { feedback_id: 'feedback', attempt_id: 'answer-1', answer_version: 1, question_index: 0, answer_text: attempt.answer_text, note: null,
  content: { kind: 'guidance', mode: 'mock', citations: [citation], observations: [{ learner_quote: attempt.answer_text, observation: 'Check the stopping condition.', next_step: 'Read the original passage.', evidence_id: citation.evidence_id, evidence_quote: citation.text }] } };
const feedbackRun = { run_id: 'feedback-run', status: 'succeeded', attempt_id: attempt.attempt_id, question_index: 0, answer_version: 1, feedback };
const learning = { run: { run_id: 'run', session_id: 'session', goal: 'Restored learning question', status: 'succeeded', model_mode: 'mock', model_calls: 0, tool_calls: 0, error_code: null },
  artifact: { artifact_id: 'artifact', title: 'Fixture practice', explanation: 'A saved explanation.', evidence_ids: [citation.evidence_id], questions: [{ question: 'When does the loop stop?', evidence_ids: [citation.evidence_id] }], citations: [citation], revision: 1, mode: 'mock' },
  attempts: [attempt], feedback_enabled: true, feedback_runs: [feedbackRun] };
function task(id) { return { taskId: id, status: 'SUCCEEDED', progressPercent: 100, currentStage: 'DONE', targetLanguage: 'zh-CN', startedAt: '2026-10-01T00:00:00Z', finishedAt: '2026-10-01T00:00:12Z' }; }
function result(id) {
  const subtitles = id === 'empty' ? [] : id === 'long' ? Array.from({ length: 10000 }, (_, i) => ({ segmentIndex: i, startMillis: i * 350, endMillis: (i + 1) * 350, language: 'en', sourceText: `Long original passage ${i}` })) : [
    { segmentIndex: 1, startMillis: 0, endMillis: 1200, language: 'en', sourceText: 'First original passage' },
    { segmentIndex: 7, startMillis: 2000, endMillis: 3000, language: 'en', sourceText: citation.text },
    { segmentIndex: 8, startMillis: 2500, endMillis: 2800, language: 'en', sourceText: 'Nested original passage' },
    { segmentIndex: 9, startMillis: 5000, endMillis: 10000, language: 'en', sourceText: 'Final original passage' },
    { segmentIndex: 10, startMillis: 11000, endMillis: 11000, language: 'en', sourceText: 'Empty interval' },
  ];
  return { taskId: id, sourceFullText: 'Whole original text', sourceParagraphs: [], translatedFullText: 'Full translation without segment alignment', translationStatus: 'SUCCEEDED', translationErrorSummary: null,
    subtitles, translations: [], learningPackage: null, keyframes: [], videoSegments: [], artifacts: [], aiCallRecords: [] };
}
const envelope = data => JSON.stringify({ code: '0', message: 'ok', data });
let tokenDelay = 0, corrupt = false;
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://127.0.0.1');
    const path = url.pathname;
    const id = path.split('/')[3];
    if (path.startsWith('/api/')) {
      let data;
      if (path.endsWith('/events')) { res.writeHead(200, { 'Content-Type': 'text/event-stream' }); res.end(`event: snapshot\ndata: ${JSON.stringify(task(id))}\n\n`); return; }
      if (path.endsWith('/playback-token')) {
        if (tokenDelay) await new Promise(r => setTimeout(r, tokenDelay));
        data = { playbackUrl: corrupt ? '/broken.mp4' : id === 'long' ? '/long.mp4' : '/short.mp4', expiresAt: '2099-01-01T00:00:00Z' };
      } else if (path.endsWith('/embedded-subtitles')) data = { status: 'NOT_FOUND', selectedStreamIndex: null, tracks: [] };
      else if (path.endsWith('/results')) data = result(id);
      else if (path.endsWith('/study/status')) data = { enabled: id !== 'empty', revision: 1 };
      else if (path.endsWith('/evidence/index-status')) data = { status: 'READY' };
      else if (path.endsWith('/study/command')) {
        let body = ''; for await (const chunk of req) body += chunk;
        const command = JSON.parse(body); commands.push(command.operation);
        if (command.operation === 'LIST') data = { sessions: id === 'empty' ? [] : [{ session_id: 'session', revision: 1 }] };
        else if (command.operation === 'READ') data = learning;
        else if (command.operation === 'RUNS') data = { runs: [learning.run] };
        else { forbidden.push(command.operation); res.writeHead(500); res.end(); return; }
      } else if (path.endsWith('/qa')) data = { answer: 'Fixture Tutor answer', evidence: [{ sourceType: 'SUBTITLE', sourceId: '7', evidenceId: citation.evidence_id, revision: 1, startTimeMillis: 2000, endTimeMillis: 3000, timeText: '00:00:02 - 00:00:03', snippet: citation.text, translatedSnippet: '', confidence: 1 }], usage: null };
      else if (path === '/api/public/runtime-configuration') data = { demoMode: false };
      else if (path === '/api/auth/me') data = { id: 1, email: 'fixture@example.invalid', role: 'USER' };
      else if (/^\/api\/tasks\/[^/]+$/.test(path)) data = task(id);
      else { errors.push(`Unhandled fixture ${path}`); res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(envelope(data)); return;
    }
    if (path === '/broken.mp4') { res.writeHead(200, { 'Content-Type': 'video/mp4' }); res.end('invalid media'); return; }
    const media = path === '/short.mp4' ? args.media : path === '/long.mp4' ? args.long : null;
    if (media) {
      const size = (await stat(media)).size;
      const range = /bytes=(\d+)-(\d*)/.exec(req.headers.range || '');
      const start = range ? Number(range[1]) : 0, end = range?.[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
      res.writeHead(range ? 206 : 200, { 'Content-Type': 'video/mp4', 'Accept-Ranges': 'bytes', 'Content-Length': end - start + 1, ...(range ? { 'Content-Range': `bytes ${start}-${end}/${size}` } : {}) });
      createReadStream(media, { start, end }).pipe(res); return;
    }
    const file = path.startsWith('/assets/') ? resolve(dist, '.' + path) : resolve(dist, 'index.html');
    if (!file.startsWith(dist + '/')) { res.writeHead(403); res.end(); return; }
    const content = await readFile(file);
    res.writeHead(200, { 'Content-Type': ({ '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html' })[extname(file)] || 'application/octet-stream' }); res.end(content);
  } catch (error) { errors.push(String(error)); res.writeHead(500); res.end(); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ headless: true, executablePath: args.chromium, args: ['--no-sandbox'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
await page.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
page.on('pageerror', error => errors.push(String(error)));
await page.addInitScript(() => localStorage.setItem('courselingo.accessToken', 'isolated-fixture-token'));
const video = page.locator('video');
const current = page.locator('.timeline-row[aria-current=true]');
const nav = label => page.getByRole('navigation', { name: '课程内容导航' }).getByRole('button', { name: label, exact: true });
const checks = [];
async function check(name, run) { if (args.only && !name.includes(args.only)) return; await run(); checks.push(name); console.log(`PASS ${name}`); }
async function seek(seconds) { await video.evaluate((v, t) => { v.currentTime = t; }, seconds); await expect.poll(() => video.evaluate(v => v.seeking)).toBe(false); }
try {
  if (args.baseline) {
    await page.goto(`${origin}/tasks/short?view=content&text=timeline&at=2500`);
    await expect(video).toHaveJSProperty('readyState', 4);
    const initial = { restoredVideoSeconds: await video.evaluate(v => v.currentTime), workspace: await page.locator('.workspace-nav [aria-current=page]').textContent() };
    await nav('课程内容').click(); await page.getByRole('button', { name: '时间轴', exact: true }).click();
    await seek(2.5);
    const currentRowsAfterSeek = await current.count();
    await page.locator('.timeline-row').filter({ hasText: 'Second original passage' }).getByRole('button').click();
    await expect(video).toHaveJSProperty('paused', false);
    await video.evaluate(v => v.pause());
    await nav('学习助手').click();
    await page.locator('.study-artifact > details summary').click(); await page.locator('.citation button').click();
    console.log(JSON.stringify({ baseline: true, ...initial, currentRowsAfterSeek, transcriptVisibleAfterCitation: await page.locator('.timeline-view').count(), citationStartedPlayback: await video.evaluate(v => !v.paused) }));
    await video.evaluate(v => v.pause());
    await page.screenshot({ path: `${output}/baseline.png`, fullPage: true });
  } else {
    await check('delayed metadata restores URL position paused; overlap and gap boundaries', async () => {
      tokenDelay = 450;
      await page.goto(`${origin}/tasks/short?view=content&text=timeline&at=2500`);
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(2.5);
      await expect(video).toHaveJSProperty('paused', true);
      await expect(current).toHaveAttribute('data-segment', '8');
      await seek(2.8); await expect(current).toHaveAttribute('data-segment', '7');
      await seek(1.5); await expect(current).toHaveCount(0);
      tokenDelay = 0;
    });
    await check('real decoded playback advances time and the active original passage', async () => {
      await seek(0); await video.evaluate(v => v.play());
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBeGreaterThan(2);
      await video.evaluate(v => v.pause());
      await expect(current).toHaveAttribute('data-segment', '7');
      expect(await video.evaluate(v => v.getVideoPlaybackQuality().totalVideoFrames)).toBeGreaterThan(0);
    });
    await check('transcript click seeks paused video; keyboard controls and search pause follow', async () => {
      await page.locator('[data-segment="9"]').getByRole('button').click();
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(5);
      await expect(video).toHaveJSProperty('paused', true);
      const list = page.locator('.timeline-list'); await list.focus(); await page.keyboard.press('PageDown');
      await expect(page.locator('.timeline-controls button')).toHaveAttribute('aria-pressed', 'false');
      await page.getByPlaceholder('搜索原文或译文关键词').fill('First');
      await seek(6); await expect(page.locator('.timeline-row')).toHaveCount(1);
      await page.locator('.timeline-controls button').click();
      await expect(page.locator('.timeline-controls button')).toHaveAttribute('aria-pressed', 'true');
      await expect(current).toHaveAttribute('data-segment', '9');
    });
    await check('Tutor citation preserves question, answer and unsubmitted follow-up', async () => {
      await nav('课程问答').click();
      const input = page.getByPlaceholder('输入与当前课程有关的问题');
      await input.fill('A course question'); await page.getByRole('button', { name: '提问', exact: true }).click();
      await expect(page.getByText('Fixture Tutor answer', { exact: true })).toBeVisible();
      await input.fill('Unsubmitted follow-up');
      await page.locator('.evidence-item').getByRole('button', { name: '跳到视频' }).click();
      await expect(current).toHaveAttribute('data-segment', '7');
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(2);
      await expect(input).toHaveValue('Unsubmitted follow-up');
      await expect(page.getByText('Fixture Tutor answer', { exact: true })).toBeVisible();
      await page.getByRole('button', { name: '返回当前学习任务' }).click();
      await expect(input).toHaveValue('Unsubmitted follow-up');
    });
    await check('practice feedback citation preserves goal, saved answer, draft and feedback identity', async () => {
      await nav('学习助手').click();
      await expect(page.getByText('Fixture practice', { exact: true })).toBeVisible();
      const goal = page.locator('.agent-panel textarea').first();
      await goal.fill('Unsubmitted learning goal');
      const answer = page.getByRole('textbox', { name: '第 1 题作答' });
      await expect(answer).toHaveValue('Saved answer'); await answer.fill('Unsaved answer revision');
      await page.getByText('核对或更正反馈', { exact: true }).click();
      const note = page.getByRole('textbox', { name: '反馈核对意见' });
      await note.fill('Unsaved feedback note');
      const beforeCommands = commands.length;
      await page.locator('.study-artifact > details summary').click();
      await page.locator('.citation button').click();
      await expect(goal).toHaveValue('Unsubmitted learning goal');
      await expect(answer).toHaveValue('Unsaved answer revision');
      await page.getByRole('button', { name: '返回当前学习任务' }).click();
      await page.getByRole('button', { name: '回看这段课程证据', exact: true }).click();
      await expect(current).toHaveAttribute('data-segment', '7');
      await expect(goal).toHaveValue('Unsubmitted learning goal');
      await expect(answer).toHaveValue('Unsaved answer revision');
      await expect(page.getByText('Check the stopping condition.', { exact: true })).toBeVisible();
      await page.screenshot({ path: `${output}/feedback-evidence.png`, fullPage: true });
      await page.getByRole('button', { name: '返回当前学习任务' }).click();
      await expect(answer).toHaveValue('Unsaved answer revision');
      await expect(note).toHaveValue('Unsaved feedback note');
      expect(commands.length).toBe(beforeCommands);
    });
    await check('view history and refresh restore coordinate; refresh never starts a Run', async () => {
      await nav('课程内容').click(); await page.getByRole('button', { name: '时间轴', exact: true }).click();
      await seek(5.5);
      await expect.poll(() => new URL(page.url()).searchParams.get('at')).toBe('5500');
      await nav('课程问答').click(); await page.goBack();
      await expect(current).toHaveAttribute('data-segment', '9');
      await page.reload();
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(5.5);
      await expect(video).toHaveJSProperty('paused', true);
      expect(page.url()).not.toContain('Unsubmitted');
    });
    await check('token refresh preserves coordinate for paused and playing video', async () => {
      await seek(6);
      await page.getByRole('button', { name: '刷新播放链接' }).click();
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(6);
      await expect(video).toHaveJSProperty('paused', true);
      await video.evaluate(v => v.play());
      await page.getByRole('button', { name: '刷新播放链接' }).click();
      await expect(video).toHaveJSProperty('paused', false);
      await video.evaluate(v => v.pause());
    });
    await check('course switch clears cached drafts; stale delayed media cannot cross courses', async () => {
      // Use the SPA router through native history/popstate to retain the same mounted page.
      tokenDelay = 700;
      await page.evaluate(() => { history.pushState({}, '', '/tasks/other?view=agent'); window.dispatchEvent(new PopStateEvent('popstate')); });
      await expect(page.locator('.agent-panel textarea').first()).toHaveValue('Restored learning question');
      await page.evaluate(() => { history.pushState({}, '', '/tasks/empty?view=content&text=timeline'); window.dispatchEvent(new PopStateEvent('popstate')); });
      await expect(page.getByText('本课程没有可定位的字幕片段', { exact: true })).toBeVisible();
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(0);
      tokenDelay = 0;
    });
    await check('real 65-minute media and 10,000 intervals support manual reading and resumption', async () => {
      await page.goto(`${origin}/tasks/long?view=content&text=timeline&at=3000000`);
      await expect.poll(() => video.evaluate(v => v.duration)).toBe(3900);
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(3000);
      await expect(current).toHaveAttribute('data-segment', '8571');
      const list = page.locator('.timeline-list');
      await list.hover(); await page.mouse.wheel(0, -600);
      await expect(page.locator('.timeline-controls button')).toHaveAttribute('aria-pressed', 'false');
      const before = await list.evaluate(el => el.scrollTop);
      await seek(3200);
      expect(Math.abs(await list.evaluate(el => el.scrollTop) - before)).toBeLessThan(4);
      await page.locator('.timeline-controls button').click();
      await expect(current).toHaveAttribute('data-segment', '9142');
      await expect.poll(() => current.evaluate(el => { const a = el.getBoundingClientRect(), b = el.parentElement.getBoundingClientRect(); return a.top >= b.top && a.top < b.bottom; })).toBe(true);
      await video.evaluate(v => v.play());
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBeGreaterThan(3200.5);
      await video.evaluate(v => v.pause());
      await page.screenshot({ path: `${output}/long-timeline.png` });
    });
    await check('390px layout and codec error retain readable course content', async () => {
      await page.setViewportSize({ width: 390, height: 844 });
      corrupt = true;
      await page.goto(`${origin}/tasks/short?view=content&text=timeline&at=2000`);
      await expect(page.getByText('浏览器不支持该视频编码或格式。', { exact: true })).toBeVisible();
      await expect(current).toHaveAttribute('data-segment', '7');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `${output}/mobile-error.png`, fullPage: true });
      corrupt = false;
      await page.getByRole('button', { name: '刷新播放链接' }).click();
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(2);
      await expect(video).toHaveJSProperty('paused', true);
    });
  }
  expect(forbidden).toEqual([]); expect(errors).toEqual([]);
  console.log(JSON.stringify({ browser: browser.version(), checks, commands, errors, forbidden, media: 'real decoded synthetic H.264; fixture business APIs; no provider calls' }));
} catch (error) {
  await page.screenshot({ path: `${output}/failure.png`, fullPage: true });
  console.error(JSON.stringify({ checks, errors, forbidden, url: page.url() }));
  throw error;
} finally { await browser.close(); await new Promise(r => server.close(r)); }
