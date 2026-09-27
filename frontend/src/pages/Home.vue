<script setup lang="ts">
import { recruiterDemoEnabled } from "../recruiterDemo";

const github = "https://github.com/a27497/lecturelens";
const evidence = `${github}/blob/main/HUMAN_ACCEPTANCE_REPORT.md#job-search-freeze`;
const courseImage = "/images/lecturelens-course-reading.webp";
const flow = ["Course", "Evidence", "Study Agent", "Practice", "Feedback"];
const demoFlow = ["Ask", "Retrieve Evidence", "Answer", "Practice", "Inspect Trace"];
const highlights = [
  { title: "Evidence & Authority", text: "检索只产生候选。Java Authority 按 owner、course、revision 与删除状态重新核验访问权。" },
  { title: "Recoverable Execution", text: "Run 持久化 checkpoint、预算和幂等工具结果；取消与恢复在明确的执行边界生效。" },
  { title: "Observable Agent", text: "历史 Run 可查看模型调用、工具调用、token、延迟与终态事件，回溯执行链。" },
  { title: "Bounded Agent Tools", text: "CHECK、SEARCH、READ、WINDOW 限定课程读取范围；证据不足时拒答或澄清。" },
];
</script>

<template>
  <main class="landing">
    <section id="product" class="hero page-container" aria-labelledby="home-title">
      <div class="hero__copy">
        <p class="eyebrow">Evidence-grounded Study Agent</p>
        <h1 id="home-title"><span class="hero__brand">LectureLens</span>课程可检索、可引用<br /><span class="hero__agent">Study Agent</span> 每一步有据可查</h1>
        <p class="hero__summary">将课程视频整理为可检索的学习材料，并让 Study Agent 基于课程证据完成解释、练习与反馈。关键执行过程可追踪、可恢复，并受课程权限与版本边界约束。</p>
        <div class="actions">
          <RouterLink class="button button--primary" to="/demo">体验 Sample Course <span aria-hidden="true">↗</span></RouterLink>
          <a class="button button--outline" :href="github" target="_blank" rel="noopener noreferrer">查看 GitHub <span aria-hidden="true">↗</span></a>
        </div>
        <a class="inline-link hero__engineering" href="#engineering">查看工程设计 <span aria-hidden="true">↓</span></a>
      </div>
      <figure class="hero__visual">
        <img :src="courseImage" alt="LectureLens 课程工作区截图：左侧视频，右侧课程阅读区域" width="1280" height="720" />
        <figcaption>LectureLens 课程工作区 · 公开的合成测试数据截图</figcaption>
      </figure>
    </section>

    <section class="section section--line page-container" aria-labelledby="flow-title">
      <div class="section-heading"><p class="eyebrow">The learning loop</p><h2 id="flow-title">从课程内容到学习反馈</h2></div>
      <ol class="flow" aria-label="学习流程">
        <li v-for="(step, index) in flow" :key="step"><span>0{{ index + 1 }}</span><strong>{{ step }}</strong></li>
      </ol>
      <div class="flow-notes">
        <p><strong>课程进入系统</strong><span>字幕、翻译、时间线与学习材料。</span></p>
        <p><strong>Agent 基于 Evidence 工作</strong><span>检索、补读、解释和生成练习；证据不足时拒答或澄清。</span></p>
        <p><strong>学习结果持续保存</strong><span>作答、反馈、Run 和执行历史进入服务端状态。</span></p>
      </div>
    </section>

    <section id="demo" class="section demo-section" aria-labelledby="demo-title">
      <div class="page-container demo-section__inner">
        <div>
          <p class="eyebrow">Recruiter demo · MIT OCW sample course</p>
          <h2 id="demo-title">从一个问题，<br />看完整 Agent 执行链</h2>
          <p class="section-summary">在已准备的公开 Python 课程片段里提出学习目标，检查来源、完成自测，再打开历史 Run 的 Trace。</p>
          <ol class="demo-steps" aria-label="演示路径">
            <li v-for="(step, index) in demoFlow" :key="step"><span>{{ String(index + 1).padStart(2, "0") }}</span>{{ step }}</li>
          </ol>
          <RouterLink class="button button--primary" to="/demo">进入 Sample Course <span aria-hidden="true">↗</span></RouterLink>
          <p v-if="!recruiterDemoEnabled" class="demo-availability">此构建尚未配置 Sample Course；演示页会显示当前状态。</p>
        </div>
        <div class="demo-section__visual">
          <div class="demo-captures">
            <figure class="demo-capture demo-capture--evidence">
              <a href="/images/recruiter-agent-evidence.webp" target="_blank" rel="noopener noreferrer" aria-label="查看 Agent 回答与课程证据截图原尺寸">
                <img src="/images/recruiter-agent-evidence.webp" alt="真实 Sample Course 截图：学习问题、Agent 解释、Evidence ID、英文原文和 00:00:36 视频时间" width="915" height="815" loading="lazy" />
              </a>
              <figcaption>01 / Agent answer + course evidence</figcaption>
            </figure>
            <figure class="demo-capture demo-capture--trace">
              <a href="/images/recruiter-agent-trace.webp" target="_blank" rel="noopener noreferrer" aria-label="查看 Agent Trace 截图原尺寸">
                <img src="/images/recruiter-agent-trace.webp" alt="真实 Agent Trace 截图：Run 状态、模型调用、工具调用、token 和延迟事件" width="838" height="720" loading="lazy" />
              </a>
              <figcaption>02 / Run trace</figcaption>
            </figure>
          </div>
          <p class="visual-caption">真实 Sample Course 验收画面 · 点击截图查看原尺寸。</p>
          <ul class="demo-signals" aria-label="演示中可检查的内容">
            <li>Evidence ID + Video Timestamp</li>
            <li>Insufficient Evidence → Refuse</li>
            <li>Model / Tool / Checkpoint Trace</li>
          </ul>
        </div>
      </div>
    </section>

    <section id="engineering" class="section page-container" aria-labelledby="engineering-title">
      <div class="section-heading section-heading--wide">
        <div><p class="eyebrow">Engineering highlights</p><h2 id="engineering-title">Agent 之外，边界同样重要</h2></div>
        <p>模型选择动作，系统约束权限、预算、版本和终止条件。</p>
      </div>
      <div class="highlights">
        <article v-for="(item, index) in highlights" :key="item.title" class="highlight">
          <span>0{{ index + 1 }}</span><h3>{{ item.title }}</h3><p>{{ item.text }}</p>
        </article>
      </div>
    </section>

    <section class="section architecture-section page-container" aria-labelledby="architecture-title">
      <div class="section-heading"><p class="eyebrow">Architecture</p><h2 id="architecture-title">访问权在 Java，学习任务在 Agent</h2></div>
      <div class="architecture" role="img" aria-label="Vue 工作区经 Java 权限与课程网关访问 Python Study Agent。Java 连接 MySQL、MinIO、RocketMQ、Redis；Agent 连接模型、有界工具和 PostgreSQL。">
        <div class="architecture__main">
          <div class="architecture__node"><small>Browser</small><strong>Vue Workspace</strong><span>课程 · Evidence · 学习记录</span></div>
          <span class="architecture__arrow" aria-hidden="true">↓</span>
          <div class="architecture__node architecture__node--authority"><small>Source of truth for course access</small><strong>Java Authority / Course Gateway</strong><span>owner · course · revision · deleted state</span></div>
          <span class="architecture__arrow" aria-hidden="true">↓</span>
          <div class="architecture__node"><small>Execution</small><strong>Python Study Agent</strong><span>决策 · 工具编排 · Session / Run</span></div>
          <span class="architecture__arrow" aria-hidden="true">↓</span>
          <div class="architecture__node"><small>Persistent state</small><strong>PostgreSQL</strong><span>checkpoint · artifacts · events</span></div>
        </div>
        <div class="architecture__side">
          <div class="architecture__branch"><small>Java services</small><strong>MySQL · MinIO<br />RocketMQ · Redis</strong></div>
          <div class="architecture__branch"><small>Agent dependencies</small><strong>LLM · Bounded Tools</strong><span>CHECK · SEARCH · READ · WINDOW</span></div>
        </div>
      </div>
    </section>

    <section class="section evidence-section" aria-labelledby="evidence-title">
      <div class="page-container evidence-section__inner">
        <div><p class="eyebrow">Engineering evidence</p><h2 id="evidence-title">有记录的工程验证</h2><p class="section-summary">以下为求职版冻结时的本地验收与隔离实验结果，不代表未见课程的教学质量。</p></div>
        <div class="evidence-stats">
          <p><strong>2,067</strong><span>automated tests passed</span></p>
          <p><strong>2,160</strong><span>negative authorization requests · 0 bypass</span></p>
          <p><strong>Verified</strong><span>real-model recruiter flow on a known sample course</span></p>
        </div>
        <a class="inline-link" :href="evidence" target="_blank" rel="noopener noreferrer">View engineering evidence <span aria-hidden="true">↗</span></a>
      </div>
    </section>

    <section class="section final-section page-container" aria-labelledby="final-title">
      <p class="eyebrow">Explore LectureLens</p>
      <h2 id="final-title">从 Sample Course 开始。</h2>
      <div class="actions">
        <RouterLink class="button button--primary" to="/demo">Try Sample Course <span aria-hidden="true">↗</span></RouterLink>
        <a class="button button--outline" :href="github" target="_blank" rel="noopener noreferrer">GitHub <span aria-hidden="true">↗</span></a>
        <a class="inline-link" :href="evidence" target="_blank" rel="noopener noreferrer">Engineering Evidence <span aria-hidden="true">↗</span></a>
      </div>
      <p class="final-section__note">LectureLens 是求职展示用的冻结实验版本，展示基于课程证据、可恢复的 Study Agent；不主张未见课程的教学质量或生产规模并发能力。</p>
    </section>
  </main>
