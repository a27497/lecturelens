<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import CourseVisualEvidencePanel from "./CourseVisualEvidencePanel.vue";
import type { AnalysisTaskStatus } from "../../types/task";
import type { ResultTranslationSegment, TaskResultResponse } from "../../types/result";
import { copyTextToClipboard } from "../../utils/clipboard";
import { formatMillisRange } from "../../utils/time";

import { createTimeIndex } from "../../utils/timeIndex";
import type { ContentView } from "./courseLocation";
const props = defineProps<{ taskId: string; status?: AnalysisTaskStatus; result: TaskResultResponse | null; positionMs?: number; view?: ContentView; visible?: boolean; locateSequence?: number }>();
const emit = defineEmits<{ seek: [startTimeMillis: number]; "update:view": [view: ContentView] }>();

const localView = ref<ContentView>("translated");
const activeView = computed({ get: () => props.view ?? localView.value, set: (view: ContentView) => { localView.value = view; emit("update:view", view); } });
const following = ref(true);
const timelineRef = ref<HTMLElement | null>(null);
const rowElements = new Map<number, HTMLElement>();
let scrollGeneration = 0;
const keyword = ref("");
const defaultedTaskId = ref("");
const baseViews: Array<{ value: ContentView; label: string }> = [
  { value: "translated", label: "中文译文" },
  { value: "source", label: "原文" },
  { value: "timeline", label: "时间轴" },
];
const hasVisualEvidence = computed(() => (props.result?.keyframes?.length ?? 0) > 0);
const views = computed(() => hasVisualEvidence.value
  ? [...baseViews, { value: "visual" as const, label: "画面证据" }]
  : baseViews);
const sourceText = computed(() => props.result?.sourceFullText?.trim() || (props.result?.subtitles ?? []).map((item) => item.sourceText).filter(Boolean).join("\n\n"));
const translatedText = computed(() => props.result?.translatedFullText?.trim() || "");
const translationByIndex = computed(() => {
  const map = new Map<number, ResultTranslationSegment>();
  for (const item of props.result?.translations ?? []) map.set(item.segmentIndex, item);
  return map;
});
const rows = computed(() => (props.result?.subtitles ?? []).map((subtitle) => {
  const translation = translationByIndex.value.get(subtitle.segmentIndex);
  // A matching array position or segment number alone does not establish time alignment.
  const aligned = translation?.startMillis === subtitle.startMillis && translation?.endMillis === subtitle.endMillis;
  return { ...subtitle, translation: aligned ? translation : undefined };
}));
const timeIndex = computed(() => createTimeIndex(rows.value, row => row.startMillis, row => row.endMillis));
const currentRow = computed(() => timeIndex.value(props.positionMs ?? 0));
const currentSegment = computed(() => currentRow.value?.segmentIndex);
function canSeek(start: number, end: number) { return Number.isFinite(start) && start >= 0 && Number.isFinite(end) && end > start; }
function pauseFollow() { following.value = false; scrollGeneration++; }
function pauseForKey(event: KeyboardEvent) {
  if (["ArrowDown", "ArrowUp", "PageDown", "PageUp", "Home", "End", " "].includes(event.key)) pauseFollow();
}
async function scrollToCurrent() {
  const generation = ++scrollGeneration;
  await nextTick();
  if (generation !== scrollGeneration || !following.value || props.visible === false || activeView.value !== "timeline") return;
  const row = currentSegment.value === undefined ? undefined : rowElements.get(currentSegment.value);
  const list = timelineRef.value;
  if (!row || !list) return;
  const box = list.getBoundingClientRect(), target = row.getBoundingClientRect();
  if (target.top < box.top || target.bottom > box.bottom) list.scrollTop += target.top - box.top - 12;
}
function resumeFollow() { keyword.value = ""; following.value = true; void scrollToCurrent(); }
watch(keyword, value => { if (value.trim()) pauseFollow(); });
watch([currentSegment, activeView, () => props.visible, () => props.locateSequence], () => { void scrollToCurrent(); }, { flush: "post" });
watch(() => props.locateSequence, () => { keyword.value = ""; following.value = true; });
const filteredRows = computed(() => {
  const value = keyword.value.trim().toLowerCase();
  if (!value) return rows.value;
  return rows.value.filter((row) => row.sourceText.toLowerCase().includes(value) || (row.translation?.translatedText || "").toLowerCase().includes(value));
});
const hasFullTextOnlyTranslation = computed(() => translatedText.value.length > 0 && (props.result?.translations.length ?? 0) === 0);
const translationStatus = computed(() => props.result?.translationStatus || "NOT_STARTED");
const translationEmptyText = computed(() => {
  switch (translationStatus.value) {
    case "RUNNING": return "中文译文生成中";
    case "FAILED": return props.result?.translationErrorSummary || "译文生成失败";
    case "CANCELED": return "已取消，未生成译文";
    case "SKIPPED": return "本次任务未生成译文";
    default: return "译文未生成";
  }
});
const segmentTranslationEmptyText = computed(() => {
  switch (translationStatus.value) {
    case "RUNNING": return "译文生成中";
    case "FAILED": return "译文生成失败";
    case "CANCELED": return "已取消，未生成译文";
    case "SKIPPED": return "本次任务未生成译文";
    default: return "译文未生成";
  }
});

