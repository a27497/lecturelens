// Records the README walkthrough against a running scripts/demo/up.sh stack.
//
//   node scripts/demo/record-demo.mjs [--instance default] [--output .demo/recording]
//
// The course URL, mode and model come from .demo/stack-<instance>/state.json and the demo
// password from the owner-only secrets.json, so nothing secret appears on the command line.
// Playwright comes from frontend/node_modules (npm ci) and needs `npx playwright install chromium`.
// A banner on every frame names the mode (Mock or Real) and the step, so a cropped GIF cannot be
// mistaken for the other mode. The script exits non-zero unless every step reached its expected
// outcome; diagnostic screenshots and the video are kept either way.
import { createRequire } from 'node:module';
import { mkdir, readFile, rm } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { parseArgs } from 'node:util';

const require = createRequire(resolve('frontend/package.json'));
const { chromium } = require('@playwright/test');

const { values: args } = parseArgs({ options: {
  instance: { type: 'string', default: process.env.LECTURELENS_DEMO_INSTANCE || 'default' },
  output: { type: 'string', default: '.demo/recording' },
} });
const stackDir = resolve('.demo', `stack-${args.instance}`);
const state = JSON.parse(await readFile(join(stackDir, 'state.json'), 'utf8'));
const password = JSON.parse(await readFile(join(stackDir, 'secrets.json'), 'utf8')).DEMO_PASSWORD;
const email = 'demo@example.com';
if (!state.task_id || !state.ports?.WEB_PORT) throw Error(`${stackDir} has no prepared course; run up.sh first`);
const courseUrl = `http://127.0.0.1:${state.ports.WEB_PORT}/tasks/${state.task_id}`;
const real = state.mode === 'real';
const modeLabel = real ? `Real · ${state.model}` : 'Mock · 确定性演示提供方，无外部模型调用';
const output = resolve(args.output);
await mkdir(output, { recursive: true });
const finalVideo = join(output, 'walkthrough.webm');
await rm(finalVideo, { force: true });
// Bounded waits: each value is the slowest step observed in the stack plus margin, so a stuck
// Run ends the recording instead of producing an endless video.
const QA_TIMEOUT_MS = 60_000;
const RUN_TIMEOUT_MS = 150_000;
const problems = [];

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: output, size: { width: 1440, height: 900 } },
});
const page = await context.newPage();
page.setDefaultTimeout(30_000);

async function banner(step) {
  await page.evaluate(([mode, text]) => {
    let node = document.getElementById('ll-demo-banner');
    if (!node) {
      node = document.createElement('div');
      node.id = 'll-demo-banner';
      node.style.cssText = 'position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:99999;'
        + 'background:rgba(32,42,38,.92);color:#fff;font:600 18px/1.4 system-ui,sans-serif;padding:10px 18px;'
        + 'border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.25);pointer-events:none;max-width:90vw;text-align:center';
      document.body.appendChild(node);
    }
    node.textContent = `${text}  ·  ${mode}`;
  }, [modeLabel, step]);
}
const pause = ms => page.waitForTimeout(ms);
const shot = name => page.screenshot({ path: join(output, `${name}.png`) });

