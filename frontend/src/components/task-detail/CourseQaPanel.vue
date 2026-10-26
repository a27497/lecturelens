<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import CourseModelUsagePanel from "./CourseModelUsagePanel.vue";
import { askCourseQa, readCourseQaHistory, getEvidenceIndexStatus, toReadableCourseQaError } from "../../api/qa";
import type { EvidenceIndexStatus } from "../../api/qa";
import type { CourseQaEvidenceItem, CourseQaResponse, CourseQaHistoryItem } from "../../types/qa";
import { formatMillisRange } from "../../utils/time";
import { mayHaveLostCourseAccess } from "../../api/courseAccess";

import type { EvidenceSeekContext } from "./evidenceSeekGuard";

import type { LearningScope } from "../../api/learningScope";
const props = defineProps<{ taskId: string; learningScope?: LearningScope | null }>();
const emit = defineEmits<{ frozenScope: [scope: LearningScope | null | undefined]; seek: [startTimeMillis: number, context: EvidenceSeekContext]; accessFailure: [] }>();
const question = ref("");
const history = ref<CourseQaHistoryItem[]>([]);
const historyCursor = ref<string | null>(null);
const historyLoading = ref(false);
const historyError = ref("");
const selectedQuestion = ref("");
const historySourceStatus = ref("");
let historyGeneration = 0;
let answerSelection = 0;
onBeforeUnmount(() => { historyGeneration++; requestVersion.value++; });
async function loadHistory(more = false, restore = false, revalidate = true) {
  if (more && historyLoading.value) return;
  const current = ++historyGeneration; const task = props.taskId; const selection = answerSelection;
  historyLoading.value = true; historyError.value = "";
  // Until this explicit read succeeds, saved citations are no longer current observations.
  if (!more && revalidate) {
    history.value = history.value.map(item => ({ ...item, evidence: [], sourceStatus: "unavailable" }));
    if (response.value) { response.value = { ...response.value, evidence: [] }; historySourceStatus.value = "unavailable"; }
  }
  try {
    const page = await readCourseQaHistory(task, more ? historyCursor.value ?? undefined : undefined);
    if (current !== historyGeneration || task !== props.taskId) return;
    history.value = [...(more ? history.value : []), ...page.items]; historyCursor.value = page.nextCursor;
    if (!more && revalidate && response.value && !loading.value) {
      const selected = page.items.find(item => item.recordId === response.value?.recordId);
      if (selected) applyHistory(selected);
      // A selected record outside this page keeps its answer, but no trusted sources.
    }
    const recentSuccess = page.items.find(item => item.status === "SUCCEEDED");
    if (restore && !response.value && !loading.value && selection === answerSelection && recentSuccess) selectHistory(recentSuccess, true);
  } catch (error) {
    if (current !== historyGeneration) return;
    const status = (error as { response?: { status?: number } })?.response?.status;
    historyError.value = status === 409 ? "课程版本已变化，请刷新课程后重试；已保存问答不受影响。" : "历史问答暂时无法读取，请重试；已保存问答不受影响。";
    if (response.value) { response.value = { ...response.value, evidence: [] }; historySourceStatus.value = "unavailable"; }
    if (mayHaveLostCourseAccess(error)) { history.value = []; response.value = null; emit("accessFailure"); }
  } finally { if (current === historyGeneration) historyLoading.value = false; }
}
function selectHistory(item: CourseQaHistoryItem, validated = false) {
  if (loading.value) return;
  requestVersion.value++; answerSelection++;
  applyHistory(historyLoading.value && !validated ? { ...item, evidence: [], sourceStatus: "unavailable" } : item);
  emit("frozenScope", undefined);
}
function applyHistory(item: CourseQaHistoryItem) {
  selectedQuestion.value = item.question; historySourceStatus.value = item.sourceStatus;
  response.value = { recordId: item.recordId, answer: item.status === "SUCCEEDED" ? item.answer : "这次提问未形成已保存的回答，可明确重新提问。", evidence: item.evidence, usage: null };
}

