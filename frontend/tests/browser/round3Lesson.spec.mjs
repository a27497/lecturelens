import { expect, test } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const port = process.env.LECTURELENS_ROUND3_PORT;
const evidence = process.env.LECTURELENS_SCREENSHOT_DIR;
const origin = `http://127.0.0.1:${port}`;
test.skip(!port, 'Requires the isolated Round 3 candidate');
test.skip(({ viewport }) => viewport?.width === 768, 'Round 3 review viewports are 1440 and 390');

const clock = page => page.locator('video').evaluate(video => Math.round(video.currentTime * 1000));
const send = page => page.getByRole('button', { name: '发送', exact: true });
const nav = page => page.getByRole('navigation', { name: '课程学习导航' });
const choose = (page, label) => nav(page).getByRole('button', { name: label, exact: true }).click();

async function capture(page, name) {
  if (evidence) {
    await mkdir(evidence, { recursive: true });
    await page.screenshot({ path: join(evidence, `${name}.png`), animations: 'disabled' });
  }
}

function trace(page) {
  let sample;
  page.on('request', request => {
    if (!sample) return;
    const url = new URL(request.url());
    if (url.origin !== origin || !url.pathname.startsWith('/api/')) return;
    const path = url.pathname.replace(/\/tasks\/[^/]+/, '/tasks/{course}')
      .replace(/\/tutor\/sessions\/[^/]+/, '/tutor/sessions/{session}')
      .replace(/\/media\/uploads\/[^/]+/, '/media/uploads/{upload}')
      .replace(/\/practice\/[^/]+/, '/practice/{artifact}');
    sample.set(request, { path, method: request.method(), startedMs: Date.now() - sample.started,
      ...(path.endsWith('/study/command') ? { operation: request.postDataJSON()?.operation } : {}) });
  });
  page.on('response', response => {
    const row = sample?.get(response.request());
    if (row) Object.assign(row, { status: response.status(), durationMs: Date.now() - sample.started - row.startedMs });
  });
  return { start() { sample = new Map(); sample.started = Date.now(); },
    stop() { const rows = [...sample.values()]; sample = null; return rows; } };
}

