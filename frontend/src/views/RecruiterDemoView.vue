<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { recruiterDemo, recruiterDemoEnabled } from "../recruiterDemo";
import { toReadableAuthError } from "../api/auth";
const auth = useAuthStore();
const router = useRouter();
const busy = ref(false);
const error = ref("");
async function enter() {
  if (busy.value || !recruiterDemoEnabled) return;
  busy.value = true; error.value = "";
  try {
    await auth.login({ email: recruiterDemo.email, password: recruiterDemo.password });
    await router.push(`/tasks/${encodeURIComponent(recruiterDemo.taskId)}`);
  } catch (failure) { error.value = toReadableAuthError(failure); }
  finally { busy.value = false; }
}
</script>
<template>
  <main class="demo page-container">
    <p class="eyebrow">LectureLens · Recruiter Demo</p>
    <h1>从课程证据到解释、练习与反馈</h1>
    <p class="intro">无需上传。打开已准备的 Python 公开课程片段，给学习助手一个目标，检查引用，再完成一次自测。</p>
    <p class="flow">Question → Agent → Evidence → Answer → View Trace</p>
    <section aria-labelledby="sample-title">
      <h2 id="sample-title">Sample Course · 字符串不可变与变量重新绑定</h2>
      <p>Ana Bell · MIT OpenCourseWare · 6.0001 Fall 2016 · Lecture 3，11:00–12:57 片段。</p>
      <p><a href="https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/resources/lecture-3-string-manipulation-guess-and-check-approximations-bisection/" target="_blank" rel="noopener noreferrer">课程来源</a> · <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-NC-SA 4.0</a>。视频已剪辑、重编码并嵌入字幕；中文翻译由模型生成。</p>
      <el-button v-if="recruiterDemoEnabled" type="primary" size="large" :loading="busy" @click="enter">进入 Sample Course</el-button>
      <p v-else role="status">此部署尚未配置 Sample Course。请使用维护者提供的演示入口。</p>
      <p v-if="recruiterDemoEnabled" class="note">使用共享演示账号登录；会切换当前登录身份。仅用于公开课程演示，请勿填写个人信息。其他访客可看到演示作答。</p>
      <p v-if="error" role="alert">{{ error }}</p>
    </section>
    <ol>
      <li><strong>解释概念</strong>：选中示例目标，点击「解释并出题」。</li>
      <li><strong>核对 Evidence</strong>：展开「查看课程证据」，检查 Evidence ID、原文与视频时间。</li>
      <li><strong>测试边界</strong>：选择课程外问题，观察证据不足时的拒答或澄清。</li>
      <li><strong>作答与反馈</strong>：完成一道题、保存作答，再点击「获取证据反馈」。</li>
      <li><strong>View Trace</strong>：查看当前或历史 Run 的模型调用、工具和终态事件。</li>
    </ol>
    <p class="note">实验阶段 Study Agent，使用真实模型。反馈用于自查，不是自动评分。调用可能失败，页面保留失败状态和历史记录。</p>
  </main>
</template>
<style scoped>
.demo { max-width: 920px; padding-top: 52px; padding-bottom: 64px; }
h1 { font-size: clamp(28px, 5vw, 44px); line-height: 1.25; }
.intro, li { line-height: 1.9; }.flow { overflow-wrap: anywhere; color: var(--color-primary); }
section { padding: 24px; margin: 28px 0; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); }
section p { line-height: 1.8; }.note { color: var(--color-ink-soft); font-size: 14px; line-height: 1.8; } li { padding: 5px 0; }
</style>
