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

test('answers Round 3 comparison counts and replays the cited course segments', async ({ page, isMobile }) => {
  await page.goto(origin + '/tasks');
  await page.getByRole('button', { name: /继续学习 01:04/ }).click({ timeout: 60_000 });
  if (isMobile) await choose(page, '助手');
  const editor = page.getByRole('textbox', { name: '就本课提问' });
  const lastTurn = page.locator('.tutor--lesson .messages > li').last();
  const source = page.getByRole('region', { name: '课程出处', exact: true });

  for (const { question, answer, sources } of [
    {
      question: '用这个例子找 42 要比较几次',
      answer: /比较 2 次.*先比较 21.*再比较 42/s,
      sources: [['01:04', 64_000, /middle value is twenty-one/], ['01:14', 74_000, /next middle value is forty-two/]],
    },
    {
      question: '比顺序查找快多少',
      answer: /一百万个有序元素.*最多比较约 20 次.*要比较一百万次.*5 万倍/s,
      sources: [['01:36', 96_000, /million sorted items take at most twenty comparisons/]],
    },
  ]) {
    await page.getByRole('button', { name: '新对话', exact: true }).click();
    await editor.fill(question);
    await editor.press('Enter');
    await expect(lastTurn.locator('.learner')).toHaveText(question);
    await expect(lastTurn).toContainText(answer);
    for (const [time, milliseconds, excerpt] of sources) {
      await lastTurn.getByRole('button', { name: '课程出处 ' + time, exact: true }).click();
      await source.locator('summary').click();
      await expect(source.locator('blockquote')).toContainText(excerpt);
      if (evidence && (isMobile ? time === '01:04' : time === '01:36')) {
        await lastTurn.evaluate(turn => turn.scrollIntoView({ block: 'start' }));
        await capture(page, isMobile ? 'tutor-390' : 'tutor-1440');
      }
      await source.getByRole('button', { name: '回看 ' + time, exact: true }).click();
      await expect.poll(() => clock(page)).toBe(milliseconds);
    }
  }
});

test('recognizes Round 3 boundary paraphrases', async ({ page, isMobile }) => {
  let externalRequests = 0;
  await page.route(url => /^https?:$/.test(url.protocol) && url.origin !== origin, route => {
    externalRequests++;
    return route.abort();
  });
  await page.goto(origin + '/tasks');
  await page.getByRole('button', { name: /继续学习 01:04/ }).click({ timeout: 60_000 });
  if (isMobile) await choose(page, '助手');
  const editor = page.getByRole('textbox', { name: '就本课提问' });
  const newChat = page.getByRole('button', { name: '新对话', exact: true });
  const lastTurn = page.locator('.tutor--lesson .messages > li').last();
  const source = page.getByRole('region', { name: '课程出处', exact: true });
  const submit = async question => {
    await editor.fill(question);
    await editor.press('Enter');
    await expect(lastTurn.locator('.learner')).toHaveText(question);
  };

  for (const [name, question, answer, time, excerpt] of [
    ['assignment', '为何在没命中时不能把 low 直接设为 mid？', '会反复比较 3', '02:12', /Setting low to mid would repeat/],
    ['equal-boundaries', '两头刚好碰在同一个格子，需要检查它吗？', '两端指向同一个下标时，要比较这一项。', '01:52', /Equal boundaries mean one candidate is left/],
  ]) {
    await newChat.click();
    await submit(question);
    await expect(lastTurn).toContainText(answer);
    const answerBlock = lastTurn.locator('.answer-block').filter({ hasText: answer });
    if (isMobile) {
      await lastTurn.evaluate(turn => window.scrollBy(0, turn.getBoundingClientRect().top - 309));
      await capture(page, 'qa-' + name + '-mobile');
    }
    await answerBlock.getByRole('button', { name: '课程出处 ' + time, exact: true }).click();
    await source.locator('summary').click();
    await expect(source.locator('blockquote')).toContainText(excerpt);
    await expect(source.getByRole('button', { name: '回看 ' + time, exact: true })).toBeEnabled();
    await source.scrollIntoViewIfNeeded();
    if (isMobile) await source.evaluate(card => window.scrollBy(0, card.getBoundingClientRect().top - 319));
    await capture(page, 'qa-' + name + '-source-' + (isMobile ? 'mobile' : 'desktop'));
  }

  await submit('把high更新成mid 合适吗？两端落在同一个下标呢？');
  await expect(lastTurn).toContainText('应更新为 high = mid − 1');
  await expect(lastTurn).toContainText('两端指向同一个下标时，要比较这一项。');
  await submit('low 等于 mid 行不行？');
  await expect(lastTurn).toContainText('会反复比较 3');
  await submit('二分查找的边界这块我有点不明白，该从哪儿看？');
  await expect(lastTurn).toContainText('你想先弄清怎么移动边界，还是怎么判断是否结束？');
  await expect(lastTurn.getByRole('button', { name: '课程出处 00:48' })).toBeVisible();
  await expect(lastTurn.getByRole('button', { name: '课程出处 01:52' })).toBeVisible();
  await submit('哈希表的装载因子怎么理解？');
  await expect(lastTurn).toContainText('这节课没有足够资料回答这个问题。');
  await expect(lastTurn.getByRole('button', { name: /课程出处/ })).toHaveCount(0);
  expect(externalRequests).toBe(0);
});

