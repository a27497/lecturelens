// Capture the README walkthrough and screenshots from a running Round 3 Mock instance.
// Setup: npm ci --prefix frontend && cd frontend && npx playwright install chromium
// Run from the repository root:
//   node scripts/demo/record-round3-showcase.mjs --port <printed port> --output .demo/showcase
// FFmpeg converts the local Chromium recording to a web-playable MP4.

import { spawnSync } from 'node:child_process';
import { mkdir, mkdtemp, rm } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { join, resolve } from 'node:path';
import { parseArgs } from 'node:util';

const require = createRequire(new URL('../../frontend/package.json', import.meta.url));
const { chromium, expect } = require('@playwright/test');
const { values } = parseArgs({
  options: { port: { type: 'string' }, output: { type: 'string', default: '.demo/showcase' } },
});
if (!/^\d+$/.test(values.port ?? '') || Number(values.port) < 1 || Number(values.port) > 65535) {
  throw new Error('Pass the local Round 3 port with --port.');
}
const origin = `http://127.0.0.1:${values.port}`;
const output = resolve(values.output);
await mkdir(output, { recursive: true });
const temporary = await mkdtemp(join(output, 'capture-'));
const desktopSize = { width: 1440, height: 900 };
const question = '为什么 mid 要向下取整？';
const browser = await chromium.launch();
const external = new Set();
const pageErrors = [];

async function openPage(options) {
  const context = await browser.newContext({
    locale: 'zh-CN', serviceWorkers: 'block', ...options,
  });
  // No external browser traffic is required for the deterministic lesson.
  await context.route(url => /^https?:$/.test(url.protocol) && url.origin !== origin, route => {
    external.add(new URL(route.request().url()).hostname);
    return route.abort();
  });
  const page = await context.newPage();
  page.on('pageerror', error => pageErrors.push(error.name));
  page.setDefaultTimeout(20_000);
  return page;
}

const enter = page => page.getByRole('button', { name: /继续学习 01:04/ });
const timestamp = page => page.locator('video').evaluate(video => Math.round(video.currentTime * 1000));
const navigation = page => page.getByRole('navigation', { name: '课程学习导航' });
const sourceCard = page => page.getByRole('region', { name: '课程出处', exact: true });

async function openLibrary(page) {
  await page.goto(origin + '/tasks', { waitUntil: 'domcontentloaded' });
  await enter(page).waitFor({ timeout: 90_000 });
}

async function openLesson(page) {
  await enter(page).click();
  await expect.poll(() => timestamp(page)).toBe(64_000);
  await expect.poll(() => page.locator('video').evaluate(video => video.readyState)).toBeGreaterThanOrEqual(2);
}

async function showStep(page, title, caption) {
  await page.evaluate(([title, caption]) => {
    let bar = document.querySelector('#showcase-caption');
    if (!bar) {
      bar = document.createElement('aside');
      bar.id = 'showcase-caption';
      bar.style.cssText = 'position:fixed;inset:auto 0 0;z-index:99999;display:flex;'
        + 'align-items:center;gap:20px;padding:13px 26px;color:#fff;background:#172823;'
        + 'font:500 17px/1.45 system-ui,sans-serif;pointer-events:none';
      const label = document.createElement('strong');
      label.textContent = 'DETERMINISTIC MOCK';
      label.style.cssText = 'font-size:12px;letter-spacing:.08em;color:#c3ebd2;white-space:nowrap';
      bar.append(label, document.createElement('span'));
      document.body.append(bar);
    }
    bar.lastElementChild.textContent = `${title}  ·  ${caption}`;
  }, [title, caption]);
}

async function askTutor(page) {
  await page.getByRole('button', { name: '新对话', exact: true }).click();
  const editor = page.getByRole('textbox', { name: '就本课提问' });
  await editor.fill(question);
  return editor;
}

async function submitQuestion(page, editor) {
  await editor.press('Enter');
  const answer = page.locator('.tutor--lesson .messages > li').last();
  await expect(answer).toContainText('偶数个候选时取左边的中点');
  return answer;
}

async function openSource(page, answer) {
  await answer.getByRole('button', { name: '课程出处 00:34', exact: true }).click();
  const card = sourceCard(page);
  await card.locator('summary').click();
  await expect(card.locator('blockquote')).toContainText('rounding the distance down');
  return card;
}

function ffmpeg(args) {
  const result = spawnSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', ...args], {
    stdio: 'inherit',
  });
  if (result.error || result.status !== 0) throw result.error ?? new Error('FFmpeg conversion failed.');
}