try {
  // 1. Log in and open the course.
  await page.goto(new URL('/login', courseUrl).href);
  const inputs = page.locator('input');
  // Real-mode login fields stay read-only until focused (autofill guard), so focus before typing.
  for (const [index, value] of [[0, email], [1, password]]) {
    await inputs.nth(index).click();
    await inputs.nth(index).fill(value);
  }
  await page.locator('button[type=submit], button:has-text("登录")').first().click();
  await page.waitForURL(/\/tasks/);
  await page.goto(courseUrl);
  await page.getByRole('button', { name: '时间轴' }).waitFor();
  await banner('1/5 打开课程：视频、字幕时间轴和学习资料');
  await pause(3500);

  // 2. Transcript and learning material.
  await page.getByRole('button', { name: '原文' }).click();
  await pause(2500);
  await page.getByRole('button', { name: '时间轴' }).click();
  await page.getByRole('button', { name: '学习资料' }).click();
  await banner('2/5 字幕原文、时间轴与学习资料（摘要、重点、术语）');
  await pause(4000);
  await shot('02-material');

  // 3. Course QA with a citation that seeks the video.
  async function ask(text) {
    await page.getByRole('button', { name: '课程问答' }).click();
    const box = page.locator('textarea:visible').first();
    await box.fill(text);
    await pause(800);
    await page.getByRole('button', { name: '提问', exact: true }).click();
    // The answer heading appears once the saved answer is rendered for this question.
    await page.locator('h3, h4, strong').filter({ hasText: text }).first().waitFor({ timeout: QA_TIMEOUT_MS });
    await page.getByText(text, { exact: true }).first().scrollIntoViewIfNeeded();
  }
  await banner('3/5 课程问答：回答附带可定位的课程证据');
  await ask('Why does the loop stop when low becomes greater than high?');
  await pause(4500);
  await shot('03-qa-answer');
  // Only the answer's own evidence list counts; the transcript has seek buttons of its own.
  const jump = page.locator('.qa-answer .qa-evidence').getByRole('button', { name: '跳到视频' });
  if (await jump.count()) {
    await jump.first().click();
    // The UI re-checks the evidence revision before seeking; wait for the highlighted reference.
    const seeked = await page.getByText('当前引用').first().waitFor({ timeout: 10_000 }).then(() => true, () => false);
    await page.locator('video').scrollIntoViewIfNeeded();
    if (seeked) await banner('3/5 点击引用：视频跳到对应时间点，原文高亮');
    else problems.push('citation seek was not confirmed');
    await pause(4000);
    await shot('03-qa-seek');
  } else {
    problems.push('course QA answer has no citation to follow');
  }

  // 4. A question the course does not cover.
  await banner('4/5 问一个课程里没讲的问题');
  await ask('How does a red-black tree keep itself balanced after insertion?');
  const refused = await page.locator('.qa-answer').getByText('没有找到明确依据').count() > 0;
  if (refused) await banner('4/5 课程里没讲：拒答，而不是编造');
  else if (!real) await banner('4/5 Mock 不会拒答：它总是引用检索到的第一条证据');
  else problems.push('real-mode course QA did not refuse the out-of-course question');
  await pause(5000);
  await shot('04-abstain');

  // 5. Study Agent: explanation and practice, then a saved answer and evidence feedback.
  await page.getByRole('button', { name: '解释与练习' }).click();
  await banner('5/5 Study Agent：检索课程证据 → 解释 → 两道练习');
  // After an earlier recording the start form is collapsed under a disclosure.
  const startForm = page.getByText('开始新的解释与练习');
  if (!(await page.getByRole('button', { name: '解释并出题' }).isVisible()) && await startForm.count()) {
    await startForm.first().click();
  }
  await page.locator('textarea[placeholder^="例如"]:visible').first()
    .fill('解释二分查找为什么每一步都能排除一半范围，并给我两道练习。');
  await pause(800);
  await page.getByRole('button', { name: '解释并出题' }).click();
  // Terminal run states as rendered by CourseAgentPanel.
  const terminal = /练习已生成|解释与练习已完成|课程证据不足|本次执行未完成|已取消|本次执行已达到时间或调用上限/;
  const runState = await page.getByText(terminal).first().waitFor({ timeout: RUN_TIMEOUT_MS })
    .then(() => page.getByText(terminal).first().innerText(), () => 'timeout');
  if (!/练习已生成|解释与练习已完成/.test(runState)) problems.push(`Study run ended: ${runState}`);
  await pause(1500);
  const explanation = page.getByText('阅读课程解释');
  if (await explanation.count()) { await explanation.first().click(); await pause(4000); }
  await shot('05-practice');
  const answer = page.locator('textarea[placeholder*="写下你的理解"]').first();
  if (!(await answer.count())) problems.push('no practice question to answer');
  else {
    await answer.scrollIntoViewIfNeeded();
    await answer.fill('每次和中间元素比较后，目标只可能在一侧，所以另一半可以直接排除。');
    await pause(800);
    await page.getByRole('button', { name: '保存作答' }).first().click();
    const request = page.getByRole('button', { name: '获取证据反馈' }).first();
    await request.waitFor();
    await page.waitForFunction(el => !el.disabled, await request.elementHandle());
    await banner('5/5 保存作答后请求证据反馈');
    await request.scrollIntoViewIfNeeded();
    await request.click();
    const outcome = /版作答的证据反馈|本次未完成可靠反馈|反馈已取消/;
    const feedback = await page.getByText(outcome).first().waitFor({ timeout: RUN_TIMEOUT_MS })
      .then(() => page.getByText(outcome).first().innerText(), () => 'timeout');
    if (!feedback.includes('版作答的证据反馈')) problems.push(`feedback did not complete: ${feedback}`);
    await pause(6000);
    await shot('05-feedback');
  }
  await banner('LectureLens · 课程证据约束的学习 Agent');
  await pause(2000);
} catch (error) {
  problems.push(`step failed: ${error.message.split('\n')[0]}`);
  await shot('failure').catch(() => {});
} finally {
  // Closing the context flushes the video; save this page's own file, never a leftover one.
  const video = page.video();
  await context.close().catch(() => {});
  if (video) {
    await video.saveAs(finalVideo).catch(error => problems.push(`video not saved: ${error.message}`));
    await video.delete().catch(() => {});
  } else {
    problems.push('no video recorded');
  }
  await browser.close().catch(() => {});
}
if (problems.length) {
  console.error(`INCOMPLETE recording ${finalVideo}\n- ${problems.join('\n- ')}`);
  process.exit(1);
}
console.log(`PASS recording ${finalVideo} (${state.mode})`);
