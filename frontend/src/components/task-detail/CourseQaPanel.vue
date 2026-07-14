<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { askCourseQa, toReadableCourseQaError } from "../../api/qa";
import type { CourseQaEvidenceItem, CourseQaResponse } from "../../types/qa";
import { formatMillisRange } from "../../utils/time";

const props = defineProps<{ taskId: string }>();
defineEmits<{ seek: [startTimeMillis: number] }>();
const question = ref("");
const loading = ref(false);
const errorMessage = ref("");
const response = ref<CourseQaResponse | null>(null);
const requestVersion = ref(0);
const canSubmit = computed(() => question.value.trim().length > 0 && question.value.trim().length <= 500 && !loading.value);
const confidenceDetails = computed(() => (response.value?.evidence ?? [])
  .filter((item) => item.confidence !== null)
  .map((item, index) => ({
    key: `${item.sourceType}-${item.sourceId}-${item.startTimeMillis}-${index}`,
    label: item.timeText || formatMillisRange(item.startTimeMillis, item.endTimeMillis),
    value: item.confidence!.toFixed(2),
  })));

watch(() => props.taskId, clear, { immediate: true });

async function submit() {
  if (loading.value) return;
  const normalized = question.value.trim();
  if (!normalized) { errorMessage.value = "请输入课程问题"; return; }
  if (normalized.length > 500) { errorMessage.value = "问题不能超过 500 个字符"; return; }
  const currentTaskId = props.taskId;
  const version = requestVersion.value + 1;
  requestVersion.value = version;
  loading.value = true;
  errorMessage.value = "";
  try {
    const nextResponse = await askCourseQa(currentTaskId, { question: normalized });
    if (version === requestVersion.value && props.taskId === currentTaskId) response.value = nextResponse;
  } catch (error) {
    if (version === requestVersion.value && props.taskId === currentTaskId) errorMessage.value = toReadableCourseQaError(error);
  } finally {
    if (version === requestVersion.value && props.taskId === currentTaskId) loading.value = false;
  }
}

function clear() {
  requestVersion.value += 1;
  question.value = "";
  loading.value = false;
  errorMessage.value = "";
  response.value = null;
}

function sourceLabel(sourceType: string): string {
  const labels: Record<string, string> = { VIDEO_SEGMENT: "音画证据", SUBTITLE_TRANSLATION: "字幕译文", SUBTITLE: "字幕", OCR: "OCR" };
  return labels[sourceType] || sourceType || "证据";
}

function evidenceText(item: CourseQaEvidenceItem): string { return sanitizeEvidence(item.translatedSnippet || item.snippet); }
function originalText(item: CourseQaEvidenceItem): string {
  if (!item.translatedSnippet || !item.snippet) return "";
  const original = sanitizeEvidence(item.snippet);
  return original && original !== evidenceText(item) ? original : "";
}
function sanitizeEvidence(value: string): string {
  return (value || "").split(/[；;\r\n]+/).map((part) => sanitizePart(part.trim())).filter(Boolean).join("；");
}
function sanitizePart(part: string): string {
  if (!part) return "";
  if (part.startsWith("本段主要讲解：")) {
    const body = part.slice("本段主要讲解：".length).trim();
    const cjk = body.match(/[\u4e00-\u9fff]/g)?.length ?? 0;
    const chars = body.replace(/[^\p{L}\p{N}]/gu, "").length;
    return chars === 0 || cjk / chars < .25 ? `本段语音原文：${body}` : part;
  }
  if (part.startsWith("画面文字包括：")) return "";
  return /(\{emcee|\bie\s+ot\b|call\s+me\s+h+m+a+a?l?i|�)/i.test(part) ? part.replace(/\{emcee[\s\S]*$/i, "").trim() : part;
}
</script>

<template>
  <section class="workspace-panel qa-panel" aria-labelledby="qa-title">
    <header><h2 id="qa-title">课程问答</h2><p>根据当前课程已经生成的内容回答问题。</p></header>
    <div class="qa-form">
      <el-input v-model="question" type="textarea" :rows="4" maxlength="500" show-word-limit placeholder="输入与当前课程有关的问题" @keydown.ctrl.enter.prevent="submit" />
      <div><el-button type="primary" :loading="loading" :disabled="!canSubmit" @click="submit">提问</el-button><el-button :disabled="loading && !response" @click="clear">清空</el-button></div>
    </div>
    <el-alert v-if="errorMessage" :closable="false" :title="errorMessage" type="warning" show-icon />
    <article v-if="response" class="qa-answer" aria-live="polite">
      <h3>回答</h3><p>{{ response.answer }}</p>
      <section class="qa-evidence" aria-labelledby="evidence-title">
        <h3 id="evidence-title">证据</h3>
        <el-empty v-if="response.evidence.length === 0" description="当前课程内容中没有找到明确依据" />
        <template v-else>
          <article v-for="item in response.evidence" :key="`${item.sourceType}-${item.sourceId}-${item.startTimeMillis}`" class="evidence-item">
            <div><el-tag size="small" effect="plain">{{ sourceLabel(item.sourceType) }}</el-tag><strong>{{ item.timeText || formatMillisRange(item.startTimeMillis, item.endTimeMillis) }}</strong></div>
            <p>{{ evidenceText(item) }}</p><small v-if="originalText(item)">原文：{{ originalText(item) }}</small>
            <el-button size="small" plain @click="$emit('seek', item.startTimeMillis)">跳到视频</el-button>
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
    </article>
  </section>
</template>

<style scoped>
.workspace-panel { display: grid; gap: 22px; min-width: 0; padding: clamp(20px, 3vw, 30px); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); box-shadow: var(--shadow-low); }
header { display: grid; gap: 6px; } header h2, header p, h3 { margin: 0; } header p { color: var(--color-ink-soft); }
.qa-form, .qa-answer, .qa-evidence { display: grid; gap: 14px; }.qa-form > div { display: flex; gap: 10px; }
.qa-answer { padding-top: 20px; border-top: 1px solid var(--color-border); }.qa-answer > p { margin: 0; color: var(--color-ink); font-size: 17px; line-height: 1.8; }
.evidence-item { display: grid; gap: 10px; padding: 15px 0; border-bottom: 1px solid var(--color-border); }.evidence-item > div { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }.evidence-item p, .evidence-item small { margin: 0; color: var(--color-ink-soft); line-height: 1.65; }.evidence-item :deep(.el-button) { width: fit-content; }
.answer-details { padding: 14px 0; border-top: 1px solid var(--color-border); }.answer-details summary { color: var(--color-ink-soft); cursor: pointer; }.answer-details dl { display: grid; gap: 8px; margin: 14px 0 0; }.answer-details dl div { display: flex; justify-content: space-between; gap: 16px; }.answer-details dt, .answer-details dd { margin: 0; color: var(--color-ink-soft); }
.answer-confidence { align-items: flex-start; }.answer-confidence__list { display: grid; gap: 6px; min-width: 0; }.answer-confidence__list > span { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px 14px; overflow-wrap: anywhere; }.answer-confidence__list strong { color: var(--color-ink); font-weight: 650; }
@media (max-width: 520px) { .answer-details dl > div { align-items: stretch; flex-direction: column; gap: 5px; }.answer-confidence__list > span { justify-content: space-between; } }
</style>