watch(() => props.taskId, () => {
  localView.value = "translated";
  following.value = true;
  rowElements.clear();
  keyword.value = "";
  defaultedTaskId.value = "";
}, { immediate: true });

watch([() => props.taskId, translatedText, sourceText, hasVisualEvidence], ([currentTaskId, translated, source, visual]) => {
  if (defaultedTaskId.value === currentTaskId || (!translated && !source && !visual)) return;
  if (!props.view) localView.value = translated ? "translated" : source ? "source" : "visual";
  defaultedTaskId.value = currentTaskId;
}, { immediate: true });

watch([hasVisualEvidence, () => props.view, () => props.result !== null], ([hasEvidence]) => {
  if (props.result && !hasEvidence && activeView.value === "visual") {
    activeView.value = translatedText.value ? "translated" : "source";
  }
}, { immediate: true });

async function copy(text: string, label: string) {
  if (!text) { ElMessage.warning(`${label}暂无可复制内容`); return; }
  try { await copyTextToClipboard(text); ElMessage.success("已复制到剪贴板"); }
  catch { ElMessage.error("复制失败，请手动选择文本复制"); }
}

function emptyText(pending: string): string {
  if (props.status === "FAILED") return "处理失败，暂无内容";
  if (props.status === "CANCELED") return "处理已取消，暂无内容";
  return pending;
}
</script>

<template>
  <section class="workspace-panel content-panel" aria-labelledby="content-title">
    <header><h2 id="content-title">课程内容</h2><p>阅读完整课程文本，或按时间查看字幕片段。</p></header>
    <nav class="subnav" aria-label="课程内容视图">
      <button v-for="item in views" :key="item.value" type="button" :aria-pressed="activeView === item.value" :class="{ 'is-active': activeView === item.value }" @click="activeView = item.value">{{ item.label }}</button>
    </nav>

    <article v-if="activeView === 'translated'" class="reading-view">
      <div class="reading-view__header"><h3>中文译文</h3><el-button :disabled="!translatedText" size="small" @click="copy(translatedText, '中文译文')">复制译文</el-button></div>
      <div v-if="translatedText" class="reading-copy">{{ translatedText }}</div>
      <el-empty v-else :description="translationEmptyText" />
    </article>
    <article v-else-if="activeView === 'source'" class="reading-view">
      <div class="reading-view__header"><h3>原文</h3><el-button size="small" @click="copy(sourceText, '原文')">复制原文</el-button></div>
      <div v-if="sourceText" class="reading-copy">{{ sourceText }}</div>
      <el-empty v-else :description="emptyText('原文生成中')" />
    </article>
    <section v-else-if="activeView === 'timeline'" class="timeline-view" aria-label="课程时间轴">
      <div class="timeline-search"><el-input v-model="keyword" clearable placeholder="搜索原文或译文关键词" /><span v-if="keyword.trim()">{{ filteredRows.length }} / {{ rows.length }} 个片段</span></div>
      <el-alert v-if="hasFullTextOnlyTranslation" :closable="false" title="当前为全文翻译模式，时间轴仅展示原文；中文全文请切换到“中文译文”。" type="info" show-icon />
      <div class="timeline-controls">
        <button type="button" :aria-pressed="following" @click="following ? pauseFollow() : resumeFollow()">{{ following ? '正在跟随视频 · 暂停跟随' : '回到当前播放位置并跟随' }}</button>
        <span>{{ currentRow ? `当前片段 #${currentSegment}` : '当前位置没有对应的原文片段' }}</span>
      </div>
      <el-empty v-if="rows.length === 0" :description="emptyText(status === 'SUCCEEDED' ? '本课程没有可定位的字幕片段' : '时间轴生成中')" />
      <el-empty v-else-if="filteredRows.length === 0" description="没有找到包含该关键词的片段" />
      <div v-else v-memo="[filteredRows, currentSegment]" ref="timelineRef" class="timeline-list" tabindex="0" aria-label="原文片段，可滚动浏览" @wheel.passive="pauseFollow" @touchstart.passive="pauseFollow" @pointerdown="pauseFollow" @keydown="pauseForKey">
        <article v-for="row in filteredRows" v-memo="[row, row.segmentIndex === currentSegment]" :key="row.segmentIndex" :ref="el => { if (el) rowElements.set(row.segmentIndex, el as HTMLElement); else rowElements.delete(row.segmentIndex); }" class="timeline-row" :class="{ 'is-current': row.segmentIndex === currentSegment }" :aria-current="row.segmentIndex === currentSegment ? 'true' : undefined" :data-segment="row.segmentIndex">
          <div class="timeline-row__time"><strong>{{ formatMillisRange(row.startMillis, row.endMillis) }}</strong><span>#{{ row.segmentIndex }}</span></div>
          <div><p>{{ row.sourceText }}</p><p class="timeline-row__translation">{{ row.translation?.translatedText || (hasFullTextOnlyTranslation ? '当前只有中文全文，没有逐段译文。' : (result?.translations.length ? '此片段暂无对齐译文' : segmentTranslationEmptyText)) }}</p></div>
          <el-button size="small" plain :disabled="!canSeek(row.startMillis, row.endMillis)" @click="resumeFollow(); emit('seek', row.startMillis)">跳到视频</el-button>
        </article>
      </div>
    </section>
    <CourseVisualEvidencePanel
      v-else-if="hasVisualEvidence && result"
      :task-id="taskId"
      :keyframes="result.keyframes"
      :video-segments="result.videoSegments"
      @seek="emit('seek', $event)"
    />
  </section>