const loading = ref(false);
const errorMessage = ref("");
const response = ref<CourseQaResponse | null>(null);
const requestVersion = ref(0);
const indexStatus = ref<EvidenceIndexStatus["status"] | "UNKNOWN">("UNKNOWN");
const indexReady = computed(() => ["DISABLED", "READY"].includes(indexStatus.value));
const indexMessage = computed(() => ({
  UNKNOWN: "正在检查课程资料状态…", DISABLED: "", READY: "课程资料已就绪，可以提问。",
  PENDING: "课程资料等待更新，完成后即可提问。", INDEXING: "正在准备课程资料，完成后即可提问。",
  FAILED: "课程资料更新暂时失败，系统会自动重试。",
})[indexStatus.value]);
const canSubmit = computed(() => props.learningScope !== null && indexReady.value && question.value.trim().length > 0 && question.value.trim().length <= 500 && !loading.value);
const confidenceDetails = computed(() => (response.value?.evidence ?? [])
  .filter((item) => item.confidence !== null)
  .map((item, index) => ({
    key: `${item.sourceType}-${item.sourceId}-${item.startTimeMillis}-${index}`,
    label: item.timeText || formatMillisRange(item.startTimeMillis, item.endTimeMillis),
    value: item.confidence!.toFixed(2),
  })));

watch(() => props.taskId, (taskId, _previous, onCleanup) => {
  clear();
  historyGeneration++; historyLoading.value = false; history.value = []; historyCursor.value = null; historyError.value = "";
  void loadHistory(false, true);
  indexStatus.value = "UNKNOWN";
  let active = true;
  let timer: ReturnType<typeof setTimeout> | undefined;
  onCleanup(() => { active = false; clearTimeout(timer); });
  async function poll() {
    try {
      const status = await getEvidenceIndexStatus(taskId);
      if (active) indexStatus.value = status.status;
    } catch (failure) {
      if (active) { indexStatus.value = "UNKNOWN"; if (mayHaveLostCourseAccess(failure)) emit("accessFailure"); }
    }
    if (active) timer = setTimeout(poll, indexReady.value ? 30_000 : 3_000);
  }
  void poll();
}, { immediate: true });

watch(() => props.learningScope, () => {
  // This selection is for the next question. Preserve a completed answer and its frozen scope;
  // its citations must still pass the existing source-version guard after a refresh.
  requestVersion.value++; loading.value = false; errorMessage.value = "";
}, { deep: true });

async function submit() {
  if (loading.value || !indexReady.value || props.learningScope === null) return;
  const normalized = question.value.trim();
  if (!normalized) { errorMessage.value = "请输入课程问题"; return; }
  if (normalized.length > 500) { errorMessage.value = "问题不能超过 500 个字符"; return; }
  answerSelection++; historyGeneration++; historyLoading.value = false;
  const currentTaskId = props.taskId;
  const version = requestVersion.value + 1;
  requestVersion.value = version;
  loading.value = true;
  errorMessage.value = "";
  response.value = null;
  try {
    const nextResponse = await askCourseQa(currentTaskId, { question: normalized, ...(props.learningScope ? { learning_scope: JSON.parse(JSON.stringify(props.learningScope)) } : {}) });
    if (version === requestVersion.value && props.taskId === currentTaskId) { response.value = nextResponse; selectedQuestion.value = normalized; historySourceStatus.value = ""; void loadHistory(false, false, false); emit("frozenScope", nextResponse.learning_scope ?? null); }
  } catch (error) {
    if (version === requestVersion.value && props.taskId === currentTaskId) { errorMessage.value = toReadableCourseQaError(error); if (mayHaveLostCourseAccess(error)) emit("accessFailure"); }
  } finally {
    if (version === requestVersion.value && props.taskId === currentTaskId) loading.value = false;
  }
}

function clear() {
  answerSelection++;
  requestVersion.value += 1;
  question.value = "";
  loading.value = false;
  errorMessage.value = "";
  response.value = null; selectedQuestion.value = ""; historySourceStatus.value = "";
  emit("frozenScope", undefined);
}

