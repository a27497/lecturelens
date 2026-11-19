<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { mayHaveLostCourseAccess } from "../../api/courseAccess";
import { getEvidenceIndexStatus } from "../../api/qa";
import { fetchScopeEvidence, type ScopeEvidence } from "../../api/learningScope";
import type { Citation } from "../../api/study";
import { formatMillisToClock } from "../../utils/time";

const props = defineProps<{ taskId: string; citation: Citation; revision: number; canNote: boolean }>();
const emit = defineEmits<{ replay: []; note: []; accessFailure: [] }>();
const original = ref<ScopeEvidence>();
const translated = ref<ScopeEvidence>();
const loading = ref(true);
const failed = ref(false);
const canReplay = computed(() => original.value && original.value.startMs >= 0 && original.value.endMs > original.value.startMs);
const clock = (value: number) => formatMillisToClock(value).replace(/^00:/, "");

watch(() => [props.taskId, props.revision, props.citation.evidence_id] as const, async ([id, revision, evidenceId], _before, onCleanup) => {
  let current = true;
  onCleanup(() => { current = false; });
  loading.value = true;
  failed.value = false;
  original.value = undefined;
  translated.value = undefined;
  try {
    let cursor = "";
    const visited = new Set<string>();
    while (current && !visited.has(cursor)) {
      visited.add(cursor);
      const page = await fetchScopeEvidence(id, cursor, revision);
      if (!current) return;
      if (page.stale || page.revision !== revision) break;
      const found = page.items.find(item => item.evidenceId === evidenceId && item.revision === revision
        && item.retrievable && item.startMs === props.citation.start_ms && item.endMs === props.citation.end_ms);
      if (found?.normalizedText.trim()) {
        const latest = await getEvidenceIndexStatus(id);
        if (!current) return;
        if (latest.revision !== revision) break;
        original.value = found;
        if (found.sourceType === "SUBTITLE") {
          translated.value = page.items.find(item => item.sourceType === "SUBTITLE_TRANSLATION" && item.revision === revision
            && item.startMs === found.startMs && item.endMs === found.endMs && item.retrievable);
        }
        return;
      }
      if (!page.nextCursor) break;
      cursor = page.nextCursor;
    }
    if (current) failed.value = true;
  } catch (error) {
    if (!current) return;
    failed.value = true;
    if (mayHaveLostCourseAccess(error)) emit("accessFailure");
  } finally {
    if (current) loading.value = false;
  }
}, { immediate: true });
</script>

<template>
  <section class="course-source" aria-label="课程出处">
    <header><h4>课程出处</h4><time>{{ clock(citation.start_ms) }}–{{ clock(citation.end_ms) }}</time></header>
    <p v-if="loading" role="status">正在核对出处…</p>
    <p v-else-if="failed" role="status">这段出处暂时无法核对。课程可能已更新，请重新打开课程。</p>
    <template v-else-if="original">
      <p class="course-source__excerpt">{{ translated?.normalizedText || original.normalizedText }}</p>
      <details>
        <summary>核对原文</summary>
        <blockquote>{{ original.normalizedText }}</blockquote>
      </details>
      <div class="course-source__actions">
        <button v-if="canReplay" type="button" @click="emit('replay')">回看 {{ clock(original.startMs) }}</button>
        <button v-if="canReplay && canNote" type="button" @click="emit('note')">记下这段</button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.course-source { display: grid; gap: 8px; margin-top: 4px; padding: 13px; border: 1px solid var(--color-border-strong); border-inline-start: 3px solid var(--color-brand); border-radius: 9px; background: var(--color-evidence-surface); font-size: 14px; }
header, .course-source__actions { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
h4, p { margin: 0; }
time { color: var(--color-brand); font-weight: 650; font-variant-numeric: tabular-nums; }
.course-source__excerpt { line-height: 1.65; }
summary { cursor: pointer; color: var(--color-brand-strong); }
blockquote { margin: 7px 0 0; padding: 0 0 0 10px; border-inline-start: 2px solid var(--color-border-strong); overflow-wrap: anywhere; }
.course-source__actions { justify-content: flex-start; }
button { color: var(--color-brand); border: 1px solid var(--color-border-strong); background: var(--color-surface); padding: 6px 10px; border-radius: 7px; cursor: pointer; font: inherit; font-weight: 650; }
</style>
