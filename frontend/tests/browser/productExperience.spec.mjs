import { expect, test } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const noteText = '中点小于目标时，下一个范围从中点右侧开始。';

async function openMock(page, { newAccount = false } = {}) {
  const instance = process.env.LECTURELENS_DEMO_INSTANCE || 'default';
  if (!/^[a-z0-9-]{1,32}$/.test(instance)) throw new Error('Invalid Mock instance name');
  const stack = new URL(`../../../.demo/stack-${instance}/`, import.meta.url);
  const state = JSON.parse(await readFile(new URL('state.json', stack), 'utf8'));
  if (state.mode !== 'mock' || !state.task_id || !state.ready_seconds || !Number.isInteger(state.ports?.WEB_PORT)) {
    throw new Error('Start the isolated seeded Mock stack before running the browser test');
  }
  const base = `http://127.0.0.1:${state.ports.WEB_PORT}`;
  const { DEMO_PASSWORD: password } = JSON.parse(await readFile(new URL('secrets.json', stack), 'utf8'));
  const email = newAccount ? `phase3-${randomUUID()}@example.com` : 'demo@example.com';
  if (newAccount) {
    const registration = await page.request.post(`${base}/api/auth/register`, { data: { email, password } });
    expect(registration.status()).toBe(200);
  }
  const login = await page.request.post(`${base}/api/auth/login`, { data: { email, password } });
  expect(login.status()).toBe(200);
  const { data: { accessToken, refreshToken, user } } = await login.json();
  await page.addInitScript(({ origin, access, refresh, account }) => {
    if (location.origin !== origin || localStorage.getItem('courselingo.accessToken')) return;
    localStorage.setItem('courselingo.accessToken', access);
    localStorage.setItem('courselingo.refreshToken', refresh);
    localStorage.setItem('courselingo.userEmail', account);
  }, { origin: base, access: accessToken, refresh: refreshToken, account: email });
  return { base, taskId: state.task_id, userId: user.userId };
}

function monitor(page) {
  const counts = { pageErrors: 0, consoleErrors: 0, failedLocalRequests: 0, externalRequests: 0, httpErrors: {} };
  page.on('pageerror', () => counts.pageErrors++);
  page.on('console', message => { if (message.type() === 'error') counts.consoleErrors++; });
  page.on('request', request => {
    if (/^https?:/.test(request.url()) && new URL(request.url()).hostname !== '127.0.0.1') counts.externalRequests++;
  });
  page.on('requestfailed', request => {
    if (request.failure()?.errorText !== 'net::ERR_ABORTED') counts.failedLocalRequests++;
  });
  page.on('response', response => {
    if (response.status() < 400) return;
    const path = new URL(response.url()).pathname.replace(/\/tasks\/[^/]+/, '/tasks/{course}');
    const key = `${response.status()} ${response.request().method()} ${path}`;
    counts.httpErrors[key] = (counts.httpErrors[key] ?? 0) + 1;
  });
  return counts;
}

const evidencePath = (page, name, extension) => {
  const dir = process.env.LECTURELENS_SCREENSHOT_DIR;
  return dir ? resolve(dir, `${page.viewportSize().width}-${name}.${extension}`) : undefined;
};

async function screenshot(page, name) {
  const path = evidencePath(page, name, 'png');
  if (path) await page.screenshot({ path, animations: 'disabled' });
}

async function record(page, name, counts) {
  const path = evidencePath(page, name, 'json');
  if (path) await writeFile(path, JSON.stringify(counts, null, 2) + '\n');
  expect(counts.pageErrors).toBe(0);
  expect(counts.failedLocalRequests).toBe(0);
  expect(counts.externalRequests).toBe(0);
}

async function expectFit(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(page.viewportSize().width);
}