function sourceLabel(sourceType: string): string {
  const labels: Record<string, string> = { VIDEO_SEGMENT: "音画证据", SUBTITLE_TRANSLATION: "字幕译文", SUBTITLE: "字幕", OCR: "画面文字", VISION: "视觉描述" };
  return labels[sourceType] || sourceType || "证据";
}

function evidenceText(item: CourseQaEvidenceItem): string { return item.translatedSnippet || item.snippet; }
function originalText(item: CourseQaEvidenceItem): string {
  return item.translatedSnippet && item.snippet !== item.translatedSnippet ? item.snippet : "";
}
</script>

<template>
  <section class="workspace-panel qa-panel" aria-labelledby="qa-title">
    <header><h2 id="qa-title">课程问答 · Tutor</h2><p>只回答你的课程问题，不自动创建学习任务或练习。已保存问答可从历史恢复；未提交的问题草稿仅保留在本页。</p></header>
    <p v-if="indexMessage" class="index-status" role="status">{{ indexMessage }}</p>
    <div class="qa-form">
      <el-input v-model="question" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="输入与当前课程有关的问题" aria-label="课程问题" @keydown.ctrl.enter.prevent="submit" />
      <div><el-button type="primary" :loading="loading" :disabled="!canSubmit" @click="submit">提问</el-button><el-button :disabled="loading && !response" @click="clear">清空</el-button></div>
    </div>
    <el-alert v-if="errorMessage" :closable="false" :title="errorMessage" type="warning" show-icon />
    <details class="qa-history" open>
      <summary>历史问答 <span>{{ history.length ? `· 已载入 ${history.length} 条` : '' }}</span></summary>
      <div class="history-toolbar"><el-button :loading="historyLoading" @click="loadHistory()">刷新历史</el-button><span v-if="historyLoading" role="status">正在读取已保存问答…</span></div>
      <p v-if="historyError" role="alert">{{ historyError }}</p>
      <p v-else-if="!historyLoading && !history.length">尚无历史问答。输入课程问题后点击“提问”。</p>
      <ol><li v-for="item in history" :key="item.recordId"><button type="button" :disabled="loading" :aria-pressed="response?.recordId === item.recordId" @click="selectHistory(item)">{{ item.question }}<small>{{ item.createdAt ? new Date(item.createdAt).toLocaleString() : '历史记录' }} · {{ item.status === 'SUCCEEDED' ? '已保存回答' : '未完成回答' }}</small></button></li></ol>
      <el-button v-if="historyCursor && history.length < 100" :loading="historyLoading" @click="loadHistory(true)">更早的问答</el-button>
      <p v-if="historyCursor && history.length >= 100">已载入最近100条，可刷新回到最新记录。</p>
    </details>
    <article v-if="response" class="qa-answer" aria-live="polite">
      <h3>回答</h3><strong class="answered-question">{{ selectedQuestion }}</strong>
      <p v-if="historySourceStatus" class="history-help">正在查看已保存问答；学习范围选择用于下一次提问。选择历史不会生成新回答。</p>
      <p v-if="['unavailable', 'partial'].includes(historySourceStatus)" role="status">部分历史来源已失效或版本已变化，不作为当前可信引用展示。</p><p>{{ response.answer }}</p>
      <section class="qa-evidence" aria-labelledby="evidence-title">
        <h3 id="evidence-title">证据</h3>
        <el-empty v-if="response.evidence.length === 0" description="当前课程内容中没有找到明确依据" />
        <template v-else>
          <article v-for="item in response.evidence" :key="`${item.sourceType}-${item.sourceId}-${item.startTimeMillis}`" class="evidence-item">
            <div><el-tag size="small" effect="plain">{{ sourceLabel(item.sourceType) }}</el-tag><strong>{{ item.timeText || formatMillisRange(item.startTimeMillis, item.endTimeMillis) }}</strong></div>
            <p>{{ evidenceText(item) }}</p><small v-if="originalText(item)">原文：{{ originalText(item) }}</small>
            <el-button size="small" plain @click="$emit('seek', item.startTimeMillis, { evidenceId: item.evidenceId, revision: item.revision })">跳到视频</el-button>
          </article>
        </template>
      </section>
      <details v-if="response.usage || response.evidence.length > 0" class="answer-details">
        <summary>回答详情</summary>
        <dl>
          <template v-if="response.usage">
            <div><dt>Provider</dt><dd>{{ response.usage.provider }}</dd></div>
            <div><dt>Model</dt><dd>{{ response.usage.model || '暂无' }}</dd></div>
            <div><dt>Token</dt><dd>{{ response.usage.totalTokens ?? '暂无' }}</dd></div>
            <div><dt>耗时</dt><dd>{{ response.usage.durationMillis === null ? '暂无' : `${response.usage.durationMillis} ms` }}</dd></div>
          </template>
          <div class="answer-confidence">
            <dt>证据置信度</dt>
            <dd v-if="confidenceDetails.length" class="answer-confidence__list">
              <span v-for="item in confidenceDetails" :key="item.key">
                <span>{{ item.label }}</span><strong>{{ item.value }}</strong>
              </span>
            </dd>
            <dd v-else>暂无</dd>
          </div>
        </dl>
      </details>
      <details class="answer-details"><summary>模型使用记录</summary><CourseModelUsagePanel :task-id="taskId" :refresh-key="response.recordId" /></details>
    </article>
  </section>