</template>

<style scoped>
.landing { overflow: clip; }
#product, #demo, #engineering { scroll-margin-top: calc(var(--header-height) + 20px); }
.section { padding-top: clamp(72px, 8vw, 116px); padding-bottom: clamp(72px, 8vw, 116px); }
.section--line { border-top: 1px solid var(--color-border); }
.hero { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, .9fr); gap: clamp(28px, 3vw, 48px); align-items: center; min-height: 650px; padding-top: 84px; padding-bottom: 96px; }
.hero__copy { min-width: 0; }
.hero h1 { margin: 22px 0 0; font-size: clamp(35px, 3vw, 43px); line-height: 1.24; letter-spacing: -.045em; font-weight: 720; }
.hero h1 .hero__brand { display: block; margin-bottom: 16px; color: var(--color-brand-strong); font-size: .45em; letter-spacing: -.02em; }
.hero__summary { max-width: 640px; margin: 25px 0 0; color: var(--color-ink-soft); font-size: 17px; line-height: 1.85; }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 32px; }
.button { display: inline-flex; min-height: 48px; align-items: center; justify-content: center; gap: 20px; padding: 0 20px; border: 1px solid var(--color-brand-strong); border-radius: var(--radius-sm); font-size: 14px; font-weight: 700; text-decoration: none; transition: background .18s, color .18s; }
.button--primary { background: var(--color-brand-strong); color: #fff; }.button--primary:hover { background: #194934; }
.button--outline { background: transparent; color: var(--color-brand-strong); }.button--outline:hover { background: var(--color-brand-soft); }
.inline-link { display: inline-flex; gap: 12px; align-items: center; color: var(--color-brand-strong); font-size: 14px; font-weight: 700; text-decoration: none; }.inline-link:hover { text-decoration: underline; text-underline-offset: 4px; }
.hero__engineering { margin-top: 24px; }
.hero__visual { min-width: 0; margin: 0; padding: 10px; border: 1px solid var(--color-border); border-radius: 11px; background: #fff; box-shadow: 0 24px 52px rgb(29 36 33 / 9%); transform: rotate(1deg); }
.hero__visual img { display: block; width: 100%; height: auto; border: 1px solid var(--color-border); border-radius: 4px; }
.hero__visual figcaption, .visual-caption { margin: 11px 2px 2px; color: var(--color-ink-muted); font-size: 11px; line-height: 1.5; }
.section-heading h2 { margin: 13px 0 0; font-size: clamp(30px, 3vw, 42px); line-height: 1.24; letter-spacing: -.035em; }
.flow { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin: 38px 0 0; padding: 0; list-style: none; }
.flow li { position: relative; min-width: 0; padding: 20px 18px 23px; border-top: 2px solid var(--color-brand); background: #fff; }
.flow li:not(:last-child)::after { position: absolute; z-index: 1; top: 34px; right: -13px; color: var(--color-brand); content: '→'; font-size: 18px; }
.flow li span { display: block; margin-bottom: 13px; color: var(--color-brand); font-size: 11px; font-weight: 800; }.flow strong { font-size: 15px; }
.flow-notes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 36px; margin-top: 31px; }.flow-notes p { display: grid; gap: 7px; margin: 0; }.flow-notes strong { font-size: 15px; }.flow-notes span, .section-summary { color: var(--color-ink-soft); font-size: 14px; line-height: 1.8; }
.demo-section { background: #eef2ed; }.demo-section__inner { display: grid; grid-template-columns: minmax(0, .84fr) minmax(0, 1.16fr); align-items: start; gap: clamp(38px, 6vw, 88px); }
.demo-section h2 { margin: 16px 0 20px; font-size: clamp(35px, 3.5vw, 50px); line-height: 1.18; letter-spacing: -.04em; }.demo-section .section-summary { max-width: 440px; }
.demo-steps { display: grid; margin: 26px 0 30px; padding: 0; list-style: none; }.demo-steps li { display: flex; gap: 14px; padding: 8px 0; border-bottom: 1px solid #dce5dd; font-size: 14px; font-weight: 650; }.demo-steps span { color: var(--color-brand); font-size: 12px; }
.demo-availability { max-width: 360px; margin: 13px 0 0; color: var(--color-ink-soft); font-size: 12px; line-height: 1.6; }
.demo-section__visual { min-width: 0; }
.demo-captures { display: grid; gap: 15px; }
.demo-capture { min-width: 0; margin: 0; padding: 8px; border: 1px solid var(--color-border-strong); border-radius: 8px; background: #fff; box-shadow: var(--shadow-low); }
.demo-capture--trace { width: min(100%, 500px); justify-self: end; }
.demo-capture a, .demo-capture img { display: block; width: 100%; }
.demo-capture img { height: auto; border: 1px solid var(--color-border); }
.demo-capture figcaption { padding: 10px 4px 2px; color: var(--color-ink-soft); font-size: 11px; font-weight: 650; letter-spacing: .02em; }
.demo-signals { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 18px 0 0; padding: 0; list-style: none; }.demo-signals li { padding: 9px; border: 1px solid #d5ddd5; color: var(--color-ink-soft); font-size: 11px; font-weight: 650; line-height: 1.5; }
.section-heading--wide { display: flex; align-items: end; justify-content: space-between; gap: 30px; }.section-heading--wide > p { max-width: 320px; margin: 0; color: var(--color-ink-soft); font-size: 14px; line-height: 1.7; }
.highlights { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 36px; border-top: 1px solid var(--color-border-strong); border-bottom: 1px solid var(--color-border-strong); }.highlight { min-width: 0; padding: 26px 22px 32px; }.highlight + .highlight { border-left: 1px solid var(--color-border); }.highlight > span { color: var(--color-brand); font-size: 12px; font-weight: 800; }.highlight h3 { margin: 30px 0 13px; font-size: 18px; letter-spacing: -.025em; }.highlight p { margin: 0; color: var(--color-ink-soft); font-size: 13px; line-height: 1.8; }
.architecture-section { padding-top: 22px; }.architecture { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(0, .72fr); gap: 38px; margin-top: 35px; padding: 36px; border: 1px solid var(--color-border); background: #fff; }.architecture__main { display: grid; }.architecture__node { padding: 15px 20px; border: 1px solid var(--color-border); border-radius: 5px; }.architecture__node--authority { border-color: var(--color-brand); background: var(--color-brand-soft); }.architecture small, .architecture__node span, .architecture__branch span { display: block; color: var(--color-ink-soft); font-size: 12px; line-height: 1.5; }.architecture small { margin-bottom: 5px; color: var(--color-brand); font-weight: 750; text-transform: uppercase; letter-spacing: .04em; }.architecture strong { display: block; font-size: 17px; }.architecture__node span { margin-top: 4px; }.architecture__arrow { justify-self: center; color: var(--color-brand); line-height: 28px; }.architecture__side { display: flex; flex-direction: column; justify-content: space-around; gap: 20px; }.architecture__branch { position: relative; padding: 22px; border: 1px dashed var(--color-border-strong); }.architecture__branch::before { position: absolute; top: 50%; left: -39px; width: 37px; border-top: 1px solid var(--color-border-strong); content: ''; }.architecture__branch span { margin-top: 7px; }
.evidence-section { background: #e8eee8; }.evidence-section__inner { display: grid; grid-template-columns: minmax(0, .8fr) minmax(0, 1.2fr); gap: 24px 70px; align-items: start; }.evidence-section h2 { margin: 12px 0 16px; font-size: 32px; letter-spacing: -.035em; }.evidence-section .section-summary { max-width: 380px; }.evidence-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }.evidence-stats p { margin: 0; padding-top: 17px; border-top: 2px solid var(--color-brand); }.evidence-stats strong { display: block; margin-bottom: 11px; font-size: clamp(20px, 2.2vw, 30px); letter-spacing: -.04em; }.evidence-stats span { color: var(--color-ink-soft); font-size: 12px; line-height: 1.5; }.evidence-section__inner > .inline-link { grid-column: 2; }
.final-section { text-align: center; }.final-section h2 { margin: 12px 0 0; font-size: clamp(32px, 4vw, 48px); letter-spacing: -.04em; }.final-section .actions { justify-content: center; }.final-section__note { max-width: 660px; margin: 42px auto 0; color: var(--color-ink-muted); font-size: 12px; line-height: 1.8; }
@media (max-width: 980px) { .hero { min-height: auto; grid-template-columns: 1fr; padding-top: 68px; }.hero__visual { width: min(100%, 720px); transform: none; }.demo-section__inner { grid-template-columns: 1fr; }.demo-section__visual { max-width: 760px; }.highlights { grid-template-columns: repeat(2, minmax(0, 1fr)); }.highlight:nth-child(3) { border-left: 0; }.highlight:nth-child(n+3) { border-top: 1px solid var(--color-border); } }
@media (max-width: 640px) { .hero__agent { display: block; } }
@media (max-width: 640px) { .section { padding-top: 68px; padding-bottom: 68px; }.hero { gap: 42px; padding-top: 54px; padding-bottom: 68px; }.hero h1 { font-size: clamp(30px, 8vw, 38px); }.hero__summary { font-size: 15px; line-height: 1.75; }.hero .actions, .final-section .actions { align-items: stretch; flex-direction: column; }.hero .button, .final-section .button { width: 100%; }.hero__visual { padding: 6px; }.flow { grid-template-columns: 1fr; gap: 0; }.flow li { display: flex; gap: 16px; align-items: center; padding: 13px 16px; border-top: 0; border-left: 2px solid var(--color-brand); }.flow li:not(:last-child)::after { top: auto; right: auto; bottom: -12px; left: 17px; content: '↓'; }.flow li span { margin: 0; }.flow-notes { grid-template-columns: 1fr; gap: 20px; }.demo-section h2 { font-size: 36px; }.demo-capture--trace { width: 100%; }.demo-signals { grid-template-columns: 1fr; }.section-heading--wide { display: block; }.section-heading--wide > p { margin-top: 18px; }.highlights { grid-template-columns: 1fr; }.highlight { padding: 24px 0; }.highlight + .highlight, .highlight:nth-child(3) { border-top: 1px solid var(--color-border); border-left: 0; }.highlight h3 { margin-top: 14px; }.architecture { display: block; padding: 16px; }.architecture__side { margin-top: 24px; }.architecture__branch::before { display: none; }.evidence-section__inner { grid-template-columns: 1fr; gap: 22px; }.evidence-stats { grid-template-columns: 1fr; }.evidence-stats p { padding-top: 12px; }.evidence-section__inner > .inline-link { grid-column: 1; }.final-section .actions > .inline-link { justify-content: center; padding: 12px; } }
</style>