async function capture(page, name) {
  const png = join(temporary, name + '.png');
  await page.screenshot({
    path: png,
    animations: 'disabled',
    style: '#showcase-caption { visibility: hidden !important; }',
  });
  ffmpeg(['-i', png, '-c:v', 'libwebp', '-lossless', '1', join(output, name + '.webp')]);
}

try {
  const recordingStartedAt = performance.now();
  const desktop = await openPage({
    viewport: desktopSize, recordVideo: { dir: temporary, size: desktopSize },
  });
  const recording = desktop.video();
  await openLibrary(desktop);
  await showStep(desktop, 'Open the course', 'Resume the synthetic binary search lesson from the course library.');
  // Cut the variable visitor provisioning time before the course library is visible.
  const trimSeconds = (performance.now() - recordingStartedAt) / 1000;
  // Reading time for the on-screen captions and product content.
  await desktop.waitForTimeout(5000);

  await openLesson(desktop);
  await showStep(desktop, 'Watch the lecture', 'The transcript follows the player. This section walks through a search for 34.');
  await desktop.getByRole('button', { name: '播放', exact: true }).click();
  await desktop.waitForTimeout(8000);
  await desktop.getByRole('button', { name: '暂停', exact: true }).click();
  expect(await timestamp(desktop)).toBeGreaterThan(64_000);

  await showStep(desktop, 'Ask Tutor', 'Why does the midpoint calculation round down?');
  const editor = await askTutor(desktop);
  await desktop.waitForTimeout(5000);
  const answer = await submitQuestion(desktop, editor);
  await showStep(desktop, 'Read the answer', 'The fixed reply explains why rounding down picks the left middle index.');
  await desktop.waitForTimeout(8000);

  const card = await openSource(desktop, answer);
  const replay = card.getByRole('button', { name: '回看 00:34', exact: true });
  await expect(replay).toBeInViewport();
  await showStep(desktop, 'Open the source', 'The 00:34 citation opens the original English excerpt.');
  await desktop.waitForTimeout(9000);
  expect(await timestamp(desktop)).toBeGreaterThan(64_000);
  await replay.click();
  await expect.poll(() => timestamp(desktop)).toBe(34_000);
  await showStep(desktop, 'Replay the cited moment', 'The player returns to 00:34 and the transcript highlights that segment.');
  await desktop.getByRole('button', { name: '播放', exact: true }).click();
  await desktop.waitForTimeout(6500);
  await desktop.getByRole('button', { name: '暂停', exact: true }).click();
  await desktop.evaluate(() => window.scrollTo(0, 0));
  await capture(desktop, 'round3-workspace-desktop');

  await navigation(desktop).getByRole('button', { name: '练习', exact: true }).click();
  await expect(desktop.getByRole('heading', { name: /把例题数组打乱后/ })).toBeVisible();
  await showStep(desktop, 'Try an exercise', 'If the array is unsorted, can you still discard the left half?');
  await desktop.waitForTimeout(6000);
  await desktop.getByRole('radio', { name: /左边仍可能藏着 34/ }).check();
  await desktop.waitForTimeout(3000);
  await desktop.getByRole('button', { name: '提交答案', exact: true }).click();
  const result = desktop.getByRole('article', { name: '选择题判分结果' });
  await expect(result).toContainText('数组打乱后，34 可能位于任意一侧');
  await result.scrollIntoViewIfNeeded();
  await showStep(desktop, 'Check the result', 'The fixed answer key gives the result and points back to the lecture evidence.');
  await capture(desktop, 'round3-practice-desktop');
  await desktop.waitForTimeout(8500);
  await desktop.context().close();

  const mobile = await openPage({
    viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true,
    deviceScaleFactor: 1,
  });
  await openLibrary(mobile);
  await openLesson(mobile);
  await navigation(mobile).getByRole('button', { name: '助手', exact: true }).click();
  const mobileAnswer = await submitQuestion(mobile, await askTutor(mobile));
  const mobileSource = await openSource(mobile, mobileAnswer);
  await mobileSource.evaluate(node => window.scrollBy(0, node.getBoundingClientRect().top - 319));
  await expect(mobileSource.getByRole('button', { name: '回看 00:34', exact: true })).toBeInViewport();
  await expect(mobile.locator('video')).toBeInViewport();
  expect(await mobile.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await capture(mobile, 'round3-source-mobile');
  await mobile.context().close();

  expect([...external], 'external browser requests').toEqual([]);
  expect(pageErrors, 'uncaught browser errors').toEqual([]);
  ffmpeg(['-ss', trimSeconds.toFixed(3), '-i', await recording.path(), '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
    '-preset', 'slow', '-crf', '23', '-movflags', '+faststart',
    join(output, 'lecturelens-round3-mock.mp4')]);
} finally {
  await browser.close();
  await rm(temporary, { recursive: true, force: true });
}
