<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import type { AnalysisTaskStatus } from "../../types/task";
import type { ResultTranslationSegment, TaskResultResponse } from "../../types/result";
import { copyTextToClipboard } from "../../utils/clipboard";
import { formatMillisRange } from "../../utils/time";

type ContentView = "translated" | "source" | "timeline";
const props = defineProps<{ taskId: string; status?: AnalysisTaskStatus; result: TaskResultResponse | null }>();
defineEmits<{ seek: [startTimeMillis: number] }>();

const activeView = ref<ContentView>("translated");
const keyword = ref("");
const defaultedTaskId = ref("");
const views: Array<{ value: ContentView; label: string }> = [
  { value: "translated", label: "中文译文" },
  { value: "source", label: "原文" },
  { value: "timeline", label: "时间轴" },
];
const sourceText = computed(() => props.result?.sourceFullText?.trim() || (props.result?.subtitles ?? []).map((item) => item.sourceText).filter(Boolean).join("\n\n"));
const translatedText = computed(() => props.result?.translatedFullText?.trim() || "");
const translationByIndex = computed(() => {
  const map = new Map<number, ResultTranslationSegment>();
  for (const item of props.result?.translations ?? []) map.set(item.segmentIndex, item);
  return map;
});
const rows = computed(() => (props.result?.subtitles ?? []).map((subtitle) => ({ ...subtitle, translation: translationByIndex.value.get(subtitle.segmentIndex) })));
const filteredRows = computed(() => {
  const value = keyword.value.trim().toLowerCase();
  if (!value) return rows.value;
  return rows.value.filter((row) => row.sourceText.toLowerCase().includes(value) || (row.translation?.translatedText || "").toLowerCase().includes(value));
});
const hasFullTextOnlyTranslation = computed(() => translatedText.value.length > 0 && (props.result?.translations.length ?? 0) === 0);

watch(() => props.taskId, () => {
  activeView.value = "translated";
  keyword.value = "";
  defaultedTaskId.value = "";
}, { immediate: true });

watch([() => props.taskId, translatedText, sourceText], ([currentTaskId, translated, source]) => {
  if (defaultedTaskId.value === currentTaskId || (!translated && !source)) return;
  activeView.value = translated ? "translated" : "source";
  defaultedTaskId.value = currentTaskId;
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
      <div class="reading-view__header"><h3>中文译文</h3><el-button size="small" @click="copy(translatedText, '中文译文')">复制译文</el-button></div>
      <div v-if="translatedText" class="reading-copy">{{ translatedText }}</div>
      <el-empty v-else :description="emptyText('中文译文生成中')" />
    </article>
    <article v-else-if="activeView === 'source'" class="reading-view">
      <div class="reading-view__header"><h3>原文</h3><el-button size="small" @click="copy(sourceText, '原文')">复制原文</el-button></div>
      <div v-if="sourceText" class="reading-copy">{{ sourceText }}</div>
      <el-empty v-else :description="emptyText('原文生成中')" />
    </article>
    <section v-else class="timeline-view" aria-label="课程时间轴">
      <div class="timeline-search"><el-input v-model="keyword" clearable placeholder="搜索原文或译文关键词" /><span v-if="keyword.trim()">{{ filteredRows.length }} / {{ rows.length }} 个片段</span></div>
      <el-alert v-if="hasFullTextOnlyTranslation" :closable="false" title="当前为全文翻译模式，时间轴仅展示原文；中文全文请切换到“中文译文”。" type="info" show-icon />
      <el-empty v-if="rows.length === 0" :description="emptyText('时间轴生成中')" />
      <el-empty v-else-if="filteredRows.length === 0" description="没有找到包含该关键词的片段" />
      <div v-else class="timeline-list">
        <article v-for="row in filteredRows" :key="row.segmentIndex" class="timeline-row">
          <div class="timeline-row__time"><strong>{{ formatMillisRange(row.startMillis, row.endMillis) }}</strong><span>#{{ row.segmentIndex }}</span></div>
          <div><p>{{ row.sourceText }}</p><p class="timeline-row__translation">{{ row.translation?.translatedText || (hasFullTextOnlyTranslation ? '当前只有中文全文，没有逐段译文。' : '译文生成中') }}</p></div>
          <el-button size="small" plain @click="$emit('seek', row.startMillis)">跳到视频</el-button>
        </article>
      </div>
    </section>
  </section>
</template>

<style scoped>
.workspace-panel { display: grid; gap: 22px; min-width: 0; padding: clamp(20px, 3vw, 30px); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); box-shadow: var(--shadow-low); }
header { display: grid; gap: 6px; } header h2, header p, h3 { margin: 0; } header p { color: var(--color-ink-soft); }
.subnav { display: flex; gap: 6px; padding-bottom: 12px; border-bottom: 1px solid var(--color-border); }
.subnav button { padding: 8px 13px; border: 1px solid transparent; border-radius: var(--radius-sm); background: transparent; color: var(--color-ink-soft); font: inherit; cursor: pointer; }
.subnav button.is-active { border-color: var(--color-border); background: var(--color-brand-soft, #edf4f0); color: var(--color-brand); font-weight: 700; }
.reading-view { display: grid; gap: 16px; min-width: 0; }
.reading-view__header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.reading-copy { white-space: pre-wrap; color: var(--color-ink); font-size: 16px; line-height: 1.9; overflow-wrap: anywhere; }
.timeline-view, .timeline-list { display: grid; gap: 14px; min-width: 0; }
.timeline-search { display: flex; align-items: center; gap: 12px; }.timeline-search span { flex: 0 0 auto; color: var(--color-ink-soft); font-size: 13px; }
.timeline-row { display: grid; grid-template-columns: 110px minmax(0,1fr) auto; gap: 16px; align-items: start; padding: 16px 0; border-bottom: 1px solid var(--color-border); }
.timeline-row__time { display: grid; gap: 4px; color: var(--color-brand); font-size: 13px; }.timeline-row p { margin: 0 0 8px; line-height: 1.65; }.timeline-row__translation { color: var(--color-ink-soft); }
@media (max-width: 680px) { .timeline-search { align-items: stretch; flex-direction: column; }.timeline-row { grid-template-columns: 1fr; } }
</style>