test('keeps verified citation and playback notes across reload and returns focus from the source', async ({ page }) => {
  const { base, taskId, userId } = await openMock(page);
  const counts = monitor(page);
  await page.goto(`${base}/tasks/${taskId}?view=tutor&layout=continuous`);
  const nav = page.getByRole('navigation', { name: '课程内容导航' });
  const tutor = page.getByRole('region', { name: 'Tutor', exact: true });
  const composer = tutor.getByLabel('向课程 Tutor 提问');
  await expect(composer).toBeVisible();
  await expectFit(page);
  await screenshot(page, 'tutor-restore');
  await expect(tutor.getByText('正在恢复对话…')).toBeHidden();
  await tutor.getByRole('button', { name: '新对话' }).click();
  await composer.fill('为什么 low 大于 high 时循环就停止？');
  await tutor.getByRole('button', { name: '发送', exact: true }).click();
  const citation = tutor.getByRole('button', { name: /^定位出处/ }).first();
  await expect(citation).toBeVisible({ timeout: 45_000 });
  await screenshot(page, 'tutor-cited');
  const wide = page.viewportSize().width > 1024;
  if (wide) {
    const source = await page.getByRole('region', { name: '视频与课程材料' }).boundingBox();
    const learning = await page.getByRole('region', { name: '课程学习工作台' }).boundingBox();
    expect(source.width / (source.width + learning.width)).toBeCloseTo(0.56, 2);
  }
  await composer.fill('保留这条未发送的追问');
  await citation.focus();
  await page.keyboard.press('Enter');
  const highlighted = page.locator('.timeline-row[data-reference="true"]');
  await expect(highlighted).toBeFocused();
  await expectFit(page);
  await screenshot(page, 'verified-source');
  await page.getByRole('button', { name: '返回当前学习任务' }).click();
  await expect(citation).toBeFocused();
  await expect(composer).toHaveValue('保留这条未发送的追问');

  await citation.press('Enter');
  const write = page.getByRole('button', { name: /写笔记$/ });
  await expect(write).toBeVisible();
  await write.click();
  const textarea = page.getByRole('textbox', { name: '记录你的理解' });
  await expect(textarea).toBeFocused();
  await expect(page.getByText('当前证据', { exact: false })).toBeVisible();
  await textarea.fill(noteText);
  await page.getByRole('button', { name: '保存笔记' }).click();
  await expect(page.getByRole('status').filter({ hasText: '笔记已保存' })).toBeVisible();
  await screenshot(page, 'note-saved');

  await page.reload();
  await expect(page.getByText(noteText, { exact: true })).toBeVisible();
  const savedSource = page.getByRole('button', { name: /^定位出处/ });
  await savedSource.press('Enter');
  await expect(highlighted).toBeFocused();
  await page.getByRole('button', { name: '返回当前学习任务' }).click();
  await expect(savedSource).toBeFocused();
  await page.getByRole('button', { name: '删除笔记', exact: true }).click();
  await page.getByRole('button', { name: '确认删除' }).click();
  await expect(page.getByText(noteText, { exact: true })).toHaveCount(0);

  if (wide) await page.getByRole('navigation', { name: '课程内容视图' }).getByRole('button', { name: '章节' }).click();
  else {
    await nav.getByRole('button', { name: '课程材料' }).click();
    await page.getByRole('navigation', { name: '课程内容视图' }).getByRole('button', { name: '章节' }).click();
  }
  await expect(page.getByRole('region', { name: '课程章节' })).toBeVisible();
  const video = page.getByLabel('课程视频', { exact: true });
  await expect.poll(() => video.evaluate(element => element.readyState)).toBeGreaterThan(0);
  await nav.getByRole('button', { name: wide ? '个人笔记' : '返回 个人笔记', exact: true }).click();
  await expect(page.getByText(/播放位置$/, { exact: false })).toBeVisible();
  await textarea.fill('记住当前播放位置');
  await page.getByRole('button', { name: '保存笔记' }).click();
  await page.getByRole('button', { name: /^跳到播放位置/ }).click();
  await expect(video).toBeVisible();
  await page.getByRole('button', { name: '返回当前学习任务' }).click();
  await expect(page.getByRole('button', { name: /^跳到播放位置/ })).toBeFocused();

  const key = `lecturelens.courseNotes.v1:${userId}:${encodeURIComponent(taskId)}`;
  await page.evaluate(storageKey => localStorage.setItem(storageKey, '{"unexpected":true}'), key);
  await page.reload();
  await expect(page.getByRole('alert').filter({ hasText: '无法读取此课程的本地笔记' })).toBeVisible();
  await expect(page.getByText('记住当前播放位置', { exact: true })).toHaveCount(0);
  await screenshot(page, 'note-storage-error');
  await record(page, 'note-network-counts', counts);
  expect(counts.httpErrors).toEqual({});
});

