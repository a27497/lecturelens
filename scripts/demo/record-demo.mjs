// Records the README walkthrough against a running scripts/demo/up.sh stack.
//
//   node scripts/demo/record-demo.mjs --url <course URL printed by up.sh> \
//     --email demo@example.com --password <printed password> --mode mock|real --output .demo/recording
//
// Playwright comes from frontend/node_modules (npm ci) and needs `npx playwright install chromium`.
// The banner injected at the top of every frame names the mode (Mock or Real) and the step,
// so a cropped GIF cannot be mistaken for the other mode.
import { createRequire } from 'node:module';
import { mkdir, readdir, rename } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { parseArgs } from 'node:util';

const require = createRequire(resolve('frontend/package.json'));
const { chromium } = require('@playwright/test');

const { values: args } = parseArgs({ options: {
  url: { type: 'string' }, email: { type: 'string' }, password: { type: 'string' },
  mode: { type: 'string', default: 'mock' }, output: { type: 'string', default: '.demo/recording' },
} });
if (!args.url || !args.email || !args.password || !['mock', 'real'].includes(args.mode)) {
  throw Error('Require --url, --email, --password and --mode mock|real');
}
const output = resolve(args.output);
await mkdir(output, { recursive: true });
const modeLabel = args.mode === 'real' ? 'Real · deepseek-flash' : 'Mock · 确定性演示提供方，无外部模型调用';
// Bounded waits: each value is the slowest step observed in the stack plus margin, so a stuck
// Run ends the recording instead of producing an endless video.
const QA_TIMEOUT_MS = 60_000;
const RUN_TIMEOUT_MS = 150_000;

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

// 1. Log in and open the course.
await page.goto(new URL('/login', args.url).href);
const inputs = page.locator('input');
// Real-mode login fields stay read-only until focused (autofill guard), so focus before typing.
for (const [index, value] of [[0, args.email], [1, args.password]]) {
  await inputs.nth(index).click();
  await inputs.nth(index).fill(value);
}
await page.locator('button[type=submit], button:has-text("登录")').first().click();
await page.waitForURL(/\/tasks/);
await page.goto(args.url);
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
const jump = page.getByRole('button', { name: '跳到视频' }).filter({ visible: true });
if (await jump.count()) {
  await jump.last().click();
  await pause(800);
  await page.locator('video').scrollIntoViewIfNeeded();
  await banner('3/5 点击引用：视频跳到对应时间点，原文高亮');
  await pause(4000);
  await shot('03-qa-seek');
}

// 4. A question the course does not cover.
await banner('4/5 课程里没讲的问题：拒答，而不是编造');
await ask('How does a red-black tree keep itself balanced after insertion?');
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
await page.getByText(/练习已生成|证据不足|未完成|失败|预算/).first().waitFor({ timeout: RUN_TIMEOUT_MS });
await pause(1500);
const explanation = page.getByText('阅读课程解释');
if (await explanation.count()) { await explanation.first().click(); await pause(4000); }
await shot('05-practice');
const answer = page.locator('textarea[placeholder*="写下你的理解"]').first();
if (await answer.count()) {
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
  await page.getByText(/版作答的证据反馈|本次未完成可靠反馈|反馈已取消/).first()
    .waitFor({ timeout: RUN_TIMEOUT_MS }).catch(() => {});
  await pause(6000);
  await shot('05-feedback');
}
await banner('LectureLens · 课程证据约束的学习 Agent');
await pause(2000);

await context.close();
await browser.close();
const video = (await readdir(output)).find(name => name.endsWith('.webm') && name !== 'walkthrough.webm');
if (video) await rename(join(output, video), join(output, 'walkthrough.webm'));
console.log(`PASS recording ${join(output, 'walkthrough.webm')}`);