</template>

<style scoped>
.workspace-panel { display: grid; gap: 22px; min-width: 0; padding: clamp(20px, 3vw, 30px); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); box-shadow: var(--shadow-low); }
header { display: grid; gap: 6px; } header h2, header p, h3 { margin: 0; } header p { color: var(--color-ink-soft); }
.subnav { display: flex; flex-wrap: wrap; gap: 6px; padding-bottom: 12px; border-bottom: 1px solid var(--color-border); }
.subnav button { padding: 8px 13px; border: 1px solid transparent; border-radius: var(--radius-sm); background: transparent; color: var(--color-ink-soft); font: inherit; cursor: pointer; }
.subnav button.is-active { border-color: var(--color-border); background: var(--color-brand-soft, #edf4f0); color: var(--color-brand); font-weight: 700; }
.reading-view { display: grid; gap: 16px; min-width: 0; }
.reading-view__header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.reading-copy { white-space: pre-wrap; color: var(--color-ink); font-size: 16px; line-height: 1.9; overflow-wrap: anywhere; }
.timeline-view, .timeline-list { display: grid; gap: 14px; min-width: 0; }
.timeline-controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; color: var(--color-ink-soft); font-size: 13px; }
.timeline-controls button { font: inherit; color: var(--color-brand); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: 8px 12px; cursor: pointer; }
.timeline-list { display: block; position: relative; max-height: 65vh; overflow-y: auto; overscroll-behavior: contain; overflow-anchor: none; }
.timeline-row.is-current { background: var(--color-brand-soft, #edf4f0); border-left: 3px solid var(--color-brand); padding-left: 10px; }
.timeline-search { display: flex; align-items: center; gap: 12px; }.timeline-search span { flex: 0 0 auto; color: var(--color-ink-soft); font-size: 13px; }
.timeline-row { display: grid; grid-template-columns: 110px minmax(0,1fr) auto; gap: 16px; align-items: start; padding: 16px 0; border-bottom: 1px solid var(--color-border); }
.timeline-row__time { display: grid; gap: 4px; color: var(--color-brand); font-size: 13px; }.timeline-row p { margin: 0 0 8px; line-height: 1.65; }.timeline-row__translation { color: var(--color-ink-soft); }
@media (max-width: 680px) { .timeline-search { align-items: stretch; flex-direction: column; }.timeline-row { grid-template-columns: 1fr; } }
</style>