test('opens at 01:04 and works through authorized learning actions', async ({ page, browser, isMobile }) => {
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
  const progress = page.getByText('已学 42%', { exact: true });
  for (const pass of ['cold', 'repeat']) {
    await page.goto(origin + '/tasks');
    const open = page.getByRole('button', { name: /继续学习 01:04/ });
    await expect(open).toBeVisible();
    await expect(progress).toBeVisible();
    if (pass === 'cold') {
      await capture(page, 'library-' + formFactor);
      await expect(page.getByRole('radio')).toHaveCount(2);
      const menu = page.getByRole('button', { name: '更多操作' });
      await menu.focus();
      await page.keyboard.press('Enter');
      const models = page.getByRole('menuitem', { name: '模型管理' });
      await expect(models).toBeVisible();
      await expect(page.getByRole('link', { name: '模型管理' })).toHaveCount(0);
      await capture(page, 'library-menu-' + formFactor);
      await page.getByRole('menuitem', { name: '批量管理' }).click();
      await expect(page.getByText('已选择 0 项')).toBeVisible();
      await expect(page.getByRole('button', { name: '删除所选' })).toBeDisabled();
      await page.getByRole('button', { name: '全选当前列表' }).click();
      await expect(page.getByText('已选择 1 项')).toBeVisible();
      await page.getByRole('button', { name: '退出批量管理' }).click();
      await menu.click();
      await models.click();
      await expect(page.getByRole('heading', { name: '模型管理', exact: true })).toBeVisible();
      await page.goto(origin + '/tasks');
      await expect(open).toBeVisible();
    }

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
    await expect(progress).toBeVisible();
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
    await expect(progress).toBeVisible();
    await page.getByRole('button', { name: /走一遍：找到 34/ }).click();
    await expect.poll(() => clock(page)).toBe(64000);
    const scrubber = page.locator('.lesson-scrubber');
    await scrubber.scrollIntoViewIfNeeded();
    const box = await scrubber.boundingBox();
    if (isMobile) await scrubber.tap({ position: { x: box.width * .98, y: box.height / 2 } });
    else {
      const y = box.y + box.height / 2;
      await page.mouse.move(box.x + box.width * (64 / 152), y);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width * .98, y, { steps: 6 });
      await page.mouse.up();
    }
    await expect.poll(() => clock(page)).toBeGreaterThan(145000);
    await expect(progress).toBeVisible();
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
    await expect(progress).toBeVisible();
    await page.getByRole('button', { name: '课程出处 01:04', exact: true }).first().click();
    await expect(source.getByRole('button', { name: '回看 01:04', exact: true })).toBeEnabled();
    await source.getByRole('button', { name: '回看 01:04', exact: true }).click();
    await expect.poll(() => clock(page)).toBe(64000);
    await source.locator('summary').click();
    await expect(source.locator('blockquote')).toBeVisible();
    await expect(source.getByRole('button', { name: '记下这段' })).toHaveCount(0);
    await expect(page.getByText(/正在核对/)).toHaveCount(0);
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

  const visitorQuestion = 'mid 为啥用整除来选左中点？';
  await test.step('answers differently worded and compound questions with verified sources', async () => {
    const select = page.getByRole('combobox', { name: '查看对话' });
    await expect(select.locator('option:not([hidden])')).toHaveText(['为什么可以排除 21？', '边界重合时怎么停？']);
    await page.getByText('更多常见问题', { exact: true }).click();
    await expect(page.locator('.followups__questions button')).toHaveCount(10);
    await page.getByRole('button', { name: '为什么 mid 要向下取整？' }).click();
    const editor = page.getByRole('textbox', { name: '就本课提问' });
    await expect(editor).toHaveValue('为什么 mid 要向下取整？');
    await page.getByRole('button', { name: '新对话' }).click();
    await expect(select.locator('option:not([hidden])')).toHaveCount(2);
    await editor.fill(visitorQuestion);
    const before = postActions.length;
    await cdp.send('Input.imeSetComposition', { text: '中', selectionStart: 1, selectionEnd: 1 });
    await editor.press('Enter');
    expect(postActions).toHaveLength(before);
    await cdp.send('Input.insertText', { text: '中文' });
    await editor.fill(visitorQuestion);
    await editor.press('Enter');
    const messages = page.locator('.tutor--lesson .messages > li');
    await expect(messages.last()).toContainText('偶数个候选时取左边的中点');
    await expect(messages.last()).toContainText('low = 4、high = 5');
    const citation = messages.last().getByRole('button', { name: '课程出处 00:34' });
    await citation.click();
    const source = page.getByRole('region', { name: '课程出处', exact: true });
    await source.locator('summary').click();
    await expect(source.locator('blockquote')).toContainText('rounding the distance down');
    await source.scrollIntoViewIfNeeded();
    if (isMobile) await source.evaluate(card => window.scrollBy(0, card.getBoundingClientRect().top - 319));
    await capture(page, 'new-answer-source-' + formFactor);

    const question1 = '左右边界越过去还要查吗？';
    const question2 = '数据乱序还能划掉半边吗？';
    await editor.fill(question1);
    await editor.press('End');
    const beforeNewline = postActions.length;
    const singleLineHeight = await editor.evaluate(node => node.clientHeight);
    await editor.press('Shift+Enter');
    await page.keyboard.insertText(question2);
    await expect(editor).toHaveValue(question1 + '\n' + question2);
    expect(postActions).toHaveLength(beforeNewline);
    expect(await editor.evaluate(node => node.clientHeight)).toBeGreaterThan(singleLineHeight);
    expect(await editor.evaluate(node => node.scrollHeight)).toBeLessThanOrEqual(await editor.evaluate(node => node.clientHeight + 1));
    await editor.press('Enter');
    await expect(messages.last()).toContainText('边界交叉时没有下标可查');
    await expect(messages.last()).toContainText('有序性给出了排除一侧的理由');
    for (const [question, answer] of [
      ['算 mid 时直接把两个下标相加会怎样？', '先算距离，避免整数相加溢出'],
      ['一堆相同的数里，找到的会是最左边？', '普通查找返回本轮命中的下标'],
      ['能换个数组给我演练一下吗？', '在 [1, 5, 9, 14, 20, 27] 中找 20'],
      ['只剩一个数还要比吗？堆排序怎么实现？', '其余部分在本课中没有找到足够的依据'],
      ['能讲讲图论里的最短路径吗？', '这节课没有足够资料回答这个问题。'],
    ]) {
      await editor.fill(question);
      await editor.press('Enter');
      await expect(messages.last()).toContainText(answer);
    }
  });

  const note = '闭区间边界更新后，中点已经排除。';
  await test.step('save a local note and submit a real practice attempt', async () => {
    await choose(page, '笔记');
    await expect(page.getByText(/中点也要划掉/)).toBeVisible();
    await page.getByRole('textbox', { name: '记录你的理解' }).fill(note);
    await page.getByRole('button', { name: '保存笔记', exact: true }).click();
    await expect(page.getByText(note, { exact: true })).toBeVisible();
    await choose(page, '练习');
    await page.getByRole('button', { name: '下一题', exact: true }).click();
    await expect(page.getByRole('heading', { name: /在 \[2, 7, 11, 18, 29\]/ })).toBeVisible();
    const choices = page.getByRole('radio');
    await expect(page.getByRole('radio', { checked: true })).toHaveCount(0);
    await expect(page.getByRole('article', { name: '选择题判分结果' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '提交答案', exact: true })).toBeDisabled();
    await page.evaluate(() => window.scrollTo(0, 0));
    await capture(page, 'practice-clean-' + formFactor);
    await choices.nth(0).check();
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
      const prior = await choices.nth(0).isChecked();
      await page.reload();
      await page.getByRole('button', { name: '下一题', exact: true }).click();
      expect(await choices.nth(0).isChecked()).toBe(prior);
      await expect(feedback).toBeVisible();
      await choose(page, '助手');
      const history = page.getByRole('combobox', { name: '查看对话' });
      await expect(history.locator('option:not([hidden])')).toContainText([visitorQuestion]);
      await history.selectOption({ label: '为什么可以排除 21？' });
      await expect(page.getByText('比较过的中点也要移出区间')).toBeVisible();
      await history.selectOption({ label: visitorQuestion });
      await expect(page.getByText('偶数个候选时取左边的中点')).toBeVisible();
      await choose(page, '笔记');
      await expect(page.getByText(note, { exact: true })).toBeVisible();
    }
  });

  if (isMobile) await test.step('isolates a fresh browser B from visitor A', async () => {
    const courseA = new URL(page.url()).pathname.split('/')[2];
    const contextB = await browser.newContext({ viewport: page.viewportSize(), locale: 'zh-CN', isMobile: true, hasTouch: true });
    try {
      const fresh = await contextB.newPage();
      await fresh.goto(origin + '/tasks', { timeout: 90_000 });
      await fresh.getByRole('button', { name: /继续学习 01:04/ }).click({ timeout: 90_000 });
      expect(new URL(fresh.url()).pathname.split('/')[2]).not.toBe(courseA);
      const crossAccess = await fresh.evaluate(async course => {
        const token = localStorage.getItem('lecturelens.round3.accessToken');
        const result = await fetch('/api/tasks/' + course + '/evidence/index-status', {
          headers: { Authorization: 'Bearer ' + token },
        });
        return result.status === 200 && String((await result.json()).code) === '0';
      }, courseA);
      expect(crossAccess).toBe(false);
      await choose(fresh, '助手');
      const dropdown = fresh.getByRole('combobox', { name: '查看对话' });
      await expect(dropdown.locator('option:not([hidden])')).toHaveText(['为什么可以排除 21？', '边界重合时怎么停？']);
      await expect(fresh.getByText(visitorQuestion, { exact: true })).toHaveCount(0);
      await expect(dropdown).not.toContainText(visitorQuestion);
      await expect(fresh.getByText('比较过的中点也要移出区间')).toBeVisible();
      await choose(fresh, '笔记');
      await expect(fresh.getByText(/中点也要划掉/)).toBeVisible();
      await expect(fresh.getByText(note, { exact: true })).toHaveCount(0);
      await choose(fresh, '练习');
      await fresh.getByRole('button', { name: '下一题', exact: true }).click();
      await expect(fresh.getByRole('radio', { checked: true })).toHaveCount(0);
      await expect(fresh.getByRole('article', { name: '选择题判分结果' })).toHaveCount(0);
      await expect(fresh.getByRole('button', { name: '提交答案', exact: true })).toBeDisabled();
      await fresh.evaluate(() => window.scrollTo(0, 0));
      await capture(fresh, 'visitor-b-practice-clean-mobile');
    } finally {
      await contextB.close();
    }
  });

  await test.step('shows the same learning progress on the course card after seeking', async () => {
    await page.locator('.lesson-scrubber').press('Home');
    await expect.poll(() => clock(page)).toBe(0);
    await page.getByRole('link', { name: '返回课程库' }).click();
    await expect(progress).toBeVisible();
    await expect(page.getByRole('button', { name: /继续学习 00:00/ })).toBeVisible();
  });

  expect(pageErrors).toEqual([]);
  expect(externalRequests).toEqual([]);
});
