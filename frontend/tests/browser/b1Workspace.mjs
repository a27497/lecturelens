import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { parseArgs } from 'node:util';
import { resolve } from 'node:path';
import { createB1Fixture } from './b1Fixture.mjs';

const { values: args } = parseArgs({ options: { dist: { type: 'string', default: 'dist' }, media: { type: 'string' }, output: { type: 'string' }, chromium: { type: 'string' } } });
if (!args.media || !args.output) throw Error('Require --media approved-synthetic.mp4 --output separate-evidence-directory');
const output = resolve(args.output); await mkdir(output, { recursive: true });
const fixture = await createB1Fixture(args), results = [];
const browser = await chromium.launch({ executablePath: args.chromium, headless: true, args: ['--no-sandbox'] });
let failed = false;
const entryChecks = [];
try {
  const guest = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await guest.route('**/*', r => new URL(r.request().url()).origin === fixture.origin ? r.continue() : r.abort());
  const login = await guest.newPage();
  for (const target of ['/login', '/login?redirect=/tasks/synthetic?layout=classic']) {
    await guest.clearCookies(); await login.goto(fixture.origin + '/__preview'); await login.evaluate(() => localStorage.clear());
    await login.goto(fixture.origin + target);
    await login.getByPlaceholder('you@example.com').fill('synthetic@example.invalid');
    await login.getByPlaceholder('请输入密码').fill('Offline-fixture-123');
    await login.getByRole('button', { name: '登录', exact: true }).click();
    await expect(login).toHaveURL(target.includes('redirect') ? fixture.origin + '/tasks/synthetic?layout=classic' : fixture.origin + '/tasks');
    entryChecks.push(target.includes('redirect') ? 'login preserves explicit legacy course redirect' : 'normal login opens course library');
  }
  await guest.close();
  for (const width of [1440, 390]) {
    fixture.reset();
    const context = await browser.newContext({ viewport: { width, height: width === 1440 ? 900 : 844 } });
    await context.addInitScript(() => localStorage.setItem('courselingo.accessToken', 'offline-fixture-token'));
    const page = await context.newPage(), errors = [], external = [], checks = [];
    page.on('pageerror', e => errors.push(String(e)));
    await context.route('**/*', route => {
      if (new URL(route.request().url()).origin === fixture.origin) return route.continue();
      external.push(route.request().url()); return route.abort();
    });
    const count = op => fixture.requests.filter(r => r.operation === op).length;
    const generation = () => count('START') + count('START_FEEDBACK') + count('CREATE_SESSION');
    const change = data => context.request.post(fixture.origin + '/__fixture', { data });
    const nav = name => page.getByRole('navigation', { name: '课程内容导航' }).getByRole('button', { name, exact: true });
    const answer = () => page.locator('.practice-question.is-current textarea').first();
    const feedback = () => page.locator('.practice-question.is-current .practice-feedback');
    const save = () => page.locator('.practice-question.is-current').getByRole('button', { name: '保存作答', exact: true });
    const capture = async name => {
      await page.screenshot({ path: `${output}/${width}-${name}.png`, fullPage: false });
      await writeFile(`${output}/${width}-${name}.aria.txt`, await page.locator('body').ariaSnapshot());
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    };
    const check = async (name, run) => { console.log(`START ${width} ${name}`); await run(); checks.push(name); console.log(`PASS ${width} ${name}`); };
    try {
      await check('authenticated entry and ready-course action', async () => {
        await page.goto(fixture.origin + '/'); await expect(page).toHaveURL(fixture.origin + '/tasks');
        await page.getByRole('button', { name: '进入学习', exact: true }).click();
        await expect(answer()).toBeVisible(); expect(generation()).toBe(0);
        await expect(page.locator('.new-study-goal')).not.toHaveAttribute('open');
        await expect.poll(() => page.locator('video').evaluate(v => v.readyState)).toBeGreaterThan(1);
        await page.evaluate(() => scrollTo(0, 0)); await capture('workspace');
        expect(await answer().evaluate(el => el.getBoundingClientRect().top)).toBeLessThan((width === 1440 ? 900 : 844) - 24);
      });
      await check('real media playback, pause and location', async () => {
        if (width === 390) await page.getByRole('button', { name: '看视频与原文', exact: true }).click();
        const video = page.locator('video'); await expect.poll(() => video.evaluate(v => v.readyState)).toBeGreaterThan(1);
        await video.evaluate(v => v.play()); await expect.poll(() => video.evaluate(v => v.currentTime)).toBeGreaterThan(0.1);
        await video.evaluate(v => { v.pause(); v.currentTime = 12; }); await expect.poll(() => video.evaluate(v => Math.abs(v.currentTime - 12))).toBeLessThan(.2);
        await capture('materials');
        await page.getByRole('button', { name: /继续第 1 题/ }).click();
      });
      await check('Tutor is independent and keeps its draft across view changes', async () => {
        await nav('课程问答').click(); await page.getByRole('textbox', { name: '课程问题', exact: true }).fill('这两组相差多少分？');
        await page.getByRole('button', { name: '提问', exact: true }).click();
        await expect(page.getByText('合成回答：A组84，B组61，相差23分；不能从虚构小样本推断所有学生。')).toBeVisible();
        expect(generation()).toBe(0); await capture('tutor');
        await page.getByRole('textbox', { name: '课程问题', exact: true }).fill('未提交追问');
        await page.locator('.qa-evidence .evidence-item button').click();
        await page.getByRole('button', { name: '返回当前学习任务', exact: true }).click();
        await expect(page.getByRole('textbox', { name: '课程问题', exact: true })).toHaveValue('未提交追问');
        await nav('学习助手').click(); await nav('课程问答').click();
        await expect(page.getByRole('textbox', { name: '课程问题', exact: true })).toHaveValue('未提交追问');
        await nav('学习助手').click();
      });
      await check('question drafts, DOM identity and media survive tab and layout changes', async () => {
        await answer().fill('第一页尚未保存'); const node = await answer().elementHandle();
        await page.getByRole('button', { name: '第 2 题', exact: true }).click(); await answer().fill('第二题草稿');
        await page.getByRole('button', { name: /第 1 题/ }).click(); await expect(answer()).toHaveValue('第一页尚未保存');
        await page.getByRole('button', { name: '经典布局', exact: true }).click(); await expect(answer()).toHaveValue('第一页尚未保存');
        await page.getByRole('button', { name: '连续工作区', exact: true }).click();
        expect(await answer().evaluate((el, old) => el === old, node)).toBe(true);
        await expect.poll(() => page.locator('video').evaluate(v => Math.abs(v.currentTime - 12))).toBeLessThan(.2);
      });
      await check('failed save keeps text and safely retries the same request key', async () => {
        await answer().fill('需要重试的合成答案'); await change({ failSave: true }); await save().click();
        await expect(page.getByText('保存未确认，你的文字仍在本页。请重试保存。', { exact: true })).toBeVisible();
        await expect(answer()).toHaveValue('需要重试的合成答案');
        const key = fixture.requests.findLast(r => r.operation === 'SAVE_ATTEMPT').command.request_key;
        await change({ failSave: false }); await save().click();
        await expect(page.getByText('已保存第 1 版', { exact: true })).toBeVisible();
        expect(fixture.requests.findLast(r => r.operation === 'SAVE_ATTEMPT').command.request_key).toBe(key);
        await change({ attempts: { 'saved-run': [], 'older-run': [] } }); await page.reload(); await expect(answer()).toHaveValue('');
      });
      await check('save is explicit and never starts feedback', async () => {
        await answer().fill('A组84，B组62，相差22，所有人都会提高。');
        await save().click(); await expect(page.getByText('已保存第 1 版', { exact: true })).toBeVisible();
        expect(count('START_FEEDBACK')).toBe(0);
        await expect(feedback().getByText('将使用已保存第 1 版作答')).toBeVisible();
      });
      await check('feedback belongs to saved attempt, source return keeps draft and focus', async () => {
        await feedback().getByRole('button', { name: '获取证据反馈', exact: true }).click();
        await expect(feedback().getByRole('heading', { name: '第 1 版作答的证据反馈', exact: true })).toBeVisible();
        await answer().fill('正在修订，但还没保存');
        await expect(feedback().getByRole('button', { name: '重新获取证据反馈', exact: true })).toBeDisabled();
        const before = generation();
        await feedback().getByRole('button', { name: '回看这段课程证据', exact: true }).focus();
        await feedback().getByRole('button', { name: '回看这段课程证据', exact: true }).click();
        const back = page.getByRole('button', { name: '返回当前学习任务', exact: true }); await expect(back).toBeVisible();
        if (width === 390) {
          await expect(page.locator('.workspace-wayfinding')).toBeHidden();
          await expect(page.locator('.workspace-header')).toBeHidden();
          await expect(page.locator('video')).toBeHidden();
          expect(await page.locator('.timeline-row[aria-current=true]').evaluate(el => el.getBoundingClientRect().width)).toBeGreaterThan(290);
        }
        await capture('source'); await back.click(); await expect(answer()).toHaveValue('正在修订，但还没保存');
        await expect(feedback().getByRole('button', { name: '回看这段课程证据', exact: true })).toBeFocused();
        expect(generation()).toBe(before);
      });
      await check('immutable answer v2 retains feedback v1 and history', async () => {
        await answer().fill('A组84，B组61，相差23分；虚构实验不代表所有学生。'); await save().click();
        await expect(page.getByText('已保存第 2 版', { exact: true })).toBeVisible();
        await expect(feedback().getByText('你已保存新版作答，下面反馈仅对应旧版。', { exact: true })).toBeVisible();
        await page.locator('.practice-question.is-current').getByRole('button', { name: '修改记录', exact: true }).click();
        await expect(page.locator('.answer-history').getByText('第 1 版', { exact: true })).toBeVisible();
        await expect(page.locator('.answer-history').getByText('第 2 版', { exact: true })).toBeVisible();
        await capture('versions');
      });
      await check('cancel feedback preserves answers and previous feedback remains readable', async () => {
        await change({ slow: true }); await feedback().getByRole('button', { name: '重新获取证据反馈', exact: true }).click();
        await feedback().getByRole('button', { name: '取消反馈', exact: true }).click();
        await expect(feedback().getByText('反馈已取消。已保存作答不受影响。', { exact: true })).toBeVisible();
        await expect(page.getByText('已保存第 2 版', { exact: true })).toBeVisible();
        await change({ slow: false }); await feedback().getByRole('button', { name: '重新获取证据反馈', exact: true }).click();
        await expect(feedback().getByRole('heading', { name: '第 2 版作答的证据反馈', exact: true })).toBeVisible();
      });
      await check('feedback-history cancellation preserves note and selected version', async () => {
        await feedback().getByText('核对或更正反馈', { exact: true }).click();
        await feedback().getByRole('textbox', { name: '反馈核对意见', exact: true }).fill('本页尚未保存的核对意见');
        const select = feedback().getByRole('combobox', { name: '第 1 题反馈记录', exact: true });
        const value = await select.inputValue();
        page.once('dialog', d => d.dismiss()); await select.selectOption('feedback-run-0');
        await expect(select).toHaveValue(value);
        await expect(feedback().getByRole('textbox', { name: '反馈核对意见', exact: true })).toHaveValue('本页尚未保存的核对意见');
      });
      await check('history switching protects unsaved answers and is read-only', async () => {
        await answer().fill('历史切换前的草稿'); const before = generation();
        await page.getByRole('button', { name: '学习记录', exact: true }).click();
        page.once('dialog', d => d.dismiss()); await page.locator('.learning-history').getByRole('button', { name: '另一条已保存的示例练习', exact: true }).click();
        await expect(answer()).toHaveValue('历史切换前的草稿');
        page.once('dialog', d => d.accept()); await page.locator('.learning-history').getByRole('button', { name: '另一条已保存的示例练习', exact: true }).click();
        await expect(answer()).toHaveValue(''); expect(generation()).toBe(before);
        await page.getByRole('button', { name: '学习记录', exact: true }).click();
        await page.locator('.learning-history').getByRole('button', { name: '核对平均分与差值，解释结论边界。', exact: true }).click();
        await expect(answer()).toHaveValue('A组84，B组61，相差23分；虚构实验不代表所有学生。');
      });
      await check('real reload restores saved versions, excludes drafts and stays paused', async () => {
        await answer().fill('刷新不应恢复的草稿'); await page.reload();
        await expect(answer()).toHaveValue('A组84，B组61，相差23分；虚构实验不代表所有学生。');
        await expect(feedback().getByRole('heading', { name: '第 2 版作答的证据反馈', exact: true })).toBeVisible();
        await expect(page.locator('video')).toHaveJSProperty('paused', true);
      });
      await check('source revision fence blocks stale feedback navigation without discarding draft', async () => {
        await answer().fill('版本变化仍保留'); await change({ revision: 2 });
        await feedback().getByRole('button', { name: '回看这段课程证据', exact: true }).click();
        await expect(page.locator('.evidence-navigation-error')).toBeVisible(); await expect(answer()).toHaveValue('版本变化仍保留');
        await capture('revision-error'); await change({ revision: 1 });
      });
      await check('scope failure remains closed and keeps saved-task access', async () => {
        await change({ scopeFailed: true }); await page.reload(); await expect(answer()).toBeVisible();
        await page.locator('.scope-options > summary').click(); await expect(page.getByRole('button', { name: '提问', exact: true })).toHaveCount(0);
        await expect(page.locator('.scope-picker').getByText('范围加载失败，请重试或重新打开课程。').first()).toBeVisible();
        await page.locator('.new-study-goal > summary').click(); await expect(page.getByRole('button', { name: '解释并出题', exact: true })).toBeDisabled();
        await change({ scopeFailed: false }); await page.locator('.scope-picker').getByRole('button', { name: '刷新范围', exact: true }).click();
      });
      await check('explicit new run freezes chosen scope and cancellation stays reachable', async () => {
        await change({ slow: true }); await page.getByRole('textbox', { name: '学习目标', exact: true }).fill('只根据课程核对差值');
        await page.getByRole('button', { name: '解释并出题', exact: true }).click();
        await expect(page.getByRole('button', { name: '取消本次执行', exact: true })).toBeVisible();
        expect(fixture.requests.findLast(r => r.operation === 'START').command.learning_scope.revision).toBe(1);
        await page.getByRole('button', { name: '取消本次执行', exact: true }).click();
        await expect(page.locator('.run-progress').getByText('已取消', { exact: true })).toBeVisible();
        await change({ slow: false });
      });
      await check('new completed run freezes strict segment scope and supports answer-feedback-source loop', async () => {
        const scope = page.getByRole('region', { name: '学习范围', exact: true });
        // A section with aria-label is a region in Chromium's accessibility tree.
        if ((await scope.locator('.scope-options').getAttribute('open')) === null) await scope.locator('.scope-options > summary').click();
        await scope.getByRole('radio', { name: '选择课程片段', exact: true }).check();
        await scope.getByRole('checkbox', { name: /Group A scores 84/ }).check();
        await expect(scope.locator('.frozen-scope > summary')).toContainText('整节课程');
        await page.locator('.new-study-goal > summary').click();
        await page.getByRole('textbox', { name: '学习目标', exact: true }).fill('明确开始：核对这个片段的差值');
        await page.getByRole('button', { name: '解释并出题', exact: true }).click();
        await expect(answer()).toHaveValue('');
        const start = fixture.requests.findLast(r => r.operation === 'START').command;
        expect(start.learning_scope.kind).toBe('segments'); expect(start.learning_scope.policy).toBe('strict'); expect(start.learning_scope.evidence_ids).toEqual(['course:synthetic:subtitle:2:r1']);
        await expect(scope.locator('.frozen-scope > summary')).toContainText('仅限选中范围');
        await answer().fill('84减61等于23；虚构示例不代表所有人。'); await save().click();
        await feedback().getByRole('button', { name: '获取证据反馈', exact: true }).click();
        await expect(feedback().getByRole('heading', { name: '第 1 版作答的证据反馈', exact: true })).toBeVisible();
        const before = generation(); await feedback().getByRole('button', { name: '回看这段课程证据', exact: true }).click();
        await page.getByRole('button', { name: '返回当前学习任务', exact: true }).click();
        await expect(answer()).toHaveValue('84减61等于23；虚构示例不代表所有人。'); expect(generation()).toBe(before);
        await capture('new-run-feedback');
      });
      await check('legacy classic URL, execution details and course denial compatibility', async () => {
        await page.goto(fixture.origin + '/tasks/synthetic?view=content&text=timeline&at=12000&layout=classic');
        await expect(page.locator('.course-layout')).not.toHaveClass(/course-layout--continuous/);
        await expect(page.locator('.timeline-row').first()).toBeVisible(); await capture('classic');
        await nav('学习助手').click(); await page.getByRole('button', { name: 'View Trace · 查看执行链路', exact: true }).click();
        await expect(page.getByRole('region', { name: 'Agent Trace' })).toBeVisible();
        const before = generation(); await change({ denied: true }); await page.getByRole('button', { name: '刷新', exact: true }).click();
        await expect(page.locator('.course-unavailable')).toBeVisible(); await expect(answer()).toHaveCount(0);
        expect(generation()).toBe(before); await capture('permission-error');
      });
      await check('index failure and preparing material show clear states without inference', async () => {
        const before = generation(); await change({ denied: false, indexFailed: true });
        await page.goto(fixture.origin + '/tasks/synthetic');
        await expect(page.getByText('课程资料准备失败，请查看处理进度并重试。', { exact: true })).toBeVisible();
        await page.locator('.new-study-goal > summary').click(); await expect(page.getByRole('button', { name: '解释并出题', exact: true })).toBeDisabled();
        await page.goto(fixture.origin + '/tasks/preparing');
        await expect(page.getByText('课程内容尚未处理完成。请先查看处理进度，完成后即可开始学习。', { exact: true })).toBeVisible();
        expect(generation()).toBe(before); await capture('preparing');
      });
      expect(errors).toEqual([]); expect(external).toEqual([]); expect(fixture.errors).toEqual([]);
      results.push({ width, height: width === 1440 ? 900 : 844, status: 'PASS', checks, errors, external, fixtureErrors: [...fixture.errors], requests: [...fixture.requests], physicalProviderCalls: 0 });
    } catch (e) {
      failed = true; await page.screenshot({ path: `${output}/${width}-failure.png` });
      results.push({ width, status: 'FAIL', checks, error: String(e), errors, external, fixtureErrors: [...fixture.errors], requests: [...fixture.requests] });
      console.error(e);
    } finally { await context.close(); }
  }
} finally { await browser.close(); await fixture.close(); await writeFile(`${output}/results.json`, JSON.stringify({ entryChecks, cases: results }, null, 2)); }
if (failed) process.exitCode = 1;