</template>

<style scoped>
.qa-history { padding: 14px; background: var(--color-canvas); border: 1px solid var(--color-border); border-radius: var(--radius-md); }
.qa-history summary { cursor: pointer; font-weight: 650; }.history-toolbar { margin-top: 10px; display: flex; gap: 10px; align-items: center; }
.qa-history ol { list-style: none; margin: 10px 0; padding: 0; display: grid; gap: 6px; max-height: 230px; overflow: auto; }
.qa-history li button { width: 100%; padding: 10px; text-align: left; border: 1px solid transparent; background: var(--color-surface); color: var(--color-ink); border-radius: var(--radius-sm); cursor: pointer; overflow-wrap: anywhere; }
.qa-history button[aria-pressed="true"] { border-color: var(--color-brand); }.qa-history small { display: block; margin-top: 5px; color: var(--color-ink-soft); }
.history-help { font-size: 13px !important; color: var(--color-ink-soft) !important; }
.workspace-panel { display: grid; gap: 22px; min-width: 0; padding: clamp(20px, 3vw, 30px); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); box-shadow: var(--shadow-low); }
header { display: grid; gap: 6px; } header h2, header p, h3 { margin: 0; } header p { color: var(--color-ink-soft); }
.qa-form, .qa-answer, .qa-evidence { display: grid; gap: 14px; }.qa-form > div { display: flex; gap: 10px; }
.qa-answer { padding-top: 20px; border-top: 1px solid var(--color-border); }.qa-answer > p { margin: 0; color: var(--color-ink); font-size: 17px; line-height: 1.8; }
.evidence-item { display: grid; gap: 10px; padding: 15px 0; border-bottom: 1px solid var(--color-border); }.evidence-item > div { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }.evidence-item p, .evidence-item small { margin: 0; color: var(--color-ink-soft); line-height: 1.65; }.evidence-item :deep(.el-button) { width: fit-content; }
.answer-details { padding: 14px 0; border-top: 1px solid var(--color-border); }.answer-details summary { color: var(--color-ink-soft); cursor: pointer; }.answer-details dl { display: grid; gap: 8px; margin: 14px 0 0; }.answer-details dl div { display: flex; justify-content: space-between; gap: 16px; }.answer-details dt, .answer-details dd { margin: 0; color: var(--color-ink-soft); }
.answer-confidence { align-items: flex-start; }.answer-confidence__list { display: grid; gap: 6px; min-width: 0; }.answer-confidence__list > span { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px 14px; overflow-wrap: anywhere; }.answer-confidence__list strong { color: var(--color-ink); font-weight: 650; }
@media (max-width: 520px) { .answer-details dl > div { align-items: stretch; flex-direction: column; gap: 5px; }.answer-confidence__list > span { justify-content: space-between; } }
</style>
