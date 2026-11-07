// Real HTTP only; synthetic account/material and actual product Mock generator/grader.
import {chromium,expect} from '../../frontend/node_modules/@playwright/test/index.mjs';
import {mkdir,writeFile} from 'node:fs/promises';
const {PREVIEW_URL:origin,PREVIEW_TASK:task,PREVIEW_EMAIL:email,PREVIEW_PASSWORD:password,PREVIEW_EVIDENCE:out,PREVIEW_SHA:sha,PREVIEW_DIRTY:sourceDirty}=process.env;
await mkdir(out+'/screenshots',{recursive:true});
const tutorRequests=[],tutorSnapshots=[],transportFaults=[],mediaProof=[];
const checks=[],requests=[],snapshots=[],errors=[],blocked=[],pending=[],bodyReadFailures=[];
let phase='before-submission';
const browser=await chromium.launch({executablePath:'/opt/google/chrome/chrome',headless:true,chromiumSandbox:true});
const context=await browser.newContext({viewport:{width:1440,height:900},timezoneId:'Asia/Shanghai'});
await context.route('**/*',route=>{const u=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(u.hostname)||['data:','blob:'].includes(u.protocol))return route.continue();blocked.push(u.origin);return route.abort()});
const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
page.on('request',r=>{if(r.url().includes('/tutor/')&&r.method()==='POST')tutorRequests.push({path:new URL(r.url()).pathname,body:r.postDataJSON()})});
page.on('response',r=>{if(r.url().includes('/tutor/')&&r.ok())pending.push(r.json().then(body=>tutorSnapshots.push({path:new URL(r.url()).pathname,data:body.data})).catch(error=>bodyReadFailures.push({operation:'TUTOR_READ',reason:String(error)})))});
page.on('response',r=>{if(r.url().includes('/study/')&&r.request().method()==='POST'){
 const operation=r.request().postDataJSON()?.operation,atPhase=phase;
 requests.push({operation,status:r.status(),phase:atPhase,path:new URL(r.url()).pathname});
 const promise=(async()=>{if(r.ok()){const body=await r.json();snapshots.push({operation,phase:atPhase,data:body.data})}})().catch(error=>{bodyReadFailures.push({operation,phase:atPhase,reason:String(error)})});pending.push(promise);
}});
const current=page.locator('.practice-question.is-current'),choice=current.locator('.practice-choice'),result=choice.locator('.choice-result'),entry=page.getByRole('region',{name:'继续本次练习',exact:true});
const nav=name=>page.getByRole('navigation',{name:'课程内容导航'}).getByRole('button',{name,exact:true});
const shot=async name=>{await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:out+'/screenshots/'+name+'.png',fullPage:true});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)};
const step=async(name,fn)=>{console.log(name);await fn();checks.push(name)};
let status='FAIL',failure,correctId,originalSession;
const review=page.getByRole('region',{name:'答错待回看',exact:true});
const openReview=async()=>{await expect(review).toBeVisible({timeout:30000});if(await review.getByRole('button',{name:'答错待回看',exact:true}).count())await review.getByRole('button',{name:'答错待回看',exact:true}).click();await expect(review.locator('.judgment-counts')).toBeVisible();await Promise.all(pending)};
const restoreOriginal=async()=>{await expect(review).toBeVisible({timeout:30000});const history=page.locator('.learning-history');await expect(history).toBeVisible();if(!await history.evaluate(element=>element.open))await history.locator(':scope > summary').click();await history.locator('select').selectOption(originalSession);await expect(choice.getByRole('radio')).toHaveCount(3,{timeout:30000});await page.getByRole('navigation',{name:'练习题目'}).getByRole('button',{name:/第 1 题/}).click()};
try{
 await step('01 real login and explicit mock choice generation',async()=>{
  await page.goto(origin+'/login');await page.getByPlaceholder('you@example.com').fill(email);await page.getByPlaceholder('请输入密码').fill(password);await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page).toHaveURL(origin+'/tasks');
  await expect(page.locator('.course-item')).toHaveCount(1);await page.getByRole('button',{name:'进入学习',exact:true}).click();await expect(page).toHaveURL(origin+'/tasks/'+task);await expect(page.locator('.agent-panel')).toBeVisible({timeout:30000});
  await page.getByRole('combobox',{name:'练习形式',exact:true}).selectOption('choice');await page.getByRole('textbox',{name:'学习目标',exact:true}).fill('练习辨认课程原文，并用自己的话解释。');await page.getByRole('button',{name:'解释并出题',exact:true}).click();
  await expect(choice.getByRole('radio')).toHaveCount(3,{timeout:60000});await expect(result).toHaveCount(0);await openReview();await expect(review).toContainText('正确 0 · 错误 0');await expect(review).toContainText('暂无答错待回看的选择题');await shot('01-generated-private-key-hidden');
 });
 await step('02 no selection means no judgment; explicit ANSWERS cannot leak the key',async()=>{
  const count=requests.filter(r=>r.operation==='SAVE_ATTEMPT').length;await expect(choice.getByRole('button',{name:'提交并判分',exact:true})).toBeDisabled();await expect(choice).toContainText('尚未选择，未判分');expect(requests.filter(r=>r.operation==='SAVE_ATTEMPT').length).toBe(count);
  const answersResponse=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/study/')&&r.request().postDataJSON()?.operation==='ANSWERS');await page.getByRole('button',{name:'查看参考答案与自查要点',exact:true}).click();expect((await answersResponse).status()).toBe(200);await Promise.all(pending);await expect(page.getByRole('button',{name:'查看参考答案与自查要点',exact:true})).toHaveCount(0);
  const reads=snapshots.filter(s=>s.data?.artifact?.questions?.[0]?.kind==='choice');expect(reads.length).toBeGreaterThan(0);const state=reads.at(-1).data;
  const status=await page.evaluate(async({task,state})=>{
   const response=await fetch(`/api/tasks/${task}/study/command`,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+localStorage.getItem('courselingo.accessToken')},body:JSON.stringify({operation:'SAVE_ATTEMPT',session_id:state.run.session_id,run_id:state.run.run_id,artifact_id:state.artifact.artifact_id,question_index:0,request_key:'p10-empty-selection',expected_version:0})});return response.status;
  },{task,state});expect(status).toBe(400);
  await Promise.all(pending);await page.reload();await expect(choice.getByRole('radio')).toHaveCount(3,{timeout:30000});await expect(result).toHaveCount(0);await Promise.all(pending);
  const before=snapshots.filter(s=>s.phase==='before-submission');expect(before.some(s=>s.operation==='ANSWERS')).toBe(true);for(const s of before)expect(JSON.stringify(s.data)).not.toContain('correct_option_id');expect(before.filter(s=>s.data?.attempts).every(s=>s.data.attempts.length===0)).toBe(true);
  await shot('02-blank-still-ungraded');
 });
 await step('03 wrong selection is graded by program and reveals the correct item and Evidence',async()=>{
  phase='after-submission';await choice.getByRole('radio',{name:/本题没有可引用的课程资料/}).check();await choice.getByRole('button',{name:'提交并判分',exact:true}).click();await expect(result.getByRole('heading')).toHaveText('第 1 版 · 错误');
  correctId=(await result.locator('.correct-option').innerText()).match(/正确选项：([A-Z])/)[1];await expect(result.locator('blockquote')).toContainText('asynchronous');await shot('03-wrong-and-revealed');
  await result.getByRole('button',{name:/回看判分依据/}).first().click();await expect(page.locator('.timeline-row[data-reference=true]')).toHaveCount(1);await shot('03-evidence-location');
  await page.getByRole('button',{name:'返回当前学习任务',exact:true}).click();await expect(result.getByRole('heading')).toHaveText('第 1 版 · 错误');
 });
 await step('03a wrong review survives another Session, reload and Evidence navigation',async()=>{
  await openReview();await expect(review).toContainText('正确 0 · 错误 1');await expect(review.locator('.review-item')).toHaveCount(1);await expect(review).toContainText('每题仅统计最新已提交版本');await expect(review).toContainText('不是掌握程度');await Promise.all(pending);
  originalSession=snapshots.filter(s=>s.operation==='CHOICE_REVIEW'&&s.data?.items?.length).at(-1).data.items[0].session_id;
  await shot('03a-cross-session-review-before-switch');
  await page.locator('.new-study-goal > summary').click();await page.getByRole('button',{name:'新会话',exact:true}).click();await expect(page.getByRole('textbox',{name:'学习目标',exact:true})).toHaveValue('');
  await page.getByRole('combobox',{name:'练习形式',exact:true}).selectOption('open');await page.getByRole('textbox',{name:'学习目标',exact:true}).fill('用新的会话解释课程异步处理步骤。');await page.getByRole('button',{name:'解释并出题',exact:true}).click();await expect(current.locator('.practice-answer textarea')).toBeVisible({timeout:60000});
  await Promise.all(pending);const newest=snapshots.filter(s=>s.data?.run?.status==='succeeded'&&s.data?.artifact?.questions?.length).at(-1).data.run;expect(newest.session_id).not.toBe(originalSession);
  await openReview();await expect(review).toContainText('正确 0 · 错误 1');await expect(review.locator('.review-item')).toHaveCount(1);await shot('03b-review-from-another-session');
  await Promise.all(pending);await page.reload();await expect(page.locator('.agent-panel')).toBeVisible({timeout:30000});await openReview();await expect(review).toContainText('正确 0 · 错误 1');
  await review.getByRole('button',{name:/回看课程原文/}).first().click();await expect(page.locator('.timeline-row[data-reference=true]')).toHaveCount(1);await shot('03c-review-evidence-time-location');await page.getByRole('button',{name:'返回当前学习任务',exact:true}).click();await openReview();
  await review.getByRole('button',{name:'打开原题与作答',exact:true}).click();await expect(result.getByRole('heading')).toHaveText('第 1 版 · 错误',{timeout:30000});await shot('03d-original-question-restored');
 });
 await step('04 reload preserves wrong result; changed correct selection saves a new correct version',async()=>{
  await Promise.all(pending);await page.reload();await restoreOriginal();await expect(result.getByRole('heading')).toHaveText('第 1 版 · 错误',{timeout:30000});await openReview();await expect(review).toContainText('错误 1');await shot('04-wrong-restored');
  await choice.locator(`input[value="${correctId}"]`).check();await expect(result).toContainText('当前选择尚未提交');await choice.getByRole('button',{name:'提交并判分',exact:true}).click();await expect(result.getByRole('heading')).toHaveText('第 2 版 · 正确');await expect(review).toContainText('正确 1 · 错误 0');await expect(review.locator('.review-item')).toHaveCount(0);await expect(review).toContainText('暂无答错待回看的选择题');await shot('04-correct-removes-review-item');await Promise.all(pending);await page.reload();await restoreOriginal();await openReview();await expect(review).toContainText('正确 1 · 错误 0');await expect(result.getByRole('heading')).toHaveText('第 2 版 · 正确',{timeout:30000});
  await choice.getByRole('button',{name:'修改记录',exact:true}).click();await expect(choice.locator('.answer-history')).toContainText('第 1 版');await expect(choice.locator('.answer-history')).toContainText('错误');await expect(choice.locator('.answer-history')).toContainText('第 2 版');await shot('04-correct-restored-and-history');
 });
 await step('05 continuation skips graded choice; open answer remains text plus optional feedback',async()=>{
  await expect(entry.getByRole('button',{name:'继续第 2 题作答',exact:true})).toBeVisible();await entry.getByRole('button',{name:'继续第 2 题作答',exact:true}).click();await expect(current.locator('.practice-answer textarea')).toBeVisible();
  await current.locator('.practice-answer textarea').fill('The synthetic course describes an asynchronous video learning pipeline.');await current.getByRole('button',{name:'保存作答',exact:true}).click();await expect(current.locator('.answer-actions')).toContainText('已保存第 1 版');await expect(current.locator('.choice-result')).toHaveCount(0);
  const feedback=current.locator('.practice-feedback');await feedback.getByRole('button',{name:'获取证据反馈',exact:true}).click();await expect(feedback.getByRole('heading',{name:/第 1 版作答的证据反馈/})).toBeVisible({timeout:60000});await expect(current.locator('.choice-result')).toHaveCount(0);
  await feedback.locator('summary').filter({hasText:'核对或更正反馈'}).click();await feedback.getByRole('textbox',{name:'反馈核对意见',exact:true}).fill('Synthetic source check only; no grade or mastery claim.');await feedback.locator('select').last().selectOption('acknowledged');await feedback.getByRole('button',{name:'保存核对意见',exact:true}).click();await expect(entry.getByRole('button',{name:'回看练习结果',exact:true})).toBeVisible();
  await Promise.all(pending);const savedOpen=snapshots.filter(s=>s.data?.attempt?.question_index===1).at(-1).data.attempt;expect(savedOpen).not.toHaveProperty('choice_result');expect(savedOpen).not.toHaveProperty('selected_option_id');await openReview();await expect(review).toContainText('正确 1 · 错误 0');await shot('05-open-text-feedback-and-completion');
 });
 await step('06 Tutor and flashcards coexist; saved choice result survives their navigation',async()=>{
  await nav('Tutor 对话').click();await page.getByRole('textbox',{name:'向课程 Tutor 提问',exact:true}).fill('Explain the asynchronous course pipeline.');await page.getByRole('button',{name:'发送',exact:true}).click();await expect(page.locator('.tutor .answer')).toBeVisible({timeout:45000});await shot('06-tutor');
  await nav('闪卡复习').click();await page.getByRole('button',{name:'生成一组证据闪卡',exact:true}).click();await expect(page.locator('.flashcards .card')).toBeVisible({timeout:45000});await page.getByRole('button',{name:'翻面 · 显示答案',exact:true}).click();await expect(page.locator('.flashcards .card .answer')).toBeVisible();await page.locator('.flashcards .ratings').getByRole('button',{name:/Good/}).click();await expect(page.locator('.flashcards')).toContainText('评分已保存');await shot('06-flashcards');
  await nav('解释与练习').click();await restoreOriginal();await openReview();await expect(review).toContainText('正确 1 · 错误 0');await expect(entry.getByRole('button',{name:'回看练习结果',exact:true})).toBeVisible();await page.getByRole('navigation',{name:'练习题目'}).getByRole('button',{name:/第 1 题/}).click();await expect(result.getByRole('heading')).toHaveText('第 2 版 · 正确',{timeout:30000});await expect(entry.getByRole('button',{name:'回看练习结果',exact:true})).toBeVisible();await page.setViewportSize({width:1280,height:800});await Promise.all(pending);await page.reload();await restoreOriginal();await openReview();await expect(review).toContainText('正确 1 · 错误 0');await expect(result.getByRole('heading')).toHaveText('第 2 版 · 正确',{timeout:30000});await expect(nav('Tutor 对话')).toBeVisible();await expect(nav('闪卡复习')).toBeVisible();await shot('06-1280-choice-restored');
 });
 await step('07 course reader and actual synthetic video decoding',async()=>{
  // Desktop keeps the reader beside the learning panel; its material tab is mobile-only.
  await expect(page.locator('.timeline-row').first()).toBeVisible();
  const video=page.locator('video');await expect(video).toHaveCount(1);
  await video.evaluate(async v=>{v.muted=true;await v.play()});
  await expect.poll(()=>video.evaluate(v=>v.currentTime)).toBeGreaterThan(0.1);
  mediaProof.push(await video.evaluate(v=>({currentTime:v.currentTime,readyState:v.readyState,width:v.videoWidth,height:v.videoHeight,decodedFrames:v.getVideoPlaybackQuality().totalVideoFrames})));
  await video.evaluate(v=>v.pause());expect(mediaProof[0].decodedFrames).toBeGreaterThan(0);await shot('07-course-reader-and-video');
 });
 await step('08 Tutor follow-up, Socratic feedback, citation and refresh recovery',async()=>{
  await nav('Tutor 对话').click();const tutor=page.locator('.tutor'),answers=tutor.locator('.answer');
  await expect(answers).toHaveCount(1,{timeout:30000});
  await tutor.getByRole('checkbox').check();await tutor.getByRole('textbox').fill('Why does this pipeline use asynchronous processing?');await tutor.getByRole('button',{name:'发送',exact:true}).click();await expect(answers).toHaveCount(2,{timeout:45000});await expect(answers.nth(1)).toContainText('引导思考');
  await tutor.getByRole('checkbox').uncheck();await tutor.getByRole('textbox').fill('I think the course pipeline separates the work into stages.');await tutor.getByRole('button',{name:'发送',exact:true}).click();await expect(answers).toHaveCount(3,{timeout:45000});await expect(answers.nth(2)).toContainText('对你的回复');
  const text=await answers.allTextContents();await answers.nth(2).locator('button.citation').first().click();await expect(page.locator('.timeline-row[data-reference=true]')).toHaveCount(1);await shot('08-tutor-evidence');await page.getByRole('button',{name:'返回当前学习任务',exact:true}).click();await page.reload();await nav('Tutor 对话').click();await expect(answers).toHaveCount(3,{timeout:30000});expect(await answers.allTextContents()).toEqual(text);await shot('08-tutor-history-restored');
 });
 await step('09 lost Tutor response retries the same turn once and restores both conversations',async()=>{
  const tutor=page.locator('.tutor');await Promise.all(pending);const previous=tutorSnapshots.filter(s=>s.data?.turns?.length===3).at(-1).data.session.session_id;
  await tutor.getByRole('button',{name:'新对话',exact:true}).click();
  const fault=async route=>{const r=route.request();if(r.method()==='POST'&&r.url().endsWith('/turns')){await route.fetch();transportFaults.push({kind:'Tutor response lost after real server commit',path:new URL(r.url()).pathname});await page.unroute('**/tutor/sessions/**/turns',fault);await route.abort('failed')}else await route.fallback()};
  await page.route('**/tutor/sessions/**/turns',fault);
  await tutor.getByRole('textbox').fill('Explain the asynchronous course pipeline again.');await tutor.getByRole('button',{name:'发送',exact:true}).click();await expect(tutor.getByRole('alert')).toContainText('发送结果未知');await expect(tutor.getByRole('textbox')).toHaveValue('Explain the asynchronous course pipeline again.');await shot('09-tutor-unknown-outcome');
  await tutor.getByRole('button',{name:'重试同一条消息',exact:true}).click();await expect(tutor.locator('.answer')).toHaveCount(1,{timeout:45000});
  const posts=tutorRequests.filter(r=>r.path.endsWith('/turns')).slice(-2);expect(posts[0]).toEqual(posts[1]);
  await page.reload();await nav('Tutor 对话').click();await expect(tutor.locator('.answer')).toHaveCount(1,{timeout:30000});await tutor.locator('select').selectOption(previous);await expect(tutor.locator('.answer')).toHaveCount(3,{timeout:30000});await shot('09-both-conversations-restored');
 });
 await step('10 flashcard response loss is idempotent; due state survives refresh',async()=>{
  await nav('闪卡复习').click();const cards=page.locator('.flashcards');await expect(cards.locator('.card')).toBeVisible({timeout:30000});
  const summary=await cards.locator('.summary').innerText(),reviewed=Number(summary.match(/今日已复习 (\d+)/)[1]);await cards.getByRole('button',{name:'翻面 · 显示答案',exact:true}).click();await cards.locator('details > summary').click();await cards.getByRole('button',{name:/回看视频/}).first().click();await expect(page.locator('.timeline-row[data-reference=true]')).toHaveCount(1);await shot('10-flashcard-evidence');await page.getByRole('button',{name:'返回当前学习任务',exact:true}).click();
  const fault=async route=>{if(route.request().postDataJSON()?.operation==='REVIEW_CARD'){await route.fetch();transportFaults.push({kind:'flashcard review response lost after real server commit',path:new URL(route.request().url()).pathname});await page.unroute('**/study/command',fault);await route.abort('failed')}else await route.fallback()};await page.route('**/study/command',fault);
  await cards.locator('.ratings').getByRole('button',{name:/Good/}).click();await expect(cards.getByRole('alert')).toContainText('操作未完成');await expect(cards.getByRole('button',{name:'重试上次评分',exact:true})).toBeVisible();await expect(cards.locator('.summary')).toContainText(`今日已复习 ${reviewed+1} 张`);await shot('10-flashcard-unknown-outcome');
  await cards.getByRole('button',{name:'重试上次评分',exact:true}).click();await expect(cards).toContainText('评分已保存');await expect(cards.locator('.summary')).toContainText(`今日已复习 ${reviewed+1} 张`);const final=await cards.locator('.summary').innerText();await page.reload();await nav('闪卡复习').click();await expect(cards.locator('.summary')).toHaveText(final,{timeout:30000});await shot('10-flashcard-progress-restored');
 });
 await step('11 source-check correction is versioned and restored with the original feedback',async()=>{
  await nav('解释与练习').click();await restoreOriginal();await page.getByRole('navigation',{name:'练习题目'}).getByRole('button',{name:/第 2 题/}).click();const feedback=current.locator('.practice-feedback');await expect(feedback.locator('.feedback-note')).toContainText('Synthetic source check only');
  const details=feedback.locator('details').filter({has:page.locator('summary').filter({hasText:'核对或更正反馈'})});if(!await details.evaluate(e=>e.open))await details.locator(':scope > summary').click();
  await feedback.getByRole('textbox',{name:'反馈核对意见',exact:true}).fill('Synthetic correction: compare the feedback with the quoted course statement; this is not a grade.');await details.locator('select').selectOption('disputed');await feedback.getByRole('button',{name:'保存核对意见',exact:true}).click();await expect(feedback.locator('.feedback-note')).toContainText('你已标记反馈不准确');
  await feedback.getByRole('button',{name:'核对记录',exact:true}).click();await expect(feedback).toContainText('第 1 版 · 已核对');await expect(feedback).toContainText('第 2 版 · 反馈不准确');await feedback.getByRole('button',{name:'回看这段课程证据',exact:true}).first().click();await expect(page.locator('.timeline-row[data-reference=true]')).toHaveCount(1);await shot('11-feedback-source');await page.getByRole('button',{name:'返回当前学习任务',exact:true}).click();
  await page.reload();await restoreOriginal();await page.getByRole('navigation',{name:'练习题目'}).getByRole('button',{name:/第 2 题/}).click();await expect(current.locator('.practice-answer textarea')).toHaveValue('The synthetic course describes an asynchronous video learning pipeline.');await expect(feedback.locator('.feedback-note')).toContainText('你已标记反馈不准确',{timeout:30000});await shot('11-feedback-correction-restored');
 });
 expect(sourceDirty).toBe('false');expect(errors).toEqual([]);expect(blocked).toEqual([]);expect(bodyReadFailures.every(e=>['READ','TUTOR_READ'].includes(e.operation)&&/No resource with given identifier|Target.*closed|No data found for resource/.test(e.reason))).toBe(true);expect(requests.filter(r=>r.status!==200)).toEqual([expect.objectContaining({operation:'SAVE_ATTEMPT',status:400})]);status='PASS';
}catch(error){failure=String(error);console.error(failure);await shot('failure').catch(()=>{})}
finally{await Promise.allSettled(pending);await writeFile(out+'/browser-results.json',JSON.stringify({sha,sourceDirty:sourceDirty==='true',status,failure,checks,requests,snapshots,errors,blocked,bodyReadFailures,httpFixtures:false,transportFaults,tutorRequests,tutorSnapshots,mediaProof,realChain:'Vue -> Java -> Python -> independent MySQL/PostgreSQL',mode:'mock'},null,2));await browser.close()}
if(status!=='PASS')process.exitCode=1;
