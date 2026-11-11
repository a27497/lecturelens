// Decoded synthetic media and real Vue; business responses are deterministic HTTP fixtures.
import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { parseArgs } from 'node:util';
import { resolve } from 'node:path';
import { createB1Fixture } from './b1Fixture.mjs';

const { values: args } = parseArgs({ options: { dist: { type: 'string', default: 'dist' }, media: { type: 'string' }, chromium: { type: 'string' }, output: { type: 'string' } } });
if (!args.media || !args.output) throw Error('Require approved --media and separate --output');
const output = resolve(args.output); await mkdir(output, { recursive: true });
const fixture = await createB1Fixture(args), cases = [];
const browser = await chromium.launch({ executablePath: args.chromium, headless: true, chromiumSandbox: true }).catch(async e => { await fixture.close(); throw e; });
try {
  for (const width of [1440, 390]) {
    fixture.reset();
    const context = await browser.newContext({ viewport: { width, height: width === 1440 ? 900 : 844 } });
    await context.addInitScript(() => localStorage.setItem('courselingo.accessToken', 'offline-fixture-token'));
    const page = await context.newPage(), errors = [], external = [], checks = [];
    await context.route('**/*', route => {
      if (new URL(route.request().url()).origin === fixture.origin) return route.continue();
      external.push(route.request().url()); return route.abort();
    });
    page.on('pageerror', e => errors.push(String(e)));
    const nav = name => page.getByRole('navigation', { name: '课程内容导航' }).getByRole('button', { name, exact: true });
    const answer = page.locator('.practice-question.is-current .practice-answer textarea');
    const source = () => page.locator('.practice-question.is-current .practice-feedback').getByRole('button', { name: '回看这段课程证据', exact: true }).first();
    const video = page.locator('video');
    const play = async () => {
      await expect(video).toBeVisible();
      await expect.poll(() => video.evaluate(v => v.readyState)).toBeGreaterThan(1);
      await video.evaluate(v => v.play());
      await expect.poll(() => video.evaluate(v => !v.paused)).toBe(true);
    };
    const capture = async name => {
      await page.screenshot({ path: `${output}/${width}-${name}.png` });
      await writeFile(`${output}/${width}-${name}.json`, JSON.stringify(await page.evaluate(() => {
        const v = document.querySelector('video');
        const focus = document.activeElement;
        return { paused: v?.paused, time: v?.currentTime, playerVisible: !!v?.getClientRects().length,
          focus: { tag: focus?.tagName, label: focus?.getAttribute('aria-label'), text: focus?.textContent?.trim().slice(0, 120) }, scrollY, width: innerWidth };
      }), null, 2));
    };
    const check = async (name, fn) => { console.log('START', width, name); await fn(); checks.push(name); console.log('PASS', width, name); };
    try {
      await page.goto(fixture.origin + '/tasks/synthetic?view=agent');
      await expect(answer).toBeVisible(); await answer.fill('saved v1');
      await page.locator('.practice-question.is-current').getByRole('button', { name: '保存作答', exact: true }).click();
      await page.locator('.practice-question.is-current .practice-feedback').getByRole('button', { name: '获取证据反馈', exact: true }).click();
      await expect(page.getByRole('heading', { name: '第 1 版作答的证据反馈', exact: true })).toBeVisible();
      await answer.fill('same page unsaved v2');
      const node = await video.elementHandle(), input = await answer.elementHandle();
      const generation = () => fixture.requests.filter(r => ['START', 'START_FEEDBACK', 'CREATE_SESSION'].includes(r.operation)).length;
      const before = generation();
      await check('playing citation review pauses every hidden mobile player; desktop keeps playing', async () => {
        if (width === 390) await nav('课程材料').click();
        await play();
        if (width === 390) await nav('解释与练习').click();
        await source().click();
        await expect(page.locator('.timeline-row[data-reference=true]')).toHaveCount(1);
        await capture('citation-before-assert');
        if (width === 390) { await expect(video).toBeHidden(); await expect.poll(() => video.evaluate(v => v.paused)).toBe(true); }
        else { await expect(video).toBeVisible(); await expect.poll(() => video.evaluate(v => v.paused)).toBe(false); }
      });
      await check('return, material and breakpoint transitions retain nodes, draft and position without autoplay', async () => {
        if (width === 1440) await page.setViewportSize({ width: 390, height: 844 });
        await expect.poll(() => video.evaluate(v => v.paused)).toBe(true);
        const time = await video.evaluate(v => v.currentTime);
        await page.getByRole('button', { name: '返回当前学习任务', exact: true }).click();
        await expect(answer).toHaveValue('same page unsaved v2');
        await nav('课程材料').click(); await expect(video).toBeVisible();
        expect(await video.evaluate(v => v.paused)).toBe(true);
        expect(Math.abs(await video.evaluate(v => v.currentTime) - time)).toBeLessThan(.3);
        await play(); await nav('解释与练习').click();
        await expect.poll(() => video.evaluate(v => v.paused)).toBe(true);
        await page.setViewportSize({ width: 1440, height: 900 });
        await expect(video).toBeVisible(); expect(await video.evaluate(v => v.paused)).toBe(true);
        expect(await video.evaluate((v, old) => v === old, node)).toBe(true);
        expect(await answer.evaluate((v, old) => v === old, input)).toBe(true);
        expect(generation()).toBe(before); await capture('returned');
      });
      await check('both citation return buttons restore the same source trigger and scroll', async () => {
        const positions = [];
        for (const label of ['返回当前学习任务', '返回本题作答']) {
          await source().click(); await expect(page.locator('.timeline-row[data-reference=true]')).toHaveCount(1);
          await page.getByRole('button', { name: label, exact: true }).click();
          await expect(source()).toBeFocused();
          positions.push(await page.evaluate(() => scrollY));
          await expect(answer).toHaveValue('same page unsaved v2');
        }
        expect(Math.abs(positions[0] - positions[1])).toBeLessThan(2);
        expect(generation()).toBe(before);
      });
      await check('classic visible playback, stale revision and course loss retain existing fences', async () => {
        await page.locator('.course-controls > summary').click();
        await page.getByRole('button', { name: '经典布局', exact: true }).click();
        await play(); await source().click();
        await expect(video).toBeVisible(); expect(await video.evaluate(v => v.paused)).toBe(false);
        await page.getByRole('button', { name: '返回当前学习任务', exact: true }).click();
        await page.getByRole('button', { name: '连续工作区', exact: true }).click();
        await page.setViewportSize({ width: 390, height: 844 });
        await expect.poll(() => video.evaluate(v => v.paused)).toBe(true);
        await context.request.post(fixture.origin + '/__fixture', { data: { revision: 2 } });
        await source().click(); await expect(page.locator('.evidence-navigation-error')).toContainText('课程资料已更新');
        await expect(page.locator('.timeline-row[data-reference=true]')).toHaveCount(0);
        expect(await video.evaluate(v => v.paused)).toBe(true);
        await context.request.post(fixture.origin + '/__fixture', { data: { denied: true } });
        await source().click(); await expect(page.locator('.course-unavailable')).toBeVisible();
        await expect(video).toHaveCount(0);
        expect(await node.evaluate(v => v.paused)).toBe(true);
        expect(generation()).toBe(before); await capture('unavailable');
      });
      expect(errors).toEqual([]); expect(external).toEqual([]); expect(fixture.errors).toEqual([]);
      cases.push({ width, status: 'PASS', checks, errors, external, requests: [...fixture.requests] });
    } catch (e) {
      await capture('failure').catch(() => {});
      cases.push({ width, status: 'FAIL', checks, error: String(e), errors, external, requests: [...fixture.requests] });
      console.error(String(e));
    } finally { await context.close(); }
  }
} finally {
  await browser.close(); await fixture.close();
  await writeFile(output + '/results.json', JSON.stringify({ chromiumSandbox: true, api: 'deterministic HTTP fixture', physicalProviderCalls: 0, cases }, null, 2));
}
if (cases.some(c => c.status !== 'PASS')) process.exitCode = 1;
