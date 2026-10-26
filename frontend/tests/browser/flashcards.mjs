// Real Vue/Chromium, signed Python API and PG; Java identity/course/media are local fixtures.
import { chromium, expect } from '@playwright/test';
import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { createHash, createHmac, randomUUID } from 'node:crypto';
import { readFile, mkdir, writeFile, stat } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
const root = resolve('.data/p7'), dist = resolve(root, 'dist'), output = resolve(root, 'browser-'+Date.now());
await mkdir(output, { recursive: true });
const secret = 'p7-local-fixture-signing-secret-only-32-bytes';
const course = 'p7-browser-'+randomUUID();
const commands = [], errors = [], forbidden = [], durations = [];
const envelope = data => JSON.stringify({ code: '0', message: 'ok', data });
const server = createServer(async (req, res) => {
  try {
    const path = new URL(req.url, 'http://127.0.0.1').pathname;
    if (path.startsWith('/api/')) {
      let data;
      if (path.endsWith('/events')) { res.writeHead(200, { 'Content-Type': 'text/event-stream' }); res.end(); return; }
      if (path.endsWith('/study/command')) {
        if (req.headers.authorization !== 'Bearer p7-browser-fixture') { res.writeHead(401); res.end(); return; }
        let raw = ''; for await (const chunk of req) raw += chunk;
        const command = JSON.parse(raw); commands.push(command.operation);
        if (!['CREATE_SESSION','GENERATE_CARDS','DUE_CARDS','READ_CARD','REVIEW_CARD','CANCEL'].includes(command.operation)) throw Error('Unexpected command '+command.operation);
        const body = JSON.stringify({ ...command, owner_id: 427, course_id: course, revision: 1 });
        const timestamp = String(Math.floor(Date.now()/1000));
        const hash = createHash('sha256').update(body).digest('hex');
        const signature = createHmac('sha256', secret).update(`lecturelens-study-v1\nPOST\n/internal/v1/study/command\n${timestamp}\n${hash}`).digest('hex');
        const start = performance.now();
        const response = await fetch('http://127.0.0.1:25702/internal/v1/study/command', { method: 'POST', body,
          headers: { 'Content-Type': 'application/json', 'X-LectureLens-Timestamp': timestamp, 'X-LectureLens-Signature': signature } });
        data = await response.json(); durations.push({ operation: command.operation, ms: performance.now()-start });
        res.writeHead(response.status, { 'Content-Type': 'application/json' }); res.end(response.ok ? envelope(data) : JSON.stringify(data)); return;
      }
      if (path.endsWith('/study/status')) data = { enabled: true, revision: 1 };
      else if (path.endsWith('/results')) data = { taskId: course, sourceFullText: 'Binary search halves the remaining interval.', sourceParagraphs: [], translatedFullText: '', translationStatus: 'SUCCEEDED', subtitles: [1,2,3].map(i => ({ segmentIndex:i, startMillis:i*1000, endMillis:(i+1)*1000, language:'en', sourceText:'Binary search halves the remaining interval.' })), translations: [], learningPackage:null, keyframes:[], videoSegments:[], artifacts:[], aiCallRecords:[] };
      else if (path.endsWith('/evidence')) data = { learningScopeVersion:1, revision:1, stale:false, nextCursor:null, items:[1,2,3].map(i=>({ evidenceId:'e'+i, revision:1, sourceType:'SUBTITLE', startMs:i*1000, endMs:(i+1)*1000, normalizedText:'Binary search halves the remaining interval.', retrievable:true })) };
      else if (path.endsWith('/playback-token')) data = { playbackUrl: '/fixture.mp4', expiresAt: '2099-01-01T00:00:00Z' };
      else if (path.endsWith('/embedded-subtitles')) data = { status: 'NOT_FOUND', tracks: [] };
      else if (path.endsWith('/evidence/index-status')) data = { status: 'READY', revision: 1 };
      else if (path.endsWith('/model-usage')) data = { taskId: course, current: null, pipeline: [], qa: [], calls: [] };
      else if (path === '/api/public/runtime-configuration') data = { demoMode: false };
      else if (path === '/api/me') data = { id: 427, email:'mock@example.invalid', role:'USER' };
      else if (/^\/api\/tasks\/[^/]+$/.test(path)) data = { taskId:course, status:'SUCCEEDED', progressPercent:100, currentStage:'DONE', targetLanguage:'zh-CN' };
      else { errors.push('Unknown API '+path); res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'Content-Type':'application/json' }); res.end(envelope(data)); return;
    }
    if (path === '/fixture.mp4') {
      const file = resolve(root,'fixture.mp4'), size = (await stat(file)).size;
      const range = /bytes=(\d+)-(\d*)/.exec(req.headers.range || '');
      const start = range ? Number(range[1]) : 0, end = range?.[2] ? Math.min(Number(range[2]),size-1) : size-1;
      res.writeHead(range ? 206 : 200, { 'Content-Type':'video/mp4', 'Accept-Ranges':'bytes', 'Content-Length':end-start+1,
        ...(range ? { 'Content-Range':`bytes ${start}-${end}/${size}` } : {}) });
      createReadStream(file,{start,end}).pipe(res); return;
    }
    if (path.endsWith('.svg')) {
      const file = resolve(dist,'.'+path);
      if (!file.startsWith(dist+'/')) throw Error('Invalid asset');
      res.writeHead(200, { 'Content-Type':'image/svg+xml' }); res.end(await readFile(file)); return;
    }
    const file = path.startsWith('/assets/') ? resolve(dist, '.'+path) : resolve(dist, 'index.html');
    if (!file.startsWith(dist+'/')) throw Error('Invalid asset');
    res.writeHead(200, { 'Content-Type': ({ '.js':'text/javascript','.css':'text/css','.html':'text/html' })[extname(file)] || 'application/octet-stream' });
    res.end(await readFile(file));
  } catch (e) { errors.push(String(e)); res.writeHead(500); res.end(); }
});
await new Promise(r => server.listen(25703, '127.0.0.1', r));
const origin = 'http://127.0.0.1:25703';
const browser = await chromium.launch({ executablePath:'/opt/google/chrome/chrome', headless:true, args:['--no-sandbox'] });
const checks = [];
try {
  const context = await browser.newContext({ viewport: { width:1440, height:900 } });
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin === origin) return route.continue();
    forbidden.push(route.request().url()); return route.abort();
  });
  await context.addInitScript(() => localStorage.setItem('courselingo.accessToken','p7-browser-fixture'));
  const page = await context.newPage(); page.on('pageerror', e => errors.push(String(e)));
  await page.goto(`${origin}/tasks/${course}?view=flashcards`);
  const panel = page.locator('.flashcards');
  await expect(panel).toContainText('还没有闪卡');
  expect(commands).toEqual(['DUE_CARDS']); checks.push('initial read creates no Run');
  const started = performance.now();
  await panel.getByRole('button', { name:'生成一组证据闪卡' }).click();
  await expect(panel.locator('.card')).toBeVisible();
  const generationMs = performance.now()-started;
  await expect(panel).toContainText('今日待复习 3');
  await panel.getByRole('button', { name:'翻面 · 显示答案' }).click();
  await panel.locator('summary').click();
  await panel.locator('.card').scrollIntoViewIfNeeded();
  await page.screenshot({ path:resolve(output,'1440x900-flipped.png') });
  checks.push('explicit generation and flip with citations');
  const second = await context.newPage(); await second.goto(page.url());
  await expect(second.locator('.flashcards .card')).toBeVisible();
  await second.locator('.flashcards').getByRole('button', { name:'翻面 · 显示答案' }).click();
  await panel.getByRole('button', { name:/^Good/ }).click();
  await expect(panel).toContainText('今日待复习 2');
  await second.locator('.flashcards').getByRole('button', { name:/^Easy/ }).click();
  await expect(second.locator('.flashcards')).toContainText('评分冲突');
  await expect(second.locator('.flashcards')).toContainText('今日待复习 2');
  checks.push('two-tab stale rating conflict preserves one review');
  await page.reload(); await expect(panel).toContainText('今日已复习 1 张');
  await expect(panel).toContainText('今日待复习 2');
  expect(commands.filter(x=>x==='GENERATE_CARDS')).toHaveLength(1);
  checks.push('reload restores server progress without generation');
  await page.setViewportSize({ width:1280, height:800 });
  await panel.getByRole('button', { name:'翻面 · 显示答案' }).click();
  await panel.locator('summary').click();
  await panel.locator('.card').scrollIntoViewIfNeeded();
  await page.screenshot({ path:resolve(output,'1280x800-review.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await panel.getByRole('button', { name:/回看视频/ }).first().click();
  await expect(page.locator('.evidence-reading')).toBeVisible();
  await expect.poll(() => page.locator('video').evaluate(v => v.currentTime)).toBeGreaterThanOrEqual(1);
  expect(commands.filter(x=>x==='GENERATE_CARDS')).toHaveLength(1);
  checks.push('canonical source navigation at both desktop sizes');
  const report = { kind:'MOCK_ONLY_NOT_QUALITY', checks, generationMs, commands, durations, errors, forbidden,
    api:'real Python HMAC API + real PostgreSQL', fixtures:'Java authentication/course; generated local H.264 media', viewports:['1440x900','1280x800'] };
  await writeFile(resolve(output,'results.json'), JSON.stringify(report,null,2)+'\n');
  expect(errors).toEqual([]); expect(forbidden).toEqual([]);
  console.log(JSON.stringify({ output, checks:checks.length, generationMs, errors, forbidden }));
} finally { await browser.close(); await new Promise(r => server.close(r)); }
