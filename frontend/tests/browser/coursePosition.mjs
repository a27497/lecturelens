// Real Chromium + decoded local media; all business/Agent responses below are fixtures.
import { chromium, expect } from '@playwright/test';
import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { readFile, stat, mkdir } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
import { parseArgs } from 'node:util';

const { values: args } = parseArgs({ options: {
  dist: { type: 'string' }, media: { type: 'string' }, long: { type: 'string' },
  only: { type: 'string' }, chromium: { type: 'string' }, output: { type: 'string' }, baseline: { type: 'boolean' }, review: { type: 'boolean' }, models: { type: 'boolean' }, classic: { type: 'boolean' }, continuous: { type: 'boolean' },
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
const modelSelection = (id, version, model, origin = 'CREATED') => ({ snapshotId: id, configVersion: version, origin, recordedAt: '2026-10-01 00:00:00', routes: [{ feature: 'COURSE_QA', source: 'DATABASE', model }] });
let modelDelay = 0, modelDenied = false, modelReads = 0;
if (args.models) learning.run = { ...learning.run, model_mode: 'real', model_calls: 2, created_at: '2026-10-01T00:00:00Z', model_selection: {
  decision: { connection_id: 'personal', name: 'Personal fixture', model: 'decision-frozen-a', version: 3 },
  review: { connection_id: null, name: 'Server default fixture', model: 'review-frozen-b', version: 0 },
} };
let sourceRevision = 1, verificationDelay = 0, verificationFailure = false, verificationReads = 0;
function result(id) {
  const subtitles = id === 'empty' ? [] : id === 'long' ? Array.from({ length: 10000 }, (_, i) => ({ segmentIndex: i, startMillis: i * 350, endMillis: (i + 1) * 350, language: 'en', sourceText: `Long original passage ${i}` })) : [
    { segmentIndex: 1, startMillis: 0, endMillis: 1200, language: 'en', sourceText: 'First original passage' },
    { segmentIndex: 7, startMillis: 2000, endMillis: 3000, language: 'en', sourceText: sourceRevision === 1 ? citation.text : "REVISED unrelated original" },
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
      else if (path.endsWith('/model-usage')) {
        modelReads++;
        if (modelDelay) await new Promise(r => setTimeout(r, modelDelay));
        if (modelDenied) { res.writeHead(404); res.end(envelope(null)); return; }
        data = { taskId: id, current: modelSelection(null, 9, 'current-model-b', 'CURRENT'),
          pipeline: [{ ...modelSelection('pipeline-a', 4, 'pipeline-model-a', 'ADOPTED'), routes: [{ feature: 'ASR_TRANSCRIPTION', source: 'ENV', model: 'pipeline-model-a' }] }],
          qa: [{ recordId: '123', invocationState: 'SKIPPED_NO_EVIDENCE', callRecordId: null, provider: null, model: null, status: 'SUCCEEDED', totalTokens: null, recordedAt: '2026-10-01', selection: modelSelection('qa-a', 5, 'historical-model-a') },
            { recordId: 'legacy', invocationState: null, callRecordId: null, provider: 'legacy-provider', model: 'legacy-model', status: 'SUCCEEDED', totalTokens: null, recordedAt: '2026-09-01', selection: null }],
          calls: [{ recordId: '456', stage: 'SUBTITLE_TRANSLATION', provider: 'fixture', model: 'observed-model-a', status: 'SUCCEEDED', totalTokens: null, startedAt: '2026-10-01' }] };
      }
      else if (path.endsWith('/results')) data = result(id);
      else if (path.endsWith('/evidence')) data = { learningScopeVersion: 1, revision: sourceRevision, stale: false, nextCursor: null,
        items: result(id).subtitles.slice(0, 200).map(row => ({ evidenceId: row.segmentIndex === 7 ? citation.evidence_id : `course:fixture:subtitle:${row.segmentIndex}:r${sourceRevision}`, revision: sourceRevision, sourceType: 'SUBTITLE', startMs: row.startMillis, endMs: row.endMillis, normalizedText: row.sourceText, retrievable: row.endMillis > row.startMillis })) };
      else if (path.endsWith('/study/status')) data = { enabled: id !== 'empty', revision: sourceRevision };
      else if (path.endsWith('/evidence/index-status')) {
        const checkedRevision = sourceRevision; verificationReads++;
        if (verificationDelay) await new Promise(r => setTimeout(r, verificationDelay));
        if (verificationFailure) { res.writeHead(503); res.end(envelope(null)); return; }
        data = { status: 'READY', revision: checkedRevision };
      }
      else if (path.endsWith('/study/command')) {
        let body = ''; for await (const chunk of req) body += chunk;
        const command = JSON.parse(body); commands.push(command.operation);
        if (command.operation === 'LIST') data = { sessions: id === 'empty' ? [] : [{ session_id: 'session', revision: 1 }] };
        else if (command.operation === 'READ') data = learning;
        else if (command.operation === 'EVENTS' && args.models) data = { events: [{ sequence: 1, event_type: 'model_started', payload: { purpose: 'decision', model_selection: { model: 'decision-frozen-a', version: 3 } } }, { sequence: 2, event_type: 'model_replayed', payload: { purpose: 'review', model_selection: { model: 'review-frozen-b', version: 0 } } }] };
        else if (command.operation === 'RUNS') data = { runs: [learning.run] };
        else { forbidden.push(command.operation); res.writeHead(500); res.end(); return; }
      } else if ((path.endsWith('/qa') || path.endsWith('/qa/scoped'))) data = { answer: 'Fixture Tutor answer', evidence: [{ sourceType: 'SUBTITLE', sourceId: '7', evidenceId: sourceRevision === 1 ? citation.evidence_id : 'canonical-r2', revision: sourceRevision, startTimeMillis: 2000, endTimeMillis: 3000, timeText: '00:00:02 - 00:00:03', snippet: sourceRevision === 1 ? citation.text : 'REVISED unrelated original', translatedSnippet: '', confidence: 1 }], usage: null };
      else if (path === '/api/public/runtime-configuration') data = { demoMode: false };
      else if (path === '/api/me') data = { id: 1, email: 'fixture@example.invalid', role: 'USER' };
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
if (args.classic) await page.addInitScript(() => {
  const url = new URL(location.href);
  if (url.pathname.startsWith('/tasks/')) { url.searchParams.set('layout', 'classic'); history.replaceState({}, '', url); }
});
const video = page.locator('video');
const current = page.locator('.timeline-row[aria-current=true]');
const nav = label => page.getByRole('navigation', { name: '课程内容导航' }).getByRole('button', { name: label, exact: true });
const checks = [];
async function check(name, run) { if (args.only && !name.includes(args.only)) return; await run(); checks.push(name); console.log(`PASS ${name}`); }
async function expectReviewCancelled() {
  if (args.continuous) {
    await expect(page.locator('.evidence-reading__return')).toBeHidden();
    await expect(page.locator('.evidence-reading')).toBeVisible();
  } else await expect(page.locator('.evidence-reading')).toBeHidden();
}
async function seek(seconds) { await video.evaluate((v, t) => { v.currentTime = t; }, seconds); await expect.poll(() => video.evaluate(v => v.seeking)).toBe(false); }
try {
  if (args.models) {
    await check('owner card separates current, adopted pipeline, exact QA and unknown usage without probes', async () => {
      await page.goto(`${origin}/tasks/short?view=agent`);
      await expect(page.getByText('Fixture practice', { exact: true })).toBeVisible();
      expect(modelReads).toBe(0);
      const recovery = page.locator('.workspace-recovery');
      if (await recovery.count()) await recovery.evaluate(el => { el.open = true; });
      const card = page.getByRole('region', { name: '课程模型使用记录' });
      await card.getByRole('button', { name: '模型使用记录', exact: true }).click();
      await expect(card.getByText('historical-model-a', { exact: false })).toBeVisible();
      await card.locator('summary').click();
      await expect(card.getByText('current-model-b', { exact: false })).toBeVisible();
      await expect(card.getByText('接管时冻结（非创建时）', { exact: false })).toBeVisible();
      await expect(card.getByText('跳过调用：证据不足', { exact: false })).toBeVisible();
      await expect(card.getByText('冻结配置：未记录', { exact: true })).toBeVisible();
      await expect(card.getByText('多轮工具兼容：未验证', { exact: false })).toBeVisible();
      await card.screenshot({ path: `${output}/model-usage.png` });
    });
    await check('trace displays independent frozen decision/review and replay without usage invention', async () => {
      await page.getByRole('button', { name: 'View Trace · 查看执行链路' }).click();
      const trace = page.getByRole('region', { name: 'Agent Trace' });
      await expect(trace.getByText('decision-frozen-a', { exact: false }).first()).toBeVisible();
      await expect(trace.getByText('review-frozen-b', { exact: false }).first()).toBeVisible();
      await expect(trace.getByText('重放已保存结果，非新调用', { exact: false })).toBeVisible();
      await expect(trace.getByText('输入 Token：未知', { exact: false }).first()).toBeVisible();
      await trace.screenshot({ path: `${output}/agent-model-trace.png` });
    });
    await check('permission denial removes previously visible model facts', async () => {
      modelDenied = true;
      const recovery = page.locator('.workspace-recovery');
      if (await recovery.count()) await recovery.evaluate(el => { el.open = true; });
      const card = page.getByRole('region', { name: '课程模型使用记录' });
      await card.getByRole('button', { name: '刷新模型使用记录' }).click();
      await expect(card.getByRole('alert')).toBeVisible();
      await expect(card.getByText('historical-model-a', { exact: false })).toHaveCount(0);
      modelDenied = false;
    });
    await check('late model record response cannot follow a course switch', async () => {
      modelDelay = 900;
      const reads = modelReads;
      await page.getByRole('button', { name: '刷新模型使用记录', exact: true }).click();
      await expect.poll(() => modelReads).toBe(reads + 1);
      await page.evaluate(() => { history.pushState({}, '', '/tasks/other?view=agent'); window.dispatchEvent(new PopStateEvent('popstate')); });
      await expect(page.getByText('Fixture practice', { exact: true })).toBeVisible();
      await new Promise(r => setTimeout(r, 1100));
      await expect(page.getByText('historical-model-a', { exact: false })).toHaveCount(0);
      modelDelay = 0;
    });
    await check('390px model card stays within viewport', async () => {
      await page.setViewportSize({ width: 390, height: 844 });
      const recovery = page.locator('.workspace-recovery');
      if (await recovery.count()) await recovery.evaluate(el => { el.open = true; });
      const card = page.getByRole('region', { name: '课程模型使用记录' });
      await card.getByRole('button', { name: '模型使用记录', exact: true }).click();
      await expect(card.getByText('historical-model-a', { exact: false })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await card.screenshot({ path: `${output}/model-usage-mobile.png` });
    });
    await check('malformed historical probe and Mock observations remain unverified without renderer errors', async () => {
      await page.setViewportSize({ width: 1440, height: 1000 });
      const valid = { ok: true, code: null, checked_at: 1700000000, version: 3 };
      const historical = [
        { ...valid, checked_at: undefined }, { ...valid, checked_at: null },
        { ...valid, checked_at: 'invalid' }, { ...valid, version: '3' },
        { ...valid, ok: 'false' }, valid,
      ];
      for (let i = 0; i < historical.length; i++) {
        learning.run.model_selection.decision.single_turn_evidence = historical[i];
        learning.run.model_mode = i === historical.length - 1 ? 'mock' : 'real';
        await page.reload();
        await expect(page.getByText('Fixture practice', { exact: true })).toBeVisible();
        await page.getByRole('button', { name: 'View Trace · 查看执行链路' }).click();
        const trace = page.getByRole('region', { name: 'Agent Trace' });
        await expect(trace.getByText('单轮协议：未验证', { exact: false })).toHaveCount(2);
        await expect(trace.getByText('多轮工具兼容：未验证', { exact: false })).toHaveCount(2);
        await expect(trace.getByText('真实课程质量：未验证', { exact: false })).toHaveCount(2);
      }
      await page.getByRole('region', { name: 'Agent Trace' }).screenshot({ path: `${output}/model-evidence-legacy.png` });
    });
  } else if (args.baseline) {
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
  } else if (args.review) {
    await check('native progress drag supersedes pending Evidence navigation', async () => {
      await page.goto(`${origin}/tasks/short?view=qa&at=6000`);
      await page.getByPlaceholder('输入与当前课程有关的问题').fill('Native seek race');
      await page.getByRole('button', { name: '提问', exact: true }).click();
      await expect(page.getByText('Fixture Tutor answer', { exact: true })).toBeVisible();
      await expect(video).toHaveJSProperty('readyState', 4);
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(6);
      verificationDelay = 700;
      await page.locator('.evidence-item button').click();
      await video.hover();
      const cdp = await page.context().newCDPSession(page);
      const { root } = await cdp.send('DOM.getDocument', { depth: -1, pierce: true });
      function find(node) {
        if (node.attributes?.includes('-webkit-media-controls-timeline')) return node;
        for (const child of [...(node.children || []), ...(node.shadowRoots || [])]) { const found = find(child); if (found) return found; }
      }
      const timeline = find(root); if (!timeline) throw Error('Native media timeline not inspectable');
      const { model } = await cdp.send('DOM.getBoxModel', { backendNodeId: timeline.backendNodeId });
      const q = model.content, x = q[0] + (q[2] - q[0]) * .65, y = (q[1] + q[5]) / 2;
      await page.mouse.move(x - 15, y); await page.mouse.down(); await page.mouse.move(x + 15, y, { steps: 4 }); await page.mouse.up();
      await expect.poll(() => video.evaluate(v => v.seeking)).toBe(false);
      const manualPosition = await video.evaluate(v => v.currentTime);
      console.log(JSON.stringify({ nativeTimelineDragSeconds: manualPosition }));
      expect(manualPosition).toBeGreaterThan(6.5);
      await new Promise(r => setTimeout(r, 1800));
      expect(await video.evaluate(v => v.currentTime)).toBeCloseTo(manualPosition, 2);
      await expectReviewCancelled();
      verificationDelay = 0;
    });

    await check('native video seek supersedes pending Evidence navigation', async () => {
      await page.goto(`${origin}/tasks/short?view=qa&at=6000`);
      await page.getByPlaceholder('输入与当前课程有关的问题').fill('Native seek race');
      await page.getByRole('button', { name: '提问', exact: true }).click();
      await expect(page.getByText('Fixture Tutor answer', { exact: true })).toBeVisible();
      await expect(video).toHaveJSProperty('readyState', 4);
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(6);
      verificationDelay = 700;
      await page.locator('.evidence-item button').click();
      await video.focus(); await video.press('ArrowLeft');
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBeCloseTo(5.88, 2);
      await new Promise(r => setTimeout(r, 1800));
      expect(await video.evaluate(v => v.currentTime)).toBeCloseTo(5.88, 2);
      await expectReviewCancelled();
      // Playback frames must not cancel a subsequent valid Evidence request.
      await video.evaluate(v => v.play());
      await page.locator('.evidence-item button').click();
      await expect(page.locator('.evidence-reading')).toBeVisible();
      await expect(current).toContainText('Second original passage');
      await video.evaluate(v => v.pause());
      verificationDelay = 0;
    });
    await check('rapid seeks and rapid workspace/history navigation keep the last intent', async () => {
      tokenDelay = 500;
      await page.goto(`${origin}/tasks/short?view=content&text=timeline&at=1000`);
      await expect(page.locator('.timeline-row')).toHaveCount(5);
      await page.evaluate(() => { const b = document.querySelectorAll('.timeline-row button'); for (const i of [3, 0, 2, 1, 3]) b[i].click(); });
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(5);
      await expect.poll(() => new URL(page.url()).searchParams.get('at')).toBe('5000');
      await page.evaluate(() => { const b = [...document.querySelectorAll('.workspace-nav button')]; for (const name of ['学习助手', '课程内容', '课程问答', '课程内容', '课程问答']) b.find(x => x.textContent.trim() === name).click(); });
      await expect(page.locator('.workspace-nav [aria-current=page]')).toHaveText('课程问答');
      await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBe('qa');
      await page.goBack(); await page.goForward();
      await expect(page.locator('.workspace-nav [aria-current=page]')).toHaveText('课程问答');
      tokenDelay = 0;
    });
    await check('stale Tutor evidence does not open changed original or discard follow-up input', async () => {
      await page.goto(`${origin}/tasks/short?view=qa&at=7000`);
      const input = page.getByPlaceholder('输入与当前课程有关的问题');
      await input.fill('Question for revision one'); await page.getByRole('button', { name: '提问', exact: true }).click();
      await expect(page.getByText('Fixture Tutor answer', { exact: true })).toBeVisible();
      await input.fill('Unsubmitted follow-up'); sourceRevision = 2;
      await page.getByRole('button', { name: '刷新', exact: true }).click();
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(7);
      await page.locator('.evidence-item button').click();
      await expect(page.getByText(/课程资料已更新，旧证据暂不能定位/)).toBeVisible();
      await expect(page.locator('.evidence-reading')).toBeHidden();
      await expect(input).toHaveValue('Unsubmitted follow-up');
      expect(await video.evaluate(v => v.currentTime)).toBe(7);
      await page.screenshot({ path: `${output}/stale-tutor.png`, fullPage: true });
    });
    await check('stale explanation and feedback retain the frozen session revision and answer draft', async () => {
      sourceRevision = 1;
      await page.goto(`${origin}/tasks/short?view=agent&at=7000`);
      const answer = page.getByRole('textbox', { name: '第 1 题作答' });
      await expect(answer).toHaveValue('Saved answer'); await answer.fill('Unsaved answer revision');
      sourceRevision = 2;
      await page.getByRole('button', { name: '回看这段课程证据', exact: true }).click();
      await expect(page.getByText(/课程资料已更新，旧证据暂不能定位/)).toBeVisible();
      await expect(answer).toHaveValue('Unsaved answer revision');
      await page.locator('.study-artifact > details summary').click(); await page.locator('.citation button').click();
      await expect(page.getByText(/课程资料已更新，旧证据暂不能定位/)).toBeVisible();
      await expect(page.locator('.evidence-reading')).toBeHidden();
    });
    await check('late verification cannot override a newer transcript seek or another course', async () => {
      sourceRevision = 1;
      await page.goto(`${origin}/tasks/short?view=qa&at=7000`);
      await page.getByPlaceholder('输入与当前课程有关的问题').fill('Question'); await page.getByRole('button', { name: '提问', exact: true }).click();
      await expect(page.getByText('Fixture Tutor answer', { exact: true })).toBeVisible();
      verificationDelay = 600;
      await page.locator('.evidence-item button').click(); await nav('课程内容').click();
      await page.getByRole('button', { name: '时间轴', exact: true }).click(); await page.locator('[data-segment="9"] button').click();
      await new Promise(r => setTimeout(r, 800)); expect(await video.evaluate(v => v.currentTime)).toBe(5);
      await nav('课程问答').click(); await page.locator('.evidence-item button').click();
      await page.evaluate(() => { history.pushState({}, '', '/tasks/other?view=content&text=timeline&at=8000'); dispatchEvent(new PopStateEvent('popstate')); });
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(8);
      await new Promise(r => setTimeout(r, 800)); expect(await video.evaluate(v => v.currentTime)).toBe(8);
      verificationDelay = 0;
    });
    await check('refresh invalidates a revision response already in flight', async () => {
      sourceRevision = 1;
      await page.goto(`${origin}/tasks/short?view=qa&at=7000`);
      await page.getByPlaceholder('输入与当前课程有关的问题').fill('Question'); await page.getByRole('button', { name: '提问', exact: true }).click();
      await expect(page.getByText('Fixture Tutor answer', { exact: true })).toBeVisible();
      const reads = verificationReads; verificationDelay = 600;
      await page.locator('.evidence-item button').click(); await expect.poll(() => verificationReads).toBeGreaterThan(reads);
      sourceRevision = 2; await page.getByRole('button', { name: '刷新', exact: true }).click();
      await new Promise(r => setTimeout(r, 800));
      expect(await video.evaluate(v => v.currentTime)).toBe(7); await expectReviewCancelled();
      verificationDelay = 0;
    });
    await check('a new revision citation refreshes an older cached transcript before showing it', async () => {
      sourceRevision = 1;
      await page.goto(`${origin}/tasks/short?view=qa&at=7000`);
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(7);
      sourceRevision = 2;
      await page.getByPlaceholder('输入与当前课程有关的问题').fill('Question about revised source'); await page.getByRole('button', { name: '提问', exact: true }).click();
      await expect(page.getByText('Fixture Tutor answer', { exact: true })).toBeVisible();
      await page.locator('.evidence-item button').click();
      await expect(current).toContainText('REVISED unrelated original');
    });
    await check('unavailable verification fails closed and a retry can resume evidence review', async () => {
      sourceRevision = 1;
      await page.goto(`${origin}/tasks/short?view=qa&at=7000`);
      await page.getByPlaceholder('输入与当前课程有关的问题').fill('Question'); await page.getByRole('button', { name: '提问', exact: true }).click();
      await expect(page.getByText('Fixture Tutor answer', { exact: true })).toBeVisible(); verificationFailure = true;
      await page.locator('.evidence-item button').click(); await expect(page.getByText(/无法核实课程证据/)).toBeVisible();
      await expect(page.locator('.evidence-reading')).toBeHidden(); verificationFailure = false;
      await page.locator('.evidence-item button').click(); await expect(current).toHaveAttribute('data-segment', '7');
      await expect.poll(() => video.evaluate(v => v.currentTime)).toBe(2);
    });
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
      await seek(0);
      // Pause in the media event loop so a busy Node process cannot sample past the 2-3s passage.
      await video.evaluate(v => new Promise((resolve, reject) => {
        const timer = setTimeout(() => { v.removeEventListener('timeupdate', pauseAtPassage); reject(Error('decoded playback timeout')); }, 15000);
        function pauseAtPassage() {
          if (v.currentTime < 2) return;
          v.pause(); clearTimeout(timer); v.removeEventListener('timeupdate', pauseAtPassage); resolve();
        }
        v.addEventListener('timeupdate', pauseAtPassage); v.play().catch(reject);
      }));
      expect(await video.evaluate(v => v.currentTime)).toBeGreaterThanOrEqual(2);
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
      // Loading and rendering 10,000 fixture intervals can outlast the default 5s assertion under concurrent DB tests.
      await expect.poll(() => video.evaluate(v => v.duration), { timeout: 15000 }).toBe(3900);
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
