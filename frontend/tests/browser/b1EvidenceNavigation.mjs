// Real Vue regression with deterministic HTTP fixtures; no Java, database or provider connection.
import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { parseArgs } from 'node:util';
import { resolve } from 'node:path';
import { createB1Fixture } from './b1Fixture.mjs';
const { values: args } = parseArgs({ options: { dist: { type: 'string', default: 'dist' }, media: { type: 'string' }, chromium: { type: 'string' }, output: { type: 'string' } } });
if (!args.media || !args.output)
    throw Error('Require approved --media and separate --output');
const output = resolve(args.output);
await mkdir(output, { recursive: true });
const fixture = await createB1Fixture(args), cases = [];
const browser = await chromium.launch({ executablePath: args.chromium, headless: true, chromiumSandbox: true }).catch(async (e) => { await fixture.close(); throw e; });
try {
    for (const width of [1440, 390])
        for (const entry of ['agent', 'content']) {
            fixture.reset();
            // A phone material tab intentionally hides task links. Start the real click on desktop,
            // then cross the breakpoint while its version check is pending; no hidden/forced click.
            const triggerWidth = width === 390 && entry === 'content' ? 1440 : width;
            const context = await browser.newContext({ viewport: { width: triggerWidth, height: triggerWidth === 1440 ? 900 : 844 } });
            await context.addInitScript(() => localStorage.setItem('courselingo.accessToken', 'offline-fixture-token'));
            const page = await context.newPage(), checks = [], errors = [], external = [];
            let holdIndex = false, releaseIndex, observedIndex;
            page.on('pageerror', e => errors.push(String(e)));
            await context.route('**/*', async (route) => {
                if (new URL(route.request().url()).origin !== fixture.origin) {
                    external.push(route.request().url());
                    return route.abort();
                }
                if (holdIndex && route.request().url().includes('/evidence/index-status')) {
                    holdIndex = false;
                    observedIndex?.();
                    await new Promise(r => releaseIndex = r);
                }
                await route.continue();
            });
            const nav = name => page.getByRole('navigation', { name: '课程内容导航' }).getByRole('button', { name, exact: true });
            const answer = () => page.locator('.practice-question.is-current .practice-answer textarea');
            const source = () => page.locator('.practice-question.is-current .practice-feedback').getByRole('button', { name: '回看这段课程证据', exact: true });
            const marker = () => page.locator('.timeline-row[data-reference=true]');
            const generation = () => fixture.requests.filter(r => ['CREATE_SESSION', 'START', 'START_FEEDBACK'].includes(r.operation)).length;
            const change = data => context.request.post(fixture.origin + '/__fixture', { data });
            const capture = async (name) => { await page.evaluate(async () => { await Promise.race([Promise.allSettled(document.getAnimations().filter(a => a.effect?.getComputedTiming().iterations !== Infinity).map(a => a.finished)), new Promise(r => setTimeout(r, 750))]); }); await page.screenshot({ path: `${output}/${width}-${entry}-${name}.png` }); await writeFile(`${output}/${width}-${entry}-${name}.aria.txt`, await page.locator('body').ariaSnapshot()); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true); };
            const check = async (name, run) => { console.log('START', width, entry, name); await run(); checks.push(name); console.log('PASS', width, entry, name); };
            const review = async (resize = false) => {
                if (resize) {
                    const waiting = new Promise(r => observedIndex = r);
                    holdIndex = true;
                    await source().click();
                    await waiting;
                    await page.setViewportSize({ width, height: 844 });
                    releaseIndex();
                }
                else
                    await source().click();
                await expect(marker()).toHaveCount(1);
            };
            try {
                await page.goto(fixture.origin + `/tasks/synthetic?view=${entry}`);
                await expect(answer()).toBeVisible();
                await answer().fill('已保存的合成v1');
                await page.locator('.practice-question.is-current').getByRole('button', { name: '保存作答', exact: true }).click();
                await expect(page.locator('.answer-actions').first()).toContainText('已保存第 1 版');
                await page.locator('.practice-question.is-current .practice-feedback').getByRole('button', { name: '获取证据反馈', exact: true }).click();
                await expect(page.getByRole('heading', { name: '第 1 版作答的证据反馈', exact: true })).toBeVisible();
                await answer().fill('同页未保存的修订');
                const input = await answer().elementHandle(), reader = await page.locator('.content-panel').elementHandle(), video = await page.locator('video').elementHandle();
                const before = generation();
                await check('verified reference and task context appear from the selected entry', async () => {
                    await review(triggerWidth !== width);
                    await expect(page.locator('.evidence-reading__return')).toContainText('正在核对第 1 题');
                    await expect(page.getByRole('button', { name: '返回当前学习任务', exact: true })).toBeVisible();
                    if (width === 390)
                        await expect(page.locator('.mobile-workspace-nav-target')).toBeHidden();
                    await capture('verified');
                });
                await check('continued playback preserves the citation; return keeps draft and single DOM instances', async () => {
                    const cited = await marker().getAttribute('data-segment');
                    await page.locator('video').evaluate(async (v) => { await v.play(); });
                    await expect.poll(() => page.locator('video').evaluate(v => v.currentTime)).toBeGreaterThan(12.15);
                    expect(await marker().getAttribute('data-segment')).toBe(cited);
                    await page.locator('video').evaluate(v => v.pause());
                    await page.getByRole('button', { name: '返回当前学习任务', exact: true }).click();
                    await expect(answer()).toHaveValue('同页未保存的修订');
                    await expect(page).toHaveURL(/view=agent/);
                    await expect(marker()).toHaveCount(0);
                    expect(await answer().evaluate((el, old) => el === old, input)).toBe(true);
                    expect(await page.locator('.content-panel').evaluate((el, old) => el === old, reader)).toBe(true);
                    expect(await page.locator('video').evaluate((el, old) => el === old, video)).toBe(true);
                    expect(generation()).toBe(before);
                    if (entry === 'content')
                        await expect(answer()).toBeFocused();
                    await capture('returned');
                });
                await check('ordinary timeline positioning clears the verified marker without starting inference', async () => {
                    await review();
                    await page.locator('.timeline-row[data-segment="3"] button').click();
                    await expect(marker()).toHaveCount(0);
                    expect(generation()).toBe(before);
                    await page.getByRole('button', { name: '返回当前学习任务', exact: true }).click();
                    await expect(answer()).toHaveValue('同页未保存的修订');
                });
                await check('v2 save leaves feedback on immutable v1', async () => {
                    await page.locator('.practice-question.is-current').getByRole('button', { name: '保存作答', exact: true }).click();
                    await expect(page.locator('.answer-actions').first()).toContainText('已保存第 2 版');
                    await expect(page.locator('.practice-question.is-current .practice-feedback')).toContainText('下面反馈仅对应旧版');
                    const state = await (await context.request.get(fixture.origin + '/__fixture/state')).json();
                    expect(state.data.attempts['saved-run'].map(a => a.version)).toEqual([1, 2]);
                    expect(state.data.feedbacks[0].feedback.answer_version).toBe(1);
                    expect(state.data.feedbacks[0].attempt_id).toBe(state.data.attempts['saved-run'][0].attempt_id);
                    expect(generation()).toBe(before);
                });
                await check('leaving during version validation cancels a late reference without inference', async () => {
                    const waiting = new Promise(r => observedIndex = r);
                    holdIndex = true;
                    await source().click();
                    await waiting;
                    const response = page.waitForResponse(r => r.url().includes('/evidence/index-status'));
                    await nav('Tutor 问答').click();
                    releaseIndex();
                    await response;
                    await expect(page.getByText('正在核对来源版本，当前学习任务保留。', { exact: true })).toHaveCount(0);
                    await nav('解释与练习').click();
                    await expect(answer()).toHaveValue('同页未保存的修订');
                    await expect(marker()).toHaveCount(0);
                    await expect(page.locator('.evidence-reading__return')).toHaveCount(0);
                    expect(generation()).toBe(before);
                });
                await check('failed recheck clears a previous trusted marker and preserves the current draft', async () => {
                    await answer().fill('旧版本错误时保留');
                    await review();
                    await page.setViewportSize({ width: 1440, height: 900 });
                    await change({ revision: 2 });
                    await source().click();
                    await expect(page.locator('.evidence-navigation-error')).toContainText('课程资料已更新');
                    await expect(marker()).toHaveCount(0);
                    await expect(answer()).toHaveValue('旧版本错误时保留');
                    expect(generation()).toBe(before);
                    await page.setViewportSize({ width, height: width === 1440 ? 900 : 844 });
                    await capture('revision-error');
                });
                await check('ownership loss clears material, citation and answer caches', async () => {
                    await change({ revision: 1 });
                    await page.setViewportSize({ width: 1440, height: 900 });
                    await review();
                    await change({ denied: true });
                    await source().click();
                    await expect(page.getByRole('heading', { name: '课程不可用或权限已变化' })).toBeVisible();
                    await expect(marker()).toHaveCount(0);
                    await expect(page.locator('.content-panel')).toHaveCount(0);
                    await expect(page.locator('.practice-answer')).toHaveCount(0);
                    expect(generation()).toBe(before);
                });
                await check('switching courses and a deleted-course response never restore a trusted reference', async () => {
                    await change({ denied: false });
                    await page.goto(fixture.origin + '/tasks/synthetic?view=agent');
                    await expect(answer()).toBeVisible();
                    await review();
                    await page.setViewportSize({ width: 1440, height: 900 });
                    await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '我的课程', exact: true }).click();
                    await page.getByRole('button', { name: '查看进度', exact: true }).click();
                    await expect(page).toHaveURL(/tasks\/preparing/);
                    await expect(marker()).toHaveCount(0);
                    await page.goto(fixture.origin + '/tasks/synthetic?view=agent');
                    await expect(answer()).toBeVisible();
                    await review();
                    await change({ denied: true });
                    await source().click();
                    await expect(page.getByRole('heading', { name: '课程不可用或权限已变化' })).toBeVisible();
                    await expect(marker()).toHaveCount(0);
                    expect(generation()).toBe(before);
                    await page.setViewportSize({ width, height: width === 1440 ? 900 : 844 });
                    await capture('unavailable');
                });
                expect(errors).toEqual([]);
                expect(external).toEqual([]);
                expect(fixture.errors).toEqual([]);
                cases.push({ width, entry, triggerWidth, status: 'PASS', checks, errors, external, requests: [...fixture.requests] });
            }
            catch (e) {
                await capture('failure').catch(() => { });
                cases.push({ width, entry, triggerWidth, status: 'FAIL', checks, error: String(e), errors, external, requests: [...fixture.requests] });
                console.error(String(e));
            }
            finally {
                releaseIndex?.();
                await context.close();
            }
        }
}
finally {
    await browser.close();
    await fixture.close();
    await writeFile(output + '/results.json', JSON.stringify({ chromiumSandbox: true, api: 'isolated deterministic HTTP fixture', physicalProviderCalls: 0, cases }, null, 2));
}
if (cases.some(c => c.status !== 'PASS'))
    process.exitCode = 1;
