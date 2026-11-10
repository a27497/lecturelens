import { chromium, expect } from '../../frontend/node_modules/@playwright/test/index.mjs';
import { writeFile } from 'node:fs/promises';
let input=''; for await (const chunk of process.stdin) input+=chunk;
const config=JSON.parse(input), errors=[], forbidden=[];
const browser=await chromium.launch({executablePath:'/opt/google/chrome/chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
const context=await browser.newContext({viewport:{width:1440,height:1100}});
await context.route('**/*', async route=>{
  const url=new URL(route.request().url());
  if (!['127.0.0.1','localhost'].includes(url.hostname) && !['data:','blob:'].includes(url.protocol)) { forbidden.push(url.origin); return route.abort(); }
  return route.continue();
});
await context.addInitScript(token=>localStorage.setItem('courselingo.accessToken',token),config.token);
const page=await context.newPage();
page.on('pageerror',error=>errors.push(error.message));
try {
  await page.goto(`${config.base}/tasks/${config.task}?view=tutor&layout=classic`);
  const panel=page.locator('section.tutor');
  await expect(panel).toBeVisible();
  await expect(panel.getByText('正在恢复对话…')).toHaveCount(0);
  const ask=async(text,socratic=false)=>{
    await panel.locator('input[type=checkbox]').setChecked(socratic);
    await panel.locator('textarea').fill(text);
    await panel.getByRole('button',{name:'发送',exact:true}).click();
    await expect(panel.locator('textarea')).toHaveValue('');
    await expect(panel.getByText('Tutor 正在查找课程证据…')).toHaveCount(0,{timeout:30000});
  };
  await ask('解释课程异步处理流程，并用初值5、两项任务说明变式；缺少重试细节时说明。');
  await expect(panel.locator('.answer').last()).toContainText('5→6→7');
  await expect(panel.locator('.answer').last()).toContainText('重试细节');
  await expect(panel).toContainText('每轮最多一次生成');
  await panel.locator('details summary').first().click();
  await expect(panel.locator('blockquote').first()).toBeVisible();
  await panel.locator('blockquote button').first().click();
  await expect(page.locator('.timeline-row[data-reference=true]')).toBeVisible(); // Verified source in the actual course view.
  await page.getByRole('button',{name:'返回 Tutor 对话'}).click();
  await ask('最后一步应放在每次处理内还是全部完成后？',true);
  await expect(panel.locator('.answer').last()).toContainText('最后一步');
  await ask('我认为只增加一次，对吗？');
  await expect(panel.locator('.answer').last()).toContainText('初值5');
  const before=await panel.locator('.messages').textContent();
  await page.reload();
  await expect(panel.locator('.messages')).toHaveText(before,{timeout:30000});
  await page.screenshot({path:`${config.out}/browser-restored.png`,fullPage:true});
  await ask('无据问题：请给出课程未覆盖的理论。');
  await expect(panel.locator('.answer').last()).toContainText('没有足够证据');
  await ask('摘录负例：只粘贴原文。');
  await expect(panel).toContainText('TUTOR_SOURCE_ONLY');
  await page.screenshot({path:`${config.out}/browser-stopped.png`,fullPage:true});
  await ask('沿用上述前提，再解释最终值。');
  await expect(panel).toContainText('本对话预算已用完');
  await expect(panel.getByRole('button',{name:'发送',exact:true})).toBeDisabled();
  await page.screenshot({path:`${config.out}/browser-bound.png`,fullPage:true});
  await writeFile(`${config.out}/browser.json`,JSON.stringify({status:'PASS',journey:['explanation','multipart','premises','focused-guidance','followup','source-navigation','reload','insufficient','source-only-stop','six-turn-stop'],errors,forbidden,quality:'NOT_RUN; authored mock'},null,2));
  if (errors.length || forbidden.length) throw Error('Browser errors or non-loopback requests');
} catch(error) {
  await page.screenshot({path:`${config.out}/browser-failure.png`,fullPage:true});
  await writeFile(`${config.out}/browser-failure.json`,JSON.stringify({error:String(error),errors,forbidden},null,2));
  throw error;
} finally {await browser.close();}
