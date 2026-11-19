import { expect, test } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createB1Fixture } from './b1Fixture.mjs';

const path = relative => fileURLToPath(new URL(relative, import.meta.url));
const course = '/tasks/synthetic';
const email = 'synthetic@example.invalid';
const draftText = '保留这条未发送的追问';
const vtt = await readFile(path('../../../fixtures/demo/binary-search.en.vtt'), 'utf8');
const longPassage = vtt.trim().split(/\r?\n\r?\n/).slice(1, 9).map(cue => cue.split(/\r?\n/).slice(1).join(' ')).join(' ');
const rows = [
  { segmentIndex: 1, startMillis: 0, endMillis: 64_000, language: 'en', sourceText: longPassage },
  { segmentIndex: 2, startMillis: 64_000, endMillis: 80_000, language: 'en', sourceText: 'Trace the example in the sorted array.' },
];

let fixture;
test.beforeAll(async () => {
  fixture = await createB1Fixture({ dist: process.env.LECTURELENS_DIST_DIR || path('../../dist'), media: path('../../../fixtures/demo/binary-search-demo.mp4') });
});
test.afterAll(async () => { await fixture?.close(); });

async function signIn(page, target) {
  await page.route('**/*', route =>
    new URL(route.request().url()).origin === fixture.origin ? route.fallback() : route.abort());
  await page.goto(`${fixture.origin}/login?redirect=${encodeURIComponent(target)}`);
  await page.getByPlaceholder('you@example.com').fill(email);
  await page.getByPlaceholder('请输入密码').fill('synthetic-local-password');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page).toHaveURL(url => url.pathname + url.search === target);
}
const openCourse = (page, view) => signIn(page, `${course}?view=${view}&layout=continuous`);
const screenshot = (page, testInfo, name) => page.screenshot({
  path: testInfo.outputPath(`${name}.png`), animations: 'disabled',
  mask: [page.getByText(email, { exact: true })], maskColor: '#fffdf8',
});

