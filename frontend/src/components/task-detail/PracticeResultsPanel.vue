<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { studyCommand } from "../../api/study";
import type { PracticeResult, StudyArtifact, StudyFeedbackRun, StudyAttempt } from "../../api/study";
import { mayHaveLostCourseAccess } from "../../api/courseAccess";
import { formatMillisRange } from "../../utils/time";
import type { EvidenceSeekContext } from "./evidenceSeekGuard";
const props = defineProps<{ taskId: string; sessionId: string; runId: string; artifact: StudyArtifact }>();
const emit = defineEmits<{
  observedAttempts: [attempts: StudyAttempt[]];
  open: [index: number, kind: "question" | "history" | "feedback", feedback?: StudyFeedbackRun];
  seek: [milliseconds: number, context: EvidenceSeekContext, index: number]; accessFailure: [];
}>();
const rows = ref<PracticeResult[]>([]);
const loading = ref(false);
const error = ref("");
let generation = 0;
watch(() => [props.taskId, props.runId, props.artifact.artifact_id], () => { generation++; rows.value = []; void load(); }, { immediate: true });
onBeforeUnmount(() => { generation++; });
async function load() {
  const current = ++generation; loading.value = true; error.value = "";
  try {
    const result = await studyCommand(props.taskId, { operation: "READ", session_id: props.sessionId, run_id: props.runId });
    if (current !== generation) return;
    if (result.artifact?.artifact_id !== props.artifact.artifact_id || !result.practice_results) throw new Error("Results unavailable");
    rows.value = result.practice_results;
    emit("observedAttempts", result.attempts ?? rows.value.flatMap(row => row.attempt ? [row.attempt] : []));
  } catch (failure) {
    if (current !== generation) return;
    rows.value = []; error.value = "学习结果暂时无法读取，请重试；已保存记录不受影响。";
    if (mayHaveLostCourseAccess(failure)) emit("accessFailure");
  } finally { if (current === generation) loading.value = false; }
}
function feedbackLabel(row: PracticeResult) {
  if (!row.attempt) return "先保存作答";
  if (!row.feedback_run?.feedback) return "待反馈";
  return row.feedback_run.attempt_id === row.attempt.attempt_id ? `第 ${row.attempt.version} 版反馈` : `已有旧版反馈（第 ${row.feedback_run.answer_version} 版）`;
}
const statusText = { queued: "反馈等待开始", running: "反馈进行中", awaiting_approval: "反馈等待审批", failed: "最近反馈未完成", cancelled: "最近反馈已取消", budget_exceeded: "最近反馈达到上限", succeeded: "" };
</script>
<template>
  <section class="practice-results" aria-label="本次练习结果" aria-live="polite">
    <header><div><h3>本次练习结果</h3><p>来自已保存记录。保存和反馈状态不是成绩；本页草稿不计入结果。</p></div><el-button :loading="loading" @click="load">刷新结果</el-button></header>
    <p v-if="loading" role="status">正在读取练习结果…</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-else-if="!loading && !rows.length">本次尚无可显示的练习结果。</p>
    <article v-for="row in rows" :key="row.question_index" class="result-question">
      <h4>第 {{ row.question_index + 1 }} 题 · {{ artifact.questions[row.question_index]?.question }}</h4>
      <div class="result-status"><strong>{{ row.attempt ? `已保存第 ${row.attempt.version} 版` : '未作答' }}</strong><span>{{ feedbackLabel(row) }}</span><span v-if="row.latest_feedback_status && statusText[row.latest_feedback_status]">{{ row.latest_feedback_answer_version ? `第 ${row.latest_feedback_answer_version} 版 · ` : '' }}{{ statusText[row.latest_feedback_status] }}</span></div>
      <p v-if="row.feedback_run?.feedback">{{ row.feedback_run.feedback.note ? (row.feedback_run.feedback.note.disposition === 'disputed' ? '已记录异议' : '已记录核对') : '待核对' }}<span v-if="row.feedback_run.feedback.note"> · 核对记录第 {{ row.feedback_run.feedback.note.version }} 版</span>；核对仅代表你的记录，不证明答案正确。</p>
      <div class="result-actions"><el-button @click="$emit('open', row.question_index, 'question')">{{ row.attempt ? '返回本题 / 修订' : '开始作答' }}</el-button><el-button v-if="row.attempt" @click="$emit('open', row.question_index, 'history')">答案版本</el-button><el-button v-if="row.feedback_run?.feedback" @click="$emit('open', row.question_index, 'feedback', row.feedback_run)">查看对应反馈</el-button></div>
      <details v-if="row.feedback_run?.feedback?.content.citations.length"><summary>核对反馈的课程来源</summary><div v-for="citation in row.feedback_run.feedback.content.citations" :key="citation.evidence_id" class="result-source"><p>{{ citation.text }}</p><el-button @click="$emit('seek', citation.start_ms, { evidenceId: citation.evidence_id, revision: artifact.revision }, row.question_index)">{{ formatMillisRange(citation.start_ms, citation.end_ms) }} · 查证来源</el-button></div></details>
    </article>
  </section>
</template>
<style scoped>
.practice-results { display: grid; gap: 16px; }.practice-results header { display: flex; align-items: start; justify-content: space-between; gap: 12px; }.practice-results h3,.practice-results h4,.practice-results p { margin: 0; }header p,.result-question > p { color: var(--color-ink-soft); font-size: 13px; line-height: 1.7; margin-top: 8px; }
.result-question { padding: 18px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-canvas); }.result-question h4 { font-size: 15px; line-height: 1.7; }.result-status,.result-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; align-items: center; }.result-status strong { color: var(--color-brand); }.result-status span { color: var(--color-ink-soft); font-size: 13px; }.result-question details { margin-top: 12px; }.result-question summary { color: var(--color-brand); cursor: pointer; }.result-source { margin-top: 12px; font-size: 13px; line-height: 1.7; }.result-source p { white-space: pre-wrap; }
</style>