test('uses an empty account, recovers a library read failure, and shows upload receipts', async ({ page }) => {
  const { base, taskId } = await openMock(page, { newAccount: true });
  const counts = monitor(page);
  const taskList = url => url.pathname === '/api/tasks' && url.searchParams.has('page');
  let fail = true;
  let release;
  const firstRead = new Promise(resolve => { release = resolve; });
  await page.route(taskList, async route => {
    if (!fail) return route.continue();
    fail = false;
    await firstRead;
    return route.fulfill({ status: 503, json: { code: 'SERVICE_UNAVAILABLE' } });
  });
  try {
    await page.goto(`${base}/tasks`);
    const loading = page.getByRole('status').filter({ hasText: '正在读取课程' });
    await expect(loading).toBeVisible();
    await screenshot(page, 'library-loading');
  } finally {
    release();
  }
  await expect(page.getByRole('alert')).toBeVisible();
  await screenshot(page, 'library-recoverable-error');
  await page.getByRole('button', { name: '刷新', exact: true }).click();
  await expect(page.getByText('还没有课程视频', { exact: true })).toBeVisible();
  await expect(page.getByRole('main').getByRole('link', { name: '上传视频', exact: true })).toHaveCount(1);
  await expect(page.getByRole('main').getByRole('button', { name: '批量管理' })).toHaveCount(0);
  await screenshot(page, 'library-empty');

  await page.goto(`${base}/tasks/${taskId}?view=notes&layout=continuous`);
  await expect(page.getByText('课程不可用或权限已变化')).toBeVisible();
  await expect(page.getByRole('textbox', { name: '记录你的理解' })).toHaveCount(0);
  expect(counts.httpErrors).toEqual({ '503 GET /api/tasks': 1, '404 GET /api/tasks/{course}': 1 });

  await page.goto(`${base}/upload`);
  await expectFit(page);
  await screenshot(page, 'upload-empty');
  const input = page.locator('input[type=file]');
  await input.setInputFiles({ name: 'invalid.txt', mimeType: 'text/plain', buffer: Buffer.from('synthetic invalid file') });
  await expect(page.getByRole('alert')).toContainText('仅支持');
  await screenshot(page, 'upload-invalid');
  await input.setInputFiles(new URL('../../../fixtures/demo/binary-search-demo.mp4', import.meta.url).pathname);
  await expect(page.getByRole('status').filter({ hasText: '文件类型已通过检查' })).toBeVisible();
  await screenshot(page, 'upload-picked');
  await page.getByRole('button', { name: '开始上传', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: '服务器已接收视频' })).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole('progressbar', { name: '视频上传进度' })).toHaveAttribute('aria-valuenow', '100');
  const previewHelp = page.locator('.preview-note > summary');
  await expect(previewHelp.getByRole('button')).toHaveCount(0);
  await previewHelp.press('Enter');
  await expect(page.getByText(/播放刚上传的原始视频/)).toBeVisible();
  await expect.poll(() => page.locator('video').evaluate(element => element.readyState)).toBeGreaterThan(0);
  await expectFit(page);
  const processCourse = page.getByRole('button', { name: '开始处理', exact: true });
  if (page.viewportSize().width >= 1024) await expect(processCourse).toBeInViewport();
  await screenshot(page, 'upload-received');

  await processCourse.click();
  await expect(page).toHaveURL(/\/tasks\/[^/?]+/);
  await screenshot(page, 'course-processing');
  await expect(page.getByText('材料已就绪', { exact: true })).toBeVisible({ timeout: 90_000 });
  await page.getByRole('link', { name: '返回我的课程' }).click();
  await expect(page.getByRole('heading', { name: 'binary-search-demo' })).toBeVisible();
  await expectFit(page);
  await screenshot(page, 'library-course');
  await record(page, 'upload-network-counts', counts);
});

test('keeps long course lists navigable across pages and batch mode', async ({ page }) => {
  const { base } = await openMock(page);
  await page.route(url => url.pathname === '/api/tasks' && url.searchParams.has('page'), route => {
    const current = Number(new URL(route.request().url()).searchParams.get('page'));
    const items = Array.from({ length: current === 1 ? 100 : 2 }, (_, index) => ({
      taskId: `fixture-course-${current}-${index}`,
      courseName: current === 1 && index === 0 ? '长名称'.repeat(50) : `测试课程 ${current}-${index + 1}`,
      status: 'SUCCEEDED',
      targetLanguage: 'zh-CN',
      currentStage: 'DONE',
    }));
    return route.fulfill({ json: { code: '0', data: { items, page: current, pageSize: 100, total: 102 } } });
  });
  await page.goto(`${base}/tasks`);
  await expect(page.getByRole('article')).toHaveCount(100);
  await expectFit(page);
  await screenshot(page, 'library-long-list');
  await page.getByRole('button', { name: '下一页' }).press('Enter');
  await expect(page.getByRole('article')).toHaveCount(2);
  await expect(page.getByRole('heading', { name: '测试课程 2-2' })).toBeVisible();

  await page.getByRole('button', { name: '批量管理' }).click();
  await page.getByRole('button', { name: '全选当前列表' }).click();
  await expect(page.getByText('已选择 2 项')).toBeVisible();
  await page.getByRole('button', { name: '上一页' }).click();
  await expect(page.getByRole('article')).toHaveCount(100);
  await expect(page.getByText('已选择 0 项')).toBeVisible();
  await expectFit(page);
});