test('opens at 01:04 and works through authorized learning actions', async ({ page, isMobile }) => {
  const formFactor = isMobile ? 'mobile' : 'desktop';
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });

  const postActions = [];
  const pageErrors = [];
  const externalRequests = [];
  page.on('pageerror', error => pageErrors.push(error.name));
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.protocol.startsWith('http') && url.origin !== origin) externalRequests.push(url.hostname);
    if (request.method() === 'POST' && /\/(study\/command|tutor\/sessions)(\/|$)/.test(url.pathname)) {
      postActions.push(url.pathname.endsWith('/study/command') ? request.postDataJSON()?.operation : 'TUTOR');
    }
  });
  const flight = trace(page);
  const measurements = [];
  for (const pass of ['cold', 'repeat']) {
    await page.goto(origin + '/tasks');
    const open = page.getByRole('button', { name: /继续学习 01:04/ });
    await expect(open).toBeVisible();
    await expect(page.getByText('已学 42%')).toBeVisible();
    if (pass === 'cold' && !isMobile) await capture(page, 'library-desktop');

    flight.start();
    const start = Date.now();
    await open.click();
    const [subtitleMs, playerMs, tutorMs] = await Promise.all([
      page.locator('.lesson-transcript article[data-current=true]').getByText(/21 及其左边的数都可以排除/).waitFor().then(() => Date.now() - start),
      page.waitForFunction(() => {
        const video = document.querySelector('video');
        return video?.readyState >= 2 && video.videoWidth > 0 && video.currentTime === 64;
      }).then(() => Date.now() - start),
      isMobile ? null : page.getByText('比较过的中点也要移出区间').waitFor().then(() => Date.now() - start),
    ]);
    expect(subtitleMs).toBeLessThan(3000);
    expect(playerMs).toBeLessThan(3000);
    await expect(page.getByRole('button', { name: '视频字幕', exact: true })).toBeEnabled();
    const network = flight.stop();
    expect(network.filter(item => item.path.endsWith('/study/command'))).toHaveLength(0);
    expect(network.filter(item => item.path.endsWith('/results'))).toHaveLength(1);
    expect(network.filter(item => item.path === '/api/tasks/{course}')).toHaveLength(1);
    measurements.push({ pass, subtitleMs, playerMs, tutorMs, count: network.length, network });
    if (pass === 'cold') await capture(page, formFactor);
  }
  if (evidence) await writeFile(join(evidence, `load-${formFactor}.json`), JSON.stringify(measurements, null, 2) + '\n');
  expect(postActions).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(isMobile ? 390 : 1440);

  await test.step('play, pause, change caption language and seek by chapter', async () => {
    await page.getByRole('button', { name: '视频字幕', exact: true }).click();
    await expect.poll(() => page.locator('video').evaluate(video => video.textTracks[0]?.mode)).toBe('showing');
    await page.getByRole('button', { name: '视频字幕', exact: true }).click();
    await page.getByRole('button', { name: '播放', exact: true }).click();
    await expect.poll(() => clock(page)).toBeGreaterThan(64000);
    await page.getByRole('button', { name: '暂停', exact: true }).click();
    await page.getByRole('button', { name: '双语', exact: true }).click();
    await expect(page.locator('.lesson-transcript article[data-current=true]')).toContainText(/middle/i);
    await page.getByRole('button', { name: '中文', exact: true }).click();
    if (isMobile) await page.getByRole('button', { name: /查看全部章节/ }).click();
    await page.getByRole('button', { name: /为什么必须有序/ }).click();
    await expect.poll(() => clock(page)).toBe(0);
    await page.getByRole('button', { name: /走一遍：找到 34/ }).click();
    await expect.poll(() => clock(page)).toBe(64000);
  });

  await test.step('verify a source in the answer before replaying it', async () => {
    if (isMobile) {
      await page.getByRole('button', { name: /问这一段/ }).click();
      await expect(page.getByRole('textbox', { name: '就本课提问' })).toHaveValue(/01:04/);
      await expect(page.getByRole('button', { name: '播放', exact: true })).toBeVisible();
    }
    const source = page.getByRole('region', { name: '课程出处', exact: true });
    const first = page.getByRole('button', { name: '课程出处 00:00', exact: true }).first();
    await first.click();
    const replay = source.getByRole('button', { name: '回看 00:00', exact: true });
    await expect(replay).toBeEnabled();
    expect(await clock(page)).toBe(64000);
    await replay.click();
    await expect.poll(() => clock(page)).toBe(0);
    await page.getByRole('button', { name: '课程出处 01:04', exact: true }).first().click();
    await expect(source.getByRole('button', { name: '回看 01:04', exact: true })).toBeEnabled();
    await source.getByRole('button', { name: '回看 01:04', exact: true }).click();
    await expect.poll(() => clock(page)).toBe(64000);
    await source.locator('summary').click();
    await expect(source.locator('blockquote')).toBeVisible();
    if (isMobile) {
      await source.evaluate(card => window.scrollBy(0, card.getBoundingClientRect().top - 319));
      const playerTop = await page.locator('video').evaluate(video => video.getBoundingClientRect().top);
      expect(playerTop).toBeGreaterThanOrEqual(49);
      await expect(source.getByRole('button', { name: '回看 01:04', exact: true })).toBeInViewport();
    }
    await capture(page, `source-${formFactor}`);
    await page.getByRole('button', { name: '课程出处 01:04', exact: true }).first().click();
  });

  if (!isMobile) {
    await test.step('prepare a recommended follow-up without making a request', async () => {
      const prompt = '如果目标比中点小，应该移动哪个边界？';
      const before = postActions.length;
      await page.getByRole('button', { name: prompt, exact: true }).click();
      await expect(page.getByRole('textbox', { name: '就本课提问' })).toHaveValue(prompt);
      await expect(send(page)).toBeEnabled();
      expect(postActions.length).toBe(before);
      await capture(page, 'followups-desktop');
      await page.getByRole('button', { name: '新对话', exact: true }).click();
      await expect(page.getByText(/可以问一个概念/)).toBeVisible();
      expect(postActions.length).toBe(before);
    });
  }

  await test.step('save a local note and submit a real practice attempt', async () => {
    await choose(page, '笔记');
    await expect(page.getByText(/中点也要划掉/)).toBeVisible();
    const text = '闭区间边界更新后，中点已经排除。';
    await page.getByRole('textbox', { name: '记录你的理解' }).fill(text);
    await page.getByRole('button', { name: '保存笔记', exact: true }).click();
    await expect(page.getByText(text, { exact: true })).toBeVisible();
    await choose(page, '练习');
    await page.getByRole('button', { name: '下一题', exact: true }).click();
    await expect(page.getByRole('heading', { name: /在 \[2, 7, 11, 18, 29\]/ })).toBeVisible();
    const choices = page.getByRole('radio');
    const selectedBefore = await choices.nth(0).isChecked();
    await choices.nth(selectedBefore ? 1 : 0).check();
    await expect(page.getByRole('button', { name: '提交答案', exact: true })).toBeEnabled();
    if (isMobile) {
      await page.evaluate(() => window.scrollTo(0, 0));
      await capture(page, 'practice-mobile');
      await page.getByRole('button', { name: '提交答案', exact: true }).click();
      const feedback = page.getByRole('article', { name: '选择题判分结果' });
      await expect(feedback.getByText(/把 low 移到 3 后，18 和 29 都还是候选/)).toBeVisible();
      expect(postActions).toContain('SAVE_ATTEMPT');
      await page.evaluate(() => window.scrollTo(0, 0));
      await capture(page, 'practice-feedback-mobile');
      const prior = await choices.nth(selectedBefore ? 1 : 0).isChecked();
      await page.reload();
      await page.getByRole('button', { name: '下一题', exact: true }).click();
      expect(await choices.nth(selectedBefore ? 1 : 0).isChecked()).toBe(prior);
      await expect(feedback).toBeVisible();
    }
  });

  expect(pageErrors).toEqual([]);
  expect(externalRequests).toEqual([]);
});