async function tutorFixture(page, citationStart = rows[0].startMillis) {
  const citation = {
    evidence_id: 'course:synthetic:subtitle:1:r1', start_ms: citationStart, end_ms: rows[0].endMillis,
    source_type: 'SUBTITLE', text: longPassage,
  };
  const session = { session_id: 'citation-session', revision: 1, status: 'active', model_calls: 1, max_calls: 40 };
  const turn = {
    turn_id: 'citation-turn', client_turn_id: 'fixture-turn', ordinal: 1, status: 'completed',
    learner_text: '为什么 low 大于 high 时循环就停止？', outcome: 'answered',
    answer: `可以核对这段课程原文 [${citation.evidence_id}]`, citations: [citation], socratic: false,
  };
  const state = { revisionReads: 0, revision: 1, sourceReads: 0, sourceMissing: false, denied: false, videoUnavailable: false, posts: 0 };
  const reply = (route, data, status = 200) => route.fulfill({ status, json: { code: '0', data } });
  await page.route('**/api/**', async route => {
    const { pathname } = new URL(route.request().url());
    const base = `/api${course}`;
    if (route.request().method() === 'POST' && /\/tutor\/|\/study\//.test(pathname)) state.posts++;
    if (pathname === `${base}/tutor/sessions`) return reply(route, { sessions: [session], revision: 1 });
    if (pathname === `${base}/tutor/sessions/${session.session_id}`) return reply(route, { session, turns: [turn] });
    if (pathname === `${base}/evidence/index-status`) {
      state.revisionReads++;
      return reply(route, { revision: state.revision, status: 'READY' }, state.denied ? 404 : 200);
    }
    if (state.denied && pathname === base) return reply(route, null, 404);
    if (state.videoUnavailable && pathname === `${base}/playback-token`) return reply(route, null, 409);
    if (pathname === `${base}/results`) {
      state.sourceReads++;
      const response = await route.fetch();
      const { data } = await response.json();
      return reply(route, { ...data, subtitles: state.sourceMissing ? rows.slice(1) : rows, translationStatus: 'SKIPPED', translatedFullText: '' });
    }
    return route.fallback();
  });
  return { citation, state };
}

async function openCitation(page) {
  const tutor = page.getByRole('region', { name: 'Tutor', exact: true });
  const draft = tutor.getByLabel('向课程 Tutor 提问');
  const trigger = tutor.getByRole('button', { name: /^定位出处/ }).first();
  await draft.fill(draftText);
  await trigger.focus();
  await page.keyboard.press('Enter');
  const reference = page.locator('.timeline-row[data-reference=true]');
  await expect(reference).toBeFocused();
  return { draft, trigger, reference };
}

const header = page => page.locator('.evidence-reading__return');
const jump = page => header(page).getByRole('button', { name: '跳到视频', exact: true });
const back = page => header(page).getByRole('button', { name: '返回当前学习任务' });
const writeNote = page => header(page).getByRole('button', { name: /写笔记$/ });
const video = page => page.getByLabel('课程视频', { exact: true });

async function controlGeometry(control) {
  return control.evaluate(el => {
    const { left, top, right, bottom, width, height } = el.getBoundingClientRect();
    return {
      top, bottom, width, height,
      fullyInView: left >= 0 && top >= 0 && right <= innerWidth && bottom <= innerHeight && width > 0 && height > 0,
      centerHitTest: el.contains(document.elementFromPoint(left + width / 2, top + height / 2)),
    };
  });
}

test('long Tutor citation exposes a keyboard video jump before scrolling', async ({ page, isMobile }, testInfo) => {
  const { citation, state } = await tutorFixture(page);
  await openCourse(page, 'tutor');
  await expect(page.locator('.login-success-message')).toBeHidden();
  const { draft, trigger, reference } = await openCitation(page);
  await expect(reference).toContainText('00:00:00 - 00:01:04');
  const controls = await Promise.all([jump(page), back(page), writeNote(page)].map(controlGeometry));
  for (const box of controls) {
    expect(box).toMatchObject({ fullyInView: true, centerHitTest: true });
    if (isMobile) expect(box.height).toBeGreaterThanOrEqual(44);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(page.viewportSize().width);
  await expect(reference.getByRole('button')).toHaveCount(0);
  await screenshot(page, testInfo, 'first-view');
  if (isMobile) await expect(video(page)).toBeHidden();

  const before = { revisions: state.revisionReads, source: state.sourceReads };
  await jump(page).focus();
  await page.keyboard.press('Enter');
  await expect(video(page)).toBeInViewport();
  await expect.poll(() => video(page).evaluate(el => el.readyState)).toBeGreaterThan(0);
  await expect.poll(() => video(page).evaluate(el => Math.round(el.currentTime * 1000))).toBe(citation.start_ms);
  await expect(video(page)).toHaveJSProperty('paused', true);
  await expect(jump(page)).toBeFocused();
  expect(state.revisionReads - before.revisions).toBe(2);
  expect(state.sourceReads - before.source).toBe(1);
  await screenshot(page, testInfo, 'paused-video');

  await back(page).press('Enter');
  await expect(trigger).toBeFocused();
  await expect(draft).toHaveValue(draftText);
  await screenshot(page, testInfo, 'tutor-return');

  await trigger.press('Enter');
  await writeNote(page).press('Enter');
  await expect(page.getByRole('textbox', { name: '记录你的理解' })).toBeFocused();
  await expect(page.getByText('当前证据', { exact: false })).toBeVisible();
  await screenshot(page, testInfo, 'citation-note');
  expect(state.posts).toBe(0);
  await writeFile(testInfo.outputPath('geometry.json'), JSON.stringify({
    viewport: page.viewportSize(), controls, citationMs: citation.start_ms, paused: true, revisionReads: 2, sourceReads: 1, runWrites: state.posts,
  }, null, 2));
});

test('uses the exact citation time and keeps other transcript seeks active', async ({ page }) => {
  const { citation } = await tutorFixture(page, 2_250);
  await openCourse(page, 'tutor');
  await openCitation(page);
  await jump(page).press('Enter');
  await expect(video(page)).toBeVisible();
  await expect.poll(() => video(page).evaluate(el => Math.round(el.currentTime * 1000))).toBe(citation.start_ms);
  await page.locator('.timeline-row[data-segment="2"]').getByRole('button', { name: /片段 2$/ }).press('Enter');
  await expect.poll(() => video(page).evaluate(el => Math.round(el.currentTime * 1000))).toBe(rows[1].startMillis);
  await expect(jump(page)).toHaveCount(0);
});

for (const failure of ['revision', 'permission', 'source', 'video']) {
  test(`citation header honors ${failure} eligibility`, async ({ page }) => {
    const { state } = await tutorFixture(page);
    state.videoUnavailable = failure === 'video';
    await openCourse(page, 'tutor');
    const { draft, reference } = await openCitation(page);
    if (state.videoUnavailable) {
      await expect(jump(page)).toHaveCount(0);
      await expect(reference.getByRole('button', { name: '跳到视频', exact: true })).toBeVisible();
      await expect(video(page)).toHaveCount(0);
      return;
    }
    state.revision = failure === 'revision' ? 2 : 1;
    state.sourceMissing = failure === 'source';
    state.denied = failure === 'permission';
    await jump(page).press('Enter');
    await expect(jump(page)).toHaveCount(0);
    await expect(reference).toHaveCount(0);
    if (state.denied) await expect(page.getByText('课程不可用或权限已变化')).toBeVisible();
    else {
      await expect(page.locator('.evidence-navigation-error')).toContainText(state.sourceMissing ? '课程原文不可定位' : '课程资料已更新');
      await expect(draft).toHaveValue(draftText);
    }
    expect(state.posts).toBe(0);
  });
}

test('login feedback and practice controls use readable, usable targets', async ({ page }, testInfo) => {
  await openCourse(page, 'agent');
  const toast = page.locator('.login-success-message');
  await expect(toast).toBeVisible();
  await expect(toast).toHaveCSS('background-color', 'rgb(230, 241, 233)');
  await expect(toast.locator('.el-message__content')).toHaveCSS('color', 'rgb(35, 92, 69)');
  await screenshot(page, testInfo, 'login-success');
  await expect(toast).toBeHidden();

  const format = page.getByRole('combobox', { name: '练习形式', exact: true });
  const approval = page.getByRole('checkbox', { name: '发布前由我审批', exact: true });
  const newGoal = page.locator('.new-study-goal > summary');
  if (!await format.isVisible()) await newGoal.press('Enter');
  await expect(format).toBeVisible();
  const formatBox = await format.boundingBox();
  const approvalBox = await approval.boundingBox();
  expect(formatBox.height).toBeGreaterThanOrEqual(44);
  expect(approvalBox.height).toBeGreaterThanOrEqual(24);
  expect(approvalBox.width).toBeGreaterThanOrEqual(24);
  await approval.press('Space');
  await expect(approval).toBeChecked();
  await format.selectOption('choice');
  await expect(approval).toBeDisabled();
  await format.selectOption('open');
  await expect(approval).toBeEnabled();
  await screenshot(page, testInfo, 'practice-controls');
});

test('upload receipt names progress and Study waits for the course readiness event', async ({ page }, testInfo) => {
  const media = path('../../../fixtures/demo/binary-search-demo.mp4');
  const sizeBytes = (await readFile(media)).length;
  const uploadId = 'fixture-upload';
  const session = { uploadId, status: 'UPLOADING' };
  const sessions = '/api/uploads/sessions';
  const taskApi = `/api${course}`;
  let studyReads = 0, created = 0, ready = false;
  let publishReady;
  const waitForReady = new Promise(resolve => { publishReady = resolve; });
  const replies = new Map([
    [sessions, session],
    [`${sessions}/${uploadId}/missing-chunks`, { ...session, totalChunks: 1, uploadedChunks: [], missingChunks: [0], allUploaded: false }],
    [`${sessions}/${uploadId}/chunks/0`, { ...session, chunkIndex: 0, uploaded: true }],
    [`${sessions}/${uploadId}/complete`, { uploadId, status: 'COMPLETED', sizeBytes }],
    [`/api/uploads/${uploadId}/playback-token`, { playbackUrl: '/synthetic.mp4', expiresAt: '2099-01-01T00:00:00Z' }],
    [`/api/uploads/${uploadId}/embedded-subtitles`, { status: 'NOT_FOUND', tracks: [], selectedStreamIndex: null }],
  ]);
  const reply = (route, data) => route.fulfill({ json: { code: '0', data } });
  await page.route('**/api/**', async route => {
    const { pathname } = new URL(route.request().url());
    if (replies.has(pathname)) return reply(route, replies.get(pathname));
    if (pathname === '/api/tasks' && route.request().method() === 'POST') {
      created++;
      return reply(route, { taskId: 'synthetic' });
    }
    if (pathname === taskApi) {
      const response = await route.fetch();
      const { data } = await response.json();
      return reply(route, { ...data, status: 'RUNNING', currentStage: 'TRANSCRIBE', learningReady: ready });
    }
    if (pathname === `${taskApi}/events`) {
      await waitForReady;
      return route.fulfill({
        contentType: 'text/event-stream',
        body: `event: snapshot\ndata: ${JSON.stringify({ taskId: 'synthetic', status: 'RUNNING', progressPercent: 75, currentStage: 'TRANSLATE', learningReady: true })}\n\n`,
      });
    }
    if (pathname === `${taskApi}/study/status`) studyReads++;
    return route.fallback();
  });
  try {
    await signIn(page, '/upload');
    await page.locator('input[type=file]').setInputFiles(media);
    await page.getByRole('button', { name: '开始上传', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: '服务器已接收视频' })).toBeVisible();
    await expect(page.getByRole('progressbar', { name: '视频上传进度' })).toHaveAttribute('aria-valuenow', '100');
    const preview = page.locator('.preview-note > summary');
    await expect(preview.getByRole('button')).toHaveCount(0);
    await preview.press('Enter');
    await expect(page.getByText(/播放刚上传的原始视频/)).toBeVisible();
    const help = page.getByRole('button', { name: '课程处理说明' });
    const target = await help.boundingBox();
    expect(target.width).toBeGreaterThanOrEqual(24);
    expect(target.height).toBeGreaterThanOrEqual(24);
    await help.press('Enter');
    await expect(page.getByText('系统会在后台生成字幕、翻译和学习笔记。')).toBeVisible();
    await expect.poll(() => page.getByLabel('原视频预览').evaluate(el => el.readyState)).toBeGreaterThan(0);
    await screenshot(page, testInfo, 'upload-received');

    await page.getByRole('button', { name: '开始处理', exact: true }).click();
    await expect(page).toHaveURL(url => url.pathname === course);
    await page.getByRole('navigation', { name: '课程学习导航' }).getByRole('button', { name: '练习', exact: true }).click();
    await expect(page.getByText(/课程内容尚未处理完成/)).toBeVisible();
    expect(studyReads).toBe(0);
    ready = true;
    publishReady();
    await expect.poll(() => studyReads).toBe(1);
    expect(created).toBe(1);
  } finally {
    publishReady();
  }
});
