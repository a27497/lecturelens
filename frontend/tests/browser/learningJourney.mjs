// Isolated real Java/MySQL + Python/PostgreSQL + Mock Provider journey.
// The fixed loopback ports belong to the test stack; never point this runner at a live service.
import { chromium, expect } from '@playwright/test';
import { createServer, request as proxyRequest } from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import { resolve, extname } from 'node:path';
import { parseArgs } from 'node:util';
const { values: args } = parseArgs({ options: { dist: { type: 'string' }, media: { type: 'string' }, chromium: { type: 'string' }, output: { type: 'string' } } });
if (!args.dist || !args.media || !args.output || !args.chromium) throw Error('Require --dist --media --chromium --output');
const dist = resolve(args.dist), output = resolve(args.output), apiBase = 'http://127.0.0.1:38434', origin = 'http://127.0.0.1:18436';
await mkdir(output, { recursive: true });
let token = '', delayReads = 0;
const requests = [], steps = [], pageErrors = [], blocked = [];
async function api(method, path, body, expected = 200, contentType = 'application/json', auth = token) {
  const response = await fetch(apiBase + path, { method, headers: { 'Content-Type': contentType, ...(auth ? { Authorization: `Bearer ${auth}` } : {}) }, body: body instanceof Buffer ? body : body === undefined ? undefined : JSON.stringify(body) });
  const payload = await response.json();
  if (response.status !== expected || (expected === 200 && String(payload.code) !== '0')) throw Error(`${method} ${path}: HTTP ${response.status} / ${payload.code}`);
  return payload.data;
}
async function account() {
  const credentials = { email: `pr4-${randomUUID()}@example.invalid`, password: `Isolated-${randomUUID()}-A1` };
  await api('POST', '/api/auth/register', credentials, 200, 'application/json', '');
  return (await api('POST', '/api/auth/login', credentials, 200, 'application/json', '')).accessToken;
}
async function createCourse() {
  const media = await readFile(args.media);
  const upload = await api('POST', '/api/uploads/sessions', { filename: `pr4-${randomUUID()}.mp4`, sizeBytes: media.length, chunkSizeBytes: media.length, totalChunks: 1, fileMd5: createHash('md5').update(media).digest('hex') });
  const boundary = 'pr4-' + randomUUID();
  const body = Buffer.concat([Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="chunk.bin"\r\nContent-Type: application/octet-stream\r\n\r\n`), media, Buffer.from(`\r\n--${boundary}--\r\n`)]);
  await api('POST', `/api/uploads/sessions/${upload.uploadId}/chunks/0`, body, 200, `multipart/form-data; boundary=${boundary}`);
  await api('POST', `/api/uploads/sessions/${upload.uploadId}/complete`);
  const task = await api('POST', '/api/tasks', { uploadId: upload.uploadId, sourceLanguage: 'en', targetLanguage: 'zh-CN' });
  await expect.poll(async () => { const status = (await api('GET', `/api/tasks/${task.taskId}`)).status; if (['FAILED', 'CANCELLED'].includes(status)) throw Error(`Synthetic course pipeline ${status}`); return status; }, { timeout: 180000 }).toBe('SUCCEEDED');
  // Sync is real, signed, and persisted; only embeddings and model responses are deterministic.
  await expect.poll(async () => (await api('GET', `/api/tasks/${task.taskId}/evidence/index-status`)).status, { timeout: 90000 }).toBe('READY');
  return task.taskId;
}
const server = createServer(async (req, res) => {
  const url = new URL(req.url, origin);
  try {
    if (url.pathname.startsWith('/api/')) {
      const parts = []; for await (const part of req) parts.push(part);
      const body = Buffer.concat(parts);
      let operation = null;
      if (url.pathname.includes('/study/') && body.length) { try { operation = JSON.parse(body).operation; } catch {} }
      const record = { method: req.method, path: url.pathname, operation, status: null };
      requests.push(record);
      const upstream = proxyRequest(apiBase + url.pathname + url.search, { method: req.method, headers: { ...req.headers, host: '127.0.0.1:38434' } }, response => {
        record.status = response.statusCode;
        const stream = () => { if (res.destroyed) { response.destroy(); return; } res.writeHead(response.statusCode, response.headers); response.pipe(res); };
        if (operation === 'READ' && delayReads) setTimeout(stream, delayReads); else stream();
      });
      upstream.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end(); });
      res.on('close', () => upstream.destroy()); upstream.end(body); return;
    }
    const file = url.pathname.startsWith('/assets/') ? resolve(dist, '.' + url.pathname) : resolve(dist, 'index.html');
    if (!file.startsWith(dist + '/')) { res.writeHead(403); res.end(); return; }
    const bytes = await readFile(file); res.writeHead(200, { 'Content-Type': ({ '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html' })[extname(file)] || 'application/octet-stream' }); res.end(bytes);
  } catch { if (!res.headersSent) res.writeHead(500); res.end(); }
});
await new Promise((resolve, reject) => { server.once('error', reject); server.listen(18436, '127.0.0.1', resolve); });
let browser, observedPage;
try {
  token = await account(); const task = await createCourse(); const otherCourse = await createCourse();
  if (task === otherCourse) throw Error('Expected two isolated course identities');
  browser = await chromium.launch({ headless: true, executablePath: args.chromium, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.addInitScript(value => localStorage.setItem('courselingo.accessToken', value), token);
  await context.route('**/*', route => { if (new URL(route.request().url()).origin === origin) return route.continue(); blocked.push(new URL(route.request().url()).origin); return route.abort(); });
  const page = await context.newPage(); observedPage = page; page.on('pageerror', error => pageErrors.push(String(error)));
  const nav = name => page.getByRole('navigation', { name: '课程内容导航' }).getByRole('button', { name, exact: true });
  const count = operation => requests.filter(r => r.operation === operation).length;
  const read = () => api('POST', `/api/tasks/${task}/study/command`, { operation: 'READ', session_id: session, run_id: run });
  async function capture(name, note) {
    console.log(`STEP ${name}`);
    await writeFile(`${output}/${name}.aria.txt`, await page.locator('body').ariaSnapshot());
    await page.screenshot({ path: `${output}/${name}.png`, fullPage: false });
    steps.push({ name, note, urlKeys: [...new URL(page.url()).searchParams.keys()], writes: requests.filter(r => ['START','CREATE_SESSION','SAVE_ATTEMPT','START_FEEDBACK','SAVE_FEEDBACK_NOTE'].includes(r.operation)).map(r => r.operation) });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  function commandResponse(operation) { return page.waitForResponse(response => response.url().includes('/study/') && response.request().method() === 'POST' && response.request().postDataJSON()?.operation === operation); }
  await page.goto(`${origin}/tasks/${task}?view=content&text=timeline&at=2000`);
  await expect(page.locator('.timeline-row').first()).toBeVisible();
  const video = page.locator('video'); await expect(video).toHaveJSProperty('readyState', 4);
  await video.evaluate(async video => { await video.play(); }); await expect.poll(() => video.evaluate(v => v.getVideoPlaybackQuality().totalVideoFrames)).toBeGreaterThan(0); await video.evaluate(v => v.pause());
  expect(count('START')).toBe(0); expect(count('CREATE_SESSION')).toBe(0);
  await capture('01-course-reading', 'Decoded synthetic video, real persisted transcript and read-only learning entry.');
  const scope = page.getByRole('region', { name: '学习范围' });
  await scope.locator('.scope-options > summary').click();
  await scope.getByRole('radio', { name: '选择课程片段' }).check();
  await scope.locator('.scope-item input[type=checkbox]').first().check();
  await scope.locator('.scope-options > summary').click();
  await nav('课程问答').click();
  const question = page.getByPlaceholder('输入与当前课程有关的问题'); await question.fill('What is the stopping condition in this course passage?');
  const qaResponse = page.waitForResponse(r => r.url().includes('/qa/scoped') && r.request().method() === 'POST');
  await page.getByRole('button', { name: '提问', exact: true }).click(); const qa = await (await qaResponse).json();
  expect(qa.data.evidence.length).toBeGreaterThan(0); expect(count('START')).toBe(0); expect(count('CREATE_SESSION')).toBe(0);
  expect((await api('POST', `/api/tasks/${task}/study/command`, { operation: 'LIST' })).sessions).toHaveLength(0);
  await question.fill('UNSAVED Tutor follow-up');
  await capture('02-tutor-question', 'Explicit scoped QA completes without creating an Agent Session or Run.');
  await page.locator('.evidence-item button').first().click(); await expect(page.locator('.evidence-reading')).toBeVisible();
  await expect(question).toHaveValue('UNSAVED Tutor follow-up');
  await page.getByRole('button', { name: '返回当前学习任务' }).click(); await expect(question).toHaveValue('UNSAVED Tutor follow-up');
  await nav('学习助手').click(); const goal = page.getByRole('textbox', { name: '学习目标' });
  const savedGoal = 'Explain the stopping condition and create two practice questions using this course passage.';
  await goal.fill(savedGoal); const starting = commandResponse('START');
  await page.getByRole('button', { name: '解释并出题', exact: true }).click(); const started = (await (await starting).json()).data;
  const session = started.run.session_id, run = started.run.run_id;
  const frozen = structuredClone(started.run.learning_scope); expect(frozen.kind).toBe('segments'); expect(frozen.policy).toBe('strict'); expect(frozen.evidence_ids).toHaveLength(1);
  await expect(page.locator('.study-artifact')).toBeVisible({ timeout: 90000 });
  await expect(page.getByRole('textbox', { name: '第 1 题作答' })).toBeVisible();
  await capture('03-saved-study-run', 'Explicit START creates the real persisted Run and artifact with frozen strict scope.');
  const answer = page.getByRole('textbox', { name: '第 1 题作答' }); const answer1 = 'The base case stops recursion.';
  await answer.fill(answer1); const saving = commandResponse('SAVE_ATTEMPT');
  await page.locator('.practice-question').filter({ has: answer }).getByRole('button', { name: '保存作答', exact: true }).click();
  const attempt1 = (await (await saving).json()).data.attempt; expect(attempt1.version).toBe(1);
  const feedbackStarted = commandResponse('START_FEEDBACK');
  await page.getByRole('region', { name: '第 1 题证据反馈' }).getByRole('button', { name: '获取证据反馈', exact: true }).click();
  const feedbackStart = (await (await feedbackStarted).json()).data; const feedbackRun = feedbackStart.run.run_id;
  await expect(page.getByRole('heading', { name: '第 1 版作答的证据反馈' })).toBeVisible({ timeout: 90000 });
  await page.getByText('核对或更正反馈', { exact: true }).click(); const note = page.getByRole('textbox', { name: '反馈核对意见' });
  await note.fill('Check the source before accepting this feedback.'); await answer.fill('UNSAVED revised answer'); await goal.fill('UNSAVED next learning goal');
  await capture('04-feedback-task', 'Real saved answer v1 and feedback, with unsaved same-page answer/goal/note for continuity checks.');
  const beforeReviewWrites = requests.filter(r => ['START','CREATE_SESSION','SAVE_ATTEMPT','START_FEEDBACK','SAVE_FEEDBACK_NOTE'].includes(r.operation)).length;
  const citation = page.getByRole('button', { name: '回看这段课程证据', exact: true }).first();
  await citation.click(); await expect(page.locator('.timeline-row[aria-current=true]')).toBeVisible();
  await expect(answer).toHaveValue('UNSAVED revised answer'); await expect(goal).toHaveValue('UNSAVED next learning goal'); await expect(note).toHaveValue('Check the source before accepting this feedback.');
  await capture('05-feedback-source', 'Source revision checked via real Java APIs; drafts and original feedback stay intact.');
  {
    const overlap = await page.evaluate(() => {
      const visible = el => { const r = el.getBoundingClientRect(); return r.bottom > 140 && r.top < innerHeight; };
      return visible(document.querySelector('.timeline-row[aria-current=true]')) && visible(document.querySelector('.practice-feedback article'));
    }); expect(overlap).toBe(true);
  }
  await page.getByRole('button', { name: '返回当前学习任务' }).click();
  await expect(answer).toHaveValue('UNSAVED revised answer'); await expect(note).toHaveValue('Check the source before accepting this feedback.');
  expect(requests.filter(r => ['START','CREATE_SESSION','SAVE_ATTEMPT','START_FEEDBACK','SAVE_FEEDBACK_NOTE'].includes(r.operation))).toHaveLength(beforeReviewWrites);
  await capture('06-return-task', 'Return restores the existing task without any write or new model execution.');
  const answer2 = 'Recursive steps reduce the remaining problem until the base case returns.';
  await answer.fill(answer2); const revision = commandResponse('SAVE_ATTEMPT');
  await page.locator('.practice-question').filter({ has: answer }).getByRole('button', { name: '保存作答', exact: true }).click();
  const attempt2 = (await (await revision).json()).data.attempt; expect(attempt2.version).toBe(2); expect(attempt2.attempt_id).not.toBe(attempt1.attempt_id);
  await expect(page.getByText('你已保存新版作答，下面反馈仅对应旧版。', { exact: true })).toBeVisible();
  const noted = commandResponse('SAVE_FEEDBACK_NOTE'); await page.getByRole('button', { name: '保存核对意见', exact: true }).click(); expect((await (await noted).json()).data.note.disposition).toBe('disputed');
  await page.getByRole('button', { name: '修改记录', exact: true }).first().click();
  await expect(page.locator('.answer-history').getByText(answer1, { exact: true })).toBeVisible(); await expect(page.locator('.answer-history').getByText(answer2, { exact: true })).toBeVisible();
  await capture('07-revision-history', 'Immutable answer v1/v2 coexist; the disputed feedback remains attached to v1.');
  {
    await scope.locator('.scope-options > summary').click(); await scope.getByRole('radio', { name: '整节课程', exact: true }).check(); await scope.locator('.scope-options > summary').click();
    expect((await read()).run.learning_scope).toEqual(frozen);
  }
  const writesBeforeReload = requests.filter(r => ['START','CREATE_SESSION','SAVE_ATTEMPT','START_FEEDBACK','SAVE_FEEDBACK_NOTE'].includes(r.operation)).length;
  await page.reload(); await expect(page.getByRole('textbox', { name: '第 1 题作答' })).toHaveValue(answer2, { timeout: 30000 });
  await expect(page.getByText('你已标记反馈不准确', { exact: true })).toBeVisible(); await expect(goal).toHaveValue(savedGoal);
  const restored = await read(); expect(restored.run.run_id).toBe(run); expect(restored.run.learning_scope).toEqual(frozen);
  expect(restored.attempts.find(a => a.question_index === 0).attempt_id).toBe(attempt2.attempt_id);
  const restoredFeedback = restored.feedback_runs.find(f => f.run_id === feedbackRun); expect(restoredFeedback.feedback.attempt_id).toBe(attempt1.attempt_id); expect(restoredFeedback.feedback.note.disposition).toBe('disputed');
  expect(requests.filter(r => ['START','CREATE_SESSION','SAVE_ATTEMPT','START_FEEDBACK','SAVE_FEEDBACK_NOTE'].includes(r.operation))).toHaveLength(writesBeforeReload);
  await capture('08-server-restored', 'Full reload restores the real server Run, answer v2, feedback v1 and disputed note; no new write.');
  {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: '继续第 1 题', exact: true }).click();
    await answer.fill('UNSAVED narrow-screen answer'); await page.getByText('核对或更正反馈', { exact: true }).click(); await note.fill('UNSAVED narrow-screen note');
    await capture('09-mobile-task', '390px task view and unsaved answer/note.');
    await page.getByRole('button', { name: '回看这段课程证据', exact: true }).first().focus(); await page.keyboard.press('Enter'); await expect(page.locator('.timeline-row[aria-current=true]')).toBeVisible();
    await expect(page.locator('.timeline-row[aria-current=true]')).toBeInViewport();
    await capture('10-mobile-source', 'Keyboard source navigation retains a current-question summary and a return button.');
    await page.getByRole('button', { name: '返回当前学习任务' }).focus(); await page.keyboard.press('Enter');
    await expect(answer).toHaveValue('UNSAVED narrow-screen answer'); await expect(note).toHaveValue('UNSAVED narrow-screen note');
    await capture('11-mobile-return', 'Keyboard return restores existing task drafts; no persistence claim for unsaved inputs.');
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  const readsBeforeSwitch = count('READ'); delayReads = 800; const lateRead = page.reload(); await lateRead;
  await expect.poll(() => count('READ')).toBeGreaterThan(readsBeforeSwitch);
  await page.evaluate(path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate')); }, `/tasks/${otherCourse}?view=agent`);
  await expect(goal).toHaveValue(''); await new Promise(r => setTimeout(r, 1100)); expect(await page.locator('.study-artifact').count()).toBe(0); await expect(goal).toHaveValue(''); delayReads = 0;
  await capture('12-course-switch', 'A delayed real READ from course A does not populate course B; no Run created for B.');
  const otherToken = await account(); await api('GET', `/api/tasks/${task}`, undefined, 404, 'application/json', otherToken);
  await api('GET', `/api/tasks/${task}/evidence`, undefined, 404, 'application/json', otherToken);
  await api('POST', `/api/tasks/${task}/study/command`, { operation: 'READ', session_id: session, run_id: run }, 404, 'application/json', otherToken);
  await page.goto(`${origin}/tasks/${task}?view=agent`); await expect(answer).toHaveValue(answer2);
  await api('POST', '/api/tasks/batch-delete', { taskIds: [task] }); await page.getByRole('button', { name: '刷新', exact: true }).click();
  { await expect(page.getByRole('heading', { name: '课程不可用或权限已变化' })).toBeVisible(); expect(await page.locator('.study-artifact').count()).toBe(0); expect(await page.locator('video').count()).toBe(0); }
  await capture('13-deleted-course', 'Actual authorized deletion followed by a denied owning-course read clears cached learning/material panels.');
  expect(pageErrors).toEqual([]); expect(blocked).toEqual([]); expect(count('START')).toBe(1); expect(count('CREATE_SESSION')).toBe(1); expect(count('SAVE_ATTEMPT')).toBe(2); expect(count('START_FEEDBACK')).toBe(1); expect(count('SAVE_FEEDBACK_NOTE')).toBe(1);
  await api('POST', '/api/tasks/batch-delete', { taskIds: [otherCourse] });
  const storageKeys = await page.evaluate(() => Object.keys(localStorage)); expect(storageKeys).toEqual(['courselingo.accessToken']);
  await writeFile(`${output}/verification.json`, JSON.stringify({ mode: 'candidate', api: 'Real isolated Java/MySQL + Python/PostgreSQL and signed Evidence APIs', models: 'Mock Provider; deterministic hash embeddings; no paid requests or quality certification', steps, requests, pageErrors, blocked, storageKeys, identities: { task, otherCourse, session, run, artifact: attempt1.artifact_id, attempt1: attempt1.attempt_id, attempt2: attempt2.attempt_id, feedbackRun }, frozen }, null, 2));
  console.log(`PASS real isolated learning journey (${steps.length} captures); one explicit Run, two answer versions, one feedback and one note; no passive writes`);
} catch (failure) {
  if (observedPage) {
    await writeFile(`${output}/failure.aria.txt`, await observedPage.locator('body').ariaSnapshot());
    await observedPage.screenshot({ path: `${output}/failure.png`, fullPage: true });
  }
  await writeFile(`${output}/failure-requests.json`, JSON.stringify(requests, null, 2));
  throw failure;
} finally { if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); }
