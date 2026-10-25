<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { fetchScopeEvidence, scopeLabel } from "../../api/learningScope";
import type { LearningScope, ScopeEvidence } from "../../api/learningScope";
import { formatMillisRange } from "../../utils/time";
import type { EvidenceSeekContext } from "./evidenceSeekGuard";
import { mayHaveLostCourseAccess } from "../../api/courseAccess";
const props = defineProps<{ taskId: string; modelValue: LearningScope | null; frozenScope?: LearningScope | null; refreshKey?: number; compact?: boolean }>();
const emit = defineEmits<{ "update:modelValue": [scope: LearningScope | null]; seek: [milliseconds: number, context: EvidenceSeekContext]; accessFailure: [] }>();
const editing = ref(false);
const items = ref<ScopeEvidence[]>([]), revision = ref<number>();
const cursor = ref<string | null>(null), loading = ref(false), error = ref("");
const kind = ref<"course" | "segments">("course"), policy = ref<"strict" | "course">("strict");
const selected = ref<string[]>([]), query = ref("");
let generation = 0;
const visible = computed(() => items.value.filter(item => `${formatMillisRange(item.startMs, item.endMs)} ${item.normalizedText}`.toLowerCase().includes(query.value.toLowerCase())));
function label(id: string) { const item = items.value.find(row => row.evidenceId === id); return item ? `${formatMillisRange(item.startMs, item.endMs)} ${item.normalizedText.slice(0, 100)}` : `片段 ${id}（未加载或属于旧版本）`; }
function publish() {
  if (revision.value === undefined || (kind.value === "segments" && !selected.value.length)) { emit("update:modelValue", null); return; }
  emit("update:modelValue", { version: 1, kind: kind.value, policy: kind.value === "course" ? "strict" : policy.value,
    revision: revision.value, evidence_ids: kind.value === "course" ? [] : [...selected.value].sort() });
}
function select(id: string, checked: boolean) { selected.value = checked ? [...selected.value, id] : selected.value.filter(value => value !== id); publish(); }
async function load(more = false) {
  const current = ++generation, task = props.taskId, previous = revision.value;
  loading.value = true; error.value = "";
  try {
    const page = await fetchScopeEvidence(task, more ? cursor.value ?? "" : "", more ? revision.value : undefined);
    if (current !== generation || task !== props.taskId) return;
    if (page.stale) throw Error("课程来源已更新，请刷新范围后重新确认。");
    items.value = [...(more ? items.value : []), ...page.items.filter(item => item.retrievable && item.endMs > item.startMs)];
    cursor.value = page.nextCursor; revision.value = page.revision;
    if (!more && previous !== undefined && previous !== page.revision) {
      selected.value = []; emit("update:modelValue", null); error.value = "课程来源版本已变化，请重新确认整课或片段范围。";
    } else if (previous === undefined) publish();
  } catch (failure) {
    if (current === generation) {
      emit("update:modelValue", null);
      error.value = failure instanceof Error && failure.message.startsWith("课程") ? failure.message : "范围加载失败，请重试或重新打开课程。";
      if (mayHaveLostCourseAccess(failure)) emit("accessFailure");
    }
  } finally { if (current === generation) loading.value = false; }
}
watch(() => props.taskId, () => { generation++; revision.value = undefined; items.value = []; selected.value = []; kind.value = "course"; policy.value = "strict"; query.value = ""; emit("update:modelValue", null); void load(); }, { immediate: true });
watch(() => props.refreshKey, () => { void load(); });
onBeforeUnmount(() => generation++);
</script>
<template>
  <section class="scope-picker" :class="{ 'scope-picker--compact': compact }" aria-label="学习范围">
    <details v-if="frozenScope !== undefined" class="frozen-scope" :open="!compact">
      <summary>当前范围：{{ scopeLabel(frozenScope) }}</summary>
      <p v-if="!frozenScope">旧学习记录按整课范围读取。</p>
      <template v-else><p>课程版本 {{ frozenScope.revision }}；此范围随执行保存，修改下次范围不会改变它。</p><ul v-if="frozenScope.kind === 'segments'"><li v-for="id in frozenScope.evidence_ids" :key="id">{{ label(id) }}</li></ul></template>
    </details>
    <details class="scope-options" :open="!compact || editing" @toggle="editing = ($event.target as HTMLDetailsElement).open">
    <summary v-if="compact">下次：{{ modelValue ? scopeLabel(modelValue) : '待确认' }} · 更改</summary>
    <h3>下次提问或学习的范围</h3>
    <p>课程问答与解释/练习使用同一范围。已开始的执行保留原范围。</p>
    <label><input v-model="kind" type="radio" value="course" @change="publish" />整节课程</label>
    <label><input v-model="kind" type="radio" value="segments" @change="publish" />选择课程片段</label>
    <template v-if="kind === 'segments'">
      <fieldset><legend>片段范围策略</legend>
        <label><input v-model="policy" type="radio" value="strict" @change="publish" />仅限选中范围</label>
        <label><input v-model="policy" type="radio" value="course" @change="publish" />允许扩展到整课</label>
      </fieldset>
      <input v-model="query" aria-label="筛选已加载课程片段" placeholder="筛选已加载片段" />
      <div class="scope-items">
        <div v-for="item in visible" :key="item.evidenceId" class="scope-item">
          <label><input type="checkbox" :checked="selected.includes(item.evidenceId)" :disabled="selected.length >= 16 && !selected.includes(item.evidenceId)" @change="select(item.evidenceId, ($event.target as HTMLInputElement).checked)" />{{ formatMillisRange(item.startMs, item.endMs) }} {{ item.normalizedText.slice(0, 160) }}</label>
          <button type="button" @click="emit('seek', item.startMs, { evidenceId: item.evidenceId, revision: item.revision })">回看</button>
        </div>
      </div>
      <p v-if="!items.length && !loading">没有可选择的有效课程片段；可以使用整节课程。</p>
      <p>已加载 {{ items.length }} 个可用片段，已选 {{ selected.length }}/16。{{ cursor ? '还有片段尚未加载。' : '' }}</p>
      <button v-if="cursor" type="button" :disabled="loading" @click="load(true)">加载更多片段</button>
    </template>
    <p aria-live="polite">下次使用：{{ modelValue ? scopeLabel(modelValue) : '请确认有效范围后再开始' }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <button type="button" :disabled="loading" @click="load()">{{ loading ? '正在核对范围…' : '刷新范围' }}</button>
    <button v-if="!modelValue && revision !== undefined" type="button" :disabled="kind === 'segments' && !selected.length" @click="publish">确认当前范围</button>
    </details>
    <p v-if="compact && error" role="status">{{ error }}</p>

  </section>
</template>
<style scoped>
.scope-picker { margin-block: 14px; padding: 16px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); }
h3 { margin-top: 0; }.scope-picker label { margin-right: 12px; }.scope-picker p { color: var(--color-ink-soft); }
.scope-items { max-height: 280px; overflow: auto; }.scope-item { display: flex; gap: 8px; padding: 8px 0; align-items: start; }.scope-item label { flex: 1; }
fieldset { margin-block: 12px; border: 1px solid var(--color-border); }.frozen-scope { margin-top: 12px; }
summary { cursor: pointer; line-height: 1.6; }.scope-options > summary { color: var(--color-brand); font-weight: 650; }
.scope-picker button { font: inherit; padding: 6px 9px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); color: var(--color-brand); cursor: pointer; }


.scope-picker--compact { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 6px 12px; }
.scope-picker--compact .frozen-scope { margin: 0; }
.scope-picker--compact summary { font-size: 12px; line-height: 1.5; padding: 4px 0; }
.scope-picker--compact > details[open] { flex-basis: 100%; }
.scope-picker--compact > p { flex-basis: 100%; margin: 4px 0; }
.scope-picker--compact .scope-options > summary { font-weight: 500; }
</style>
