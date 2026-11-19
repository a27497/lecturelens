import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const openingQuestion = '为什么 low 大于 high 时循环就停止？';
const answer = '每次和中间元素比较后，目标只可能在一侧，所以另一半可以直接排除。';

test('opens a course, checks sources, practices, reviews and resumes', async ({ page, isMobile }) => {
  const instance = process.env.LECTURELENS_DEMO_INSTANCE || 'default';
  if (!/^[a-z0-9-]{1,32}$/.test(instance)) throw new Error('Invalid demo instance name');
  const stack = new URL(`../../../.demo/stack-${instance}/`, import.meta.url);
  const state = JSON.parse(await readFile(new URL('state.json', stack), 'utf8'));
  if (state.mode !== 'mock' || !state.task_id || !state.ready_seconds || !Number.isInteger(state.ports?.WEB_PORT)) {
    throw new Error('Start the seeded Mock demo with scripts/demo/up.sh before running this test.');
  }
  const { DEMO_PASSWORD: password } = JSON.parse(await readFile(new URL('secrets.json', stack), 'utf8'));
  const base = `http://127.0.0.1:${state.ports.WEB_PORT}`;
  const position = () => new URL(page.url()).searchParams.get('at');
  const nav = page.getByRole('navigation', { name: '课程内容导航' });
  const tab = name => nav.getByRole('button', { name, exact: true });
  const courseCard = page.getByRole('article').filter({ has: page.getByRole('heading', { name: 'binary-search-demo', exact: true }) });
  const video = page.locator('video');
  const returnToLearning = page.getByRole('button', { name: '返回当前学习任务' });
  const citedRow = page.locator('.timeline-row[data-reference="true"]');
  const question = page.locator('.practice-question.is-current');
  const entries = () => page.evaluate(() => Object.entries(localStorage).filter(([key]) => key.startsWith('lecturelens.lastCourseLocation.v1:')));

  async function capture(name, target) {
    const output = process.env.LECTURELENS_SCREENSHOT_DIR;
    if (!output) return;
    if (target) await target.scrollIntoViewIfNeeded();
    const prefix = String(page.viewportSize().width);
    await page.screenshot({ path: resolve(output, `${prefix}-${name}.png`), fullPage: !target });
  }

  async function openTab(name) {
    const button = tab(name);
    if (!(await button.isVisible())) await nav.locator('summary').click();
    await button.click();
  }

  async function seekFromCitation(button, name) {
    await button.click();
    await expect(citedRow).toBeVisible();
    await expect(returnToLearning).toBeVisible();
    await capture(name, citedRow);
  }

  async function startPractice(format) {
    const goal = page.getByRole('textbox', { name: '学习目标' });
    const newGoal = page.locator('.new-study-goal');
    await expect(newGoal).toBeAttached();
    if (!(await goal.isVisible())) await newGoal.locator('summary').click();
    await goal.fill('解释二分查找为什么每次可以排除一半范围，并给我两道课程练习。');
    await page.getByLabel('练习形式').selectOption(format);
    await page.getByRole('button', { name: '解释并出题', exact: true }).click();
  }

  await test.step('sign in and open the named course', async () => {
    await page.goto(`${base}/login`);
    for (const [placeholder, value] of [['you@example.com', 'demo@example.com'], ['请输入密码', password]]) {
      const input = page.getByPlaceholder(placeholder, { exact: true });
      await input.click();
      await input.fill(value);
    }
    await page.locator('form').getByRole('button', { name: '登录', exact: true }).click();
    await expect(page).toHaveURL(`${base}/tasks`);
    await expect(courseCard.getByRole('heading')).toHaveAttribute('title', 'binary-search-demo');
    await capture('01-tasks');
    await courseCard.getByRole('button', { name: '进入学习', exact: true }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('binary-search-demo');
    await capture('02-course');
  });

  await test.step('read course captions and study material', async () => {
    if (isMobile) await openTab('课程材料');
    await expect(video).toBeVisible();
    await expect(page.locator('.timeline-row').first()).toBeVisible();
    await capture('03-transcript', page.locator('.timeline-row').first());
    await page.getByRole('navigation', { name: '课程内容视图' }).getByRole('button', { name: '原文', exact: true }).click();
    await expect(page.locator('.reading-copy')).toContainText(/binary search/i);
    await capture('03b-source', page.getByRole('heading', { name: '原文', exact: true }));
    await openTab('学习资料');
    const summary = page.getByRole('heading', { name: '课程摘要', exact: true });
    await expect(summary).toBeVisible();
    await capture('04-material', summary);
  });

  await test.step('ask Tutor, jump from a verified transcript row and return to the same draft', async () => {
    await openTab('Tutor 对话');
    const tutor = page.getByRole('region', { name: 'Tutor', exact: true });
    const draft = tutor.getByLabel('向课程 Tutor 提问');
    await expect(tutor.getByText('正在恢复对话…')).toBeHidden();
    await tutor.getByRole('button', { name: '新对话', exact: true }).click();
    await capture('05-tutor-empty', draft);
    await draft.fill(openingQuestion);
    await tutor.getByRole('button', { name: '发送', exact: true }).click();
    const chip = tutor.getByRole('button', { name: /^定位出处 \d{2}:\d{2}:\d{2} - \d{2}:\d{2}:\d{2}$/ }).first();
    await expect(chip).toBeVisible();
    await capture('06-tutor-answer', chip);
    await draft.fill('还没发送的追问');
    await seekFromCitation(chip, '07-tutor-seek');
    await expect.poll(() => position()).not.toBeNull();
    const citedMs = Number(position());
    if (isMobile) await expect(video).toBeHidden();
    await page.locator('.evidence-reading__return').getByRole('button', { name: '跳到视频', exact: true }).click();
    if (isMobile) await expect(video).toBeInViewport();
    else await expect(video).toBeVisible();
    await expect(video).toHaveJSProperty('paused', true);
    await expect.poll(() => video.evaluate(el => Math.round(el.currentTime * 1000))).toBe(citedMs);
    await capture('07b-jump', video);
    await returnToLearning.click();
    await expect(chip).toBeVisible();
    await expect(draft).toHaveValue('还没发送的追问');
    await capture('07c-return', draft);
  });

  await test.step('use the separate course Q&A entry and verify its source', async () => {
    await openTab('课程问答');
    const qa = page.getByRole('region', { name: '课程问答', exact: true });
    await expect(qa.getByRole('heading', { level: 2 })).toHaveText('课程问答');
    await capture('08-qa-empty', qa.getByRole('heading', { level: 2 }));
    await qa.getByRole('textbox', { name: '课程问题' }).fill('What happens when the middle element is smaller than the target?');
    await qa.getByRole('button', { name: '提问', exact: true }).click();
    const source = qa.getByRole('button', { name: '跳到视频', exact: true }).first();
    await expect(source).toBeVisible();
    await capture('09-qa-answer', source);
    await seekFromCitation(source, '10-qa-seek');
    await returnToLearning.click();
  });

  await test.step('generate open practice, save an answer and check feedback evidence', async () => {
    await openTab('解释与练习');
    await startPractice('open');
    const response = question.getByRole('textbox', { name: /题作答/ });
    await expect(response).toBeVisible();
    await capture('open-11-practice', response);
    await response.fill(answer);
    await question.getByRole('button', { name: '保存作答', exact: true }).click();
    const feedbackButton = question.getByRole('button', { name: '获取证据反馈', exact: true });
    await expect(feedbackButton).toBeEnabled();
    await capture('12-saved', feedbackButton);
    await feedbackButton.click();
    const feedback = question.getByRole('heading', { name: /版作答的证据反馈/ });
    await expect(feedback).toBeVisible();
    await expect(question.getByText('演示反馈，不代表模型判断。')).toBeVisible();
    await capture('13-feedback', feedback);
    await seekFromCitation(question.getByRole('button', { name: /^回看(这段课程证据|课程证据)/ }).first(), '13b-feedback-source');
    await returnToLearning.click();
    await expect(feedback).toBeVisible();
  });

  await test.step('submit a wrong choice and open its saved review', async () => {
    await startPractice('choice');
    const option = question.getByRole('radio', { name: /本题没有可引用的课程资料/ });
    await expect(option).toBeVisible();
    await capture('14-choice', option);
    await option.check();
    await question.getByRole('button', { name: '提交并判分', exact: true }).click();
    const grade = question.getByRole('article', { name: '选择题判分结果' });
    await expect(grade.getByRole('heading')).toContainText('错误');
    await capture('15-choice-graded', grade);
    await page.getByRole('button', { name: '答错待回看', exact: true }).click();
    const wrong = page.getByText(/程序判分：错误 · 正确选项/).first();
    await expect(wrong).toBeVisible();
    await capture('16-review', wrong);
  });

  await test.step('review a flashcard, return from My Courses and clear resume on sign-out', async () => {
    await openTab('课程材料');
    await expect(video).toBeVisible();
    await video.evaluate(el => { el.currentTime = 75; });
    await expect.poll(position).toBe('75000');
    await openTab('闪卡复习');
    const deck = page.getByRole('region', { name: '闪卡复习', exact: true });
    const generate = deck.getByRole('button', { name: '生成一组证据闪卡', exact: true });
    const flip = deck.getByRole('button', { name: /翻面/ });
    const reviewed = deck.getByText(/今日已复习 \d+ 张/);
    await expect(generate).toBeEnabled();
    await capture('17-flash-empty', generate);
    if (!(await flip.isVisible())) await generate.click();
    await flip.click();
    const previousReviews = Number((await reviewed.innerText()).match(/今日已复习 (\d+) 张/)[1]);
    const savedReviewCount = new RegExp(`今日已复习 ${previousReviews + 1} 张`);
    const good = deck.getByRole('button', { name: /Good/ });
    await capture('18-flash-card', good);
    await good.click();
    await expect(deck.getByRole('status')).toHaveText('评分已保存，下次复习时间已安排。');
    await expect(reviewed).toHaveText(savedReviewCount);

    await page.getByRole('link', { name: /返回我的课程/ }).click();
    await expect(page).toHaveURL(`${base}/tasks`);
    await expect(courseCard.getByText('上次停在：闪卡复习 · 视频 00:01:15')).toBeVisible();
    await capture('19-tasks-return');

    const [[key]] = await entries();
    await page.evaluate(storageKey => {
      const saved = JSON.parse(localStorage.getItem(storageKey));
      localStorage.setItem(storageKey, JSON.stringify({ ...saved, at: 74000 }));
      window.dispatchEvent(new StorageEvent('storage', { key: storageKey }));
    }, key);
    await expect(courseCard.getByText('上次停在：闪卡复习 · 视频 00:01:14')).toBeVisible();
    // Simulate a newer write whose storage event has not been handled yet.
    await page.evaluate(storageKey => {
      const saved = JSON.parse(localStorage.getItem(storageKey));
      localStorage.setItem(storageKey, JSON.stringify({ ...saved, at: 75000 }));
    }, key);
    await courseCard.getByRole('button', { name: '继续学习', exact: true }).click();
    await expect(tab('闪卡复习')).toHaveAttribute('aria-current', 'page');
    await expect.poll(position).toBe('75000');
    await expect.poll(() => video.evaluate(el => el.currentTime)).toBe(75);
    await expect(video).toHaveJSProperty('paused', true);
    await expect(reviewed).toHaveText(savedReviewCount);
    await capture('20-reenter', deck.getByRole('heading', { name: '闪卡复习' }));

    const [[, saved]] = await entries();
    expect(key).toMatch(/^lecturelens\.lastCourseLocation\.v1:\d+:/);
    expect(key.endsWith(`:${state.task_id}`)).toBe(true);
    expect(JSON.parse(saved)).toEqual({ view: 'flashcards', text: 'timeline', at: 75000, visitedAt: expect.any(Number) });

    await page.getByRole('link', { name: /返回我的课程/ }).click();
    let releaseIdentity;
    const identityReady = new Promise(resolve => { releaseIdentity = resolve; });
    let identityRequests = 0;
    await page.route('**/api/me', async route => {
      identityRequests += 1;
      if (identityRequests === 2) {
        await route.fulfill({ status: 503 });
        return;
      }
      await identityReady;
      await route.continue();
    });
    try {
      await page.reload();
      // Keep the header's request pending while the first attempt to open the course fails.
      await expect.poll(() => identityRequests).toBe(1);
      await courseCard.getByRole('button', { name: '进入学习', exact: true }).click();
      const error = courseCard.getByRole('alert');
      await expect(error).toContainText('暂时无法确认登录账号');
      await expect(page).toHaveURL(`${base}/tasks`);
      expect(await entries()).toEqual([[key, saved]]);
      await capture('21-resume-retry', error);

      await courseCard.getByRole('button', { name: '重试打开课程', exact: true }).click();
      await expect.poll(() => identityRequests).toBe(3);
      await expect(courseCard.getByRole('button', { name: '进入学习', exact: true })).toHaveClass(/is-loading/);
      await expect(page).toHaveURL(`${base}/tasks`);
    } finally {
      releaseIdentity();
    }
    await expect(tab('闪卡复习')).toHaveAttribute('aria-current', 'page');
    await expect.poll(position).toBe('75000');
    await expect.poll(() => video.evaluate(el => el.currentTime)).toBe(75);
    await page.unroute('**/api/me');

    const mobileMenu = page.getByRole('button', { name: '打开导航' });
    const usesMobileHeader = await mobileMenu.isVisible();
    if (usesMobileHeader) await mobileMenu.click();
    await page.getByRole('button', { name: usesMobileHeader ? '退出登录' : '退出', exact: true }).click();
    await expect(page.getByPlaceholder('请输入密码')).toBeVisible();
    expect(await entries()).toEqual([]);
  });
});
