// Real HTTP only; synthetic account/material and actual product Mock generator/grader.
import {chromium,expect} from '../../frontend/node_modules/@playwright/test/index.mjs';
import {mkdir,writeFile} from 'node:fs/promises';
const {PREVIEW_URL:origin,PREVIEW_TASK:task,PREVIEW_EMAIL:email,PREVIEW_PASSWORD:password,PREVIEW_EVIDENCE:out,PREVIEW_SHA:sha,PREVIEW_DIRTY:sourceDirty}=process.env;
await mkdir(out+'/screenshots',{recursive:true});
const checks=[],requests=[],snapshots=[],errors=[],blocked=[],pending=[];
let phase='before-submission';
const browser=await chromium.launch({executablePath:'/opt/google/chrome/chrome',headless:true,chromiumSandbox:true});
const context=await browser.newContext({viewport:{width:1440,height:900},timezoneId:'Asia/Shanghai'});
await context.route('**/*',route=>{const u=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(u.hostname)||['data:','blob:'].includes(u.protocol))return route.continue();blocked.push(u.origin);return route.abort()});
const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
page.on('response',r=>{if(r.url().includes('/study/')&&r.request().method()==='POST'){
 const operation=r.request().postDataJSON()?.operation,atPhase=phase;
 requests.push({operation,status:r.status(),phase:atPhase,path:new URL(r.url()).pathname});
 const promise=(async()=>{if(r.ok()){const body=await r.json();snapshots.push({operation,phase:atPhase,data:body.data})}})();pending.push(promise);
}});
const current=page.locator('.practice-question.is-current'),choice=current.locator('.practice-choice'),result=choice.locator('.choice-result'),entry=page.getByRole('region',{name:'继续本次练习',exact:true});
const nav=name=>page.getByRole('navigation',{name:'课程内容导航'}).getByRole('button',{name,exact:true});
const shot=async name=>{await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:out+'/screenshots/'+name+'.png',fullPage:true});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)};
const step=async(name,fn)=>{console.log(name);await fn();checks.push(name)};
let status='FAIL',failure,correctId;
try{
 await step('01 real login and explicit mock choice generation',async()=>{
  await page.goto(origin+'/login');await page.getByPlaceholder('you@example.com').fill(email);await page.getByPlaceholder('请输入密码').fill(password);await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page).toHaveURL(origin+'/tasks');
  await page.goto(origin+'/tasks/'+task);await expect(page.locator('.agent-panel')).toBeVisible({timeout:30000});
  await page.getByRole('combobox',{name:'练习形式',exact:true}).selectOption('choice');await page.getByRole('textbox',{name:'学习目标',exact:true}).fill('练习辨认课程原文，并用自己的话解释。');await page.getByRole('button',{name:'解释并出题',exact:true}).click();
  await expect(choice.getByRole('radio')).toHaveCount(3,{timeout:60000});await expect(result).toHaveCount(0);await shot('01-generated-private-key-hidden');
 });
 await step('02 no selection means no judgment; explicit ANSWERS cannot leak the key',async()=>{
  const count=requests.filter(r=>r.operation==='SAVE_ATTEMPT').length;await expect(choice.getByRole('button',{name:'提交并判分',exact:true})).toBeDisabled();await expect(choice).toContainText('尚未选择，未判分');expect(requests.filter(r=>r.operation==='SAVE_ATTEMPT').length).toBe(count);
  const answersResponse=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/study/')&&r.request().postDataJSON()?.operation==='ANSWERS');await page.getByRole('button',{name:'查看参考答案与自查要点',exact:true}).click();expect((await answersResponse).status()).toBe(200);await Promise.all(pending);await expect(page.getByRole('button',{name:'查看参考答案与自查要点',exact:true})).toHaveCount(0);
  const reads=snapshots.filter(s=>s.data?.artifact?.questions?.[0]?.kind==='choice');expect(reads.length).toBeGreaterThan(0);const state=reads.at(-1).data;
  const status=await page.evaluate(async({task,state})=>{
   const response=await fetch(`/api/tasks/${task}/study/command`,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+localStorage.getItem('courselingo.accessToken')},body:JSON.stringify({operation:'SAVE_ATTEMPT',session_id:state.run.session_id,run_id:state.run.run_id,artifact_id:state.artifact.artifact_id,question_index:0,request_key:'p9-empty-selection',expected_version:0})});return response.status;
  },{task,state});expect(status).toBe(400);
  await page.reload();await expect(choice.getByRole('radio')).toHaveCount(3,{timeout:30000});await expect(result).toHaveCount(0);await Promise.all(pending);
  const before=snapshots.filter(s=>s.phase==='before-submission');expect(before.some(s=>s.operation==='ANSWERS')).toBe(true);for(const s of before)expect(JSON.stringify(s.data)).not.toContain('correct_option_id');expect(before.filter(s=>s.data?.attempts).every(s=>s.data.attempts.length===0)).toBe(true);
  await shot('02-blank-still-ungraded');
 });
 await step('03 wrong selection is graded by program and reveals the correct item and Evidence',async()=>{
  phase='after-submission';await choice.getByRole('radio',{name:/本题没有可引用的课程资料/}).check();await choice.getByRole('button',{name:'提交并判分',exact:true}).click();await expect(result.getByRole('heading')).toHaveText('第 1 版 · 错误');
  correctId=(await result.locator('.correct-option').innerText()).match(/正确选项：([A-Z])/)[1];await expect(result.locator('blockquote')).toContainText('asynchronous');await shot('03-wrong-and-revealed');
  await result.getByRole('button',{name:/回看判分依据/}).first().click();await expect(page.locator('.timeline-row[data-reference=true]')).toHaveCount(1);await shot('03-evidence-location');
  await page.getByRole('button',{name:'返回当前学习任务',exact:true}).click();await expect(result.getByRole('heading')).toHaveText('第 1 版 · 错误');
 });
 await step('04 reload preserves wrong result; changed correct selection saves a new correct version',async()=>{
  await page.reload();await expect(result.getByRole('heading')).toHaveText('第 1 版 · 错误',{timeout:30000});await shot('04-wrong-restored');
  await choice.locator(`input[value="${correctId}"]`).check();await expect(result).toContainText('当前选择尚未提交');await choice.getByRole('button',{name:'提交并判分',exact:true}).click();await expect(result.getByRole('heading')).toHaveText('第 2 版 · 正确');await page.reload();await expect(result.getByRole('heading')).toHaveText('第 2 版 · 正确',{timeout:30000});
  await choice.getByRole('button',{name:'修改记录',exact:true}).click();await expect(choice.locator('.answer-history')).toContainText('第 1 版');await expect(choice.locator('.answer-history')).toContainText('错误');await expect(choice.locator('.answer-history')).toContainText('第 2 版');await shot('04-correct-restored-and-history');
 });
 await step('05 continuation skips graded choice; open answer remains text plus optional feedback',async()=>{
  await expect(entry.getByRole('button',{name:'继续第 2 题作答',exact:true})).toBeVisible();await entry.getByRole('button',{name:'继续第 2 题作答',exact:true}).click();await expect(current.locator('.practice-answer textarea')).toBeVisible();
  await current.locator('.practice-answer textarea').fill('The synthetic course describes an asynchronous video learning pipeline.');await current.getByRole('button',{name:'保存作答',exact:true}).click();await expect(current.locator('.answer-actions')).toContainText('已保存第 1 版');await expect(current.locator('.choice-result')).toHaveCount(0);
  const feedback=current.locator('.practice-feedback');await feedback.getByRole('button',{name:'获取证据反馈',exact:true}).click();await expect(feedback.getByRole('heading',{name:/第 1 版作答的证据反馈/})).toBeVisible({timeout:60000});await expect(current.locator('.choice-result')).toHaveCount(0);
  await feedback.locator('summary').filter({hasText:'核对或更正反馈'}).click();await feedback.getByRole('textbox',{name:'反馈核对意见',exact:true}).fill('Synthetic source check only; no grade or mastery claim.');await feedback.locator('select').last().selectOption('acknowledged');await feedback.getByRole('button',{name:'保存核对意见',exact:true}).click();await expect(entry.getByRole('button',{name:'回看练习结果',exact:true})).toBeVisible();
  await Promise.all(pending);const savedOpen=snapshots.filter(s=>s.data?.attempt?.question_index===1).at(-1).data.attempt;expect(savedOpen).not.toHaveProperty('choice_result');expect(savedOpen).not.toHaveProperty('selected_option_id');await shot('05-open-text-feedback-and-completion');
 });
 await step('06 Tutor and flashcards coexist; saved choice result survives their navigation',async()=>{
  await nav('Tutor 对话').click();await page.getByRole('textbox',{name:'向课程 Tutor 提问',exact:true}).fill('Explain the asynchronous course pipeline.');await page.getByRole('button',{name:'发送',exact:true}).click();await expect(page.locator('.tutor .answer')).toBeVisible({timeout:45000});await shot('06-tutor');
  await nav('闪卡复习').click();await page.getByRole('button',{name:'生成一组证据闪卡',exact:true}).click();await expect(page.locator('.flashcards .card')).toBeVisible({timeout:45000});await page.getByRole('button',{name:'翻面 · 显示答案',exact:true}).click();await expect(page.locator('.flashcards .card .answer')).toBeVisible();await shot('06-flashcards');
  await nav('解释与练习').click();await expect(entry.getByRole('button',{name:'回看练习结果',exact:true})).toBeVisible();await page.getByRole('navigation',{name:'练习题目'}).getByRole('button',{name:/第 1 题/}).click();await expect(result.getByRole('heading')).toHaveText('第 2 版 · 正确',{timeout:30000});await expect(entry.getByRole('button',{name:'回看练习结果',exact:true})).toBeVisible();await page.setViewportSize({width:1280,height:800});await page.reload();await expect(result.getByRole('heading')).toHaveText('第 2 版 · 正确',{timeout:30000});await expect(nav('Tutor 对话')).toBeVisible();await expect(nav('闪卡复习')).toBeVisible();await shot('06-1280-choice-restored');
 });
 expect(errors).toEqual([]);expect(blocked).toEqual([]);expect(requests.filter(r=>r.status!==200)).toEqual([expect.objectContaining({operation:'SAVE_ATTEMPT',status:400})]);status='PASS';
}catch(error){failure=String(error);console.error(failure);await shot('failure').catch(()=>{})}
finally{await Promise.allSettled(pending);await writeFile(out+'/browser-results.json',JSON.stringify({sha,sourceDirty:sourceDirty==='true',status,failure,checks,requests,snapshots,errors,blocked,httpFixtures:false,realChain:'Vue -> Java -> Python -> independent MySQL/PostgreSQL',mode:'mock'},null,2));await browser.close()}
if(status!=='PASS')process.exitCode=1;
