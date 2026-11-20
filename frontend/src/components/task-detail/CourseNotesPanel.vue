<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { formatMillisToClock } from "../../utils/time";
import { randomUuid } from "../../utils/randomUuid";
import { courseNotesKey, readCourseNotes, updateCourseNotes, type CourseNote, type NoteAnchor } from "./courseNotes";

const props = defineProps<{ userId: number; taskId: string; playbackMs?: number; citation?: NoteAnchor; jumpError?: string }>();
const emit = defineEmits<{ jump: [anchor: NoteAnchor]; clearCitation: [] }>();
const key = computed(() => courseNotesKey(props.userId, props.taskId));
const notes = ref<CourseNote[]>([]);
const draft = ref("");
const frozenPlayback = ref<number>();
const status = ref("");
const error = ref("");
const pendingDelete = ref<string>();
const editor = ref<HTMLTextAreaElement | null>(null);
let deleteRow: Element | null = null;
const anchor = computed<NoteAnchor | null>(() => {
  if (props.citation) return props.citation;
  const milliseconds = draft.value ? frozenPlayback.value : props.playbackMs;
  return milliseconds === undefined ? null : { kind: "playback", milliseconds };
});

function refresh() {
  try {
    notes.value = readCourseNotes(window.localStorage, key.value);
    error.value = "";
  } catch {
    notes.value = [];
    error.value = "无法读取此课程的本地笔记。请检查浏览器存储后重试。";
  }
}

function sync(event: StorageEvent) {
  if (event.key === null || event.key === key.value) refresh();
}

function persist(change: (current: CourseNote[]) => CourseNote[], message: string) {
  try {
    notes.value = updateCourseNotes(window.localStorage, key.value, change);
    error.value = "";
    status.value = message;
    return true;
  } catch {
    status.value = "";
    error.value = "无法更新本地笔记。请检查浏览器存储后重试。";
    return false;
  }
}

function clearDraft() {
  draft.value = "";
  frozenPlayback.value = undefined;
  emit("clearCitation");
}

function updateDraft(event: Event) {
  if (!draft.value) frozenPlayback.value = props.playbackMs;
  draft.value = (event.target as HTMLTextAreaElement).value;
}

function save() {
  const text = draft.value.trim();
  if (!text) return;
  const note: CourseNote = { id: randomUuid(), text, anchor: anchor.value };
  if (persist(current => [note, ...current], "笔记已保存。")) clearDraft();
}

async function requestDelete(id: string, event: MouseEvent) {
  deleteRow = (event.currentTarget as HTMLElement).closest("li");
  pendingDelete.value = id;
  await nextTick();
  deleteRow?.querySelector<HTMLButtonElement>(".note-confirm-delete")?.focus();
}

async function cancelDelete() {
  pendingDelete.value = undefined;
  await nextTick();
  deleteRow?.querySelector<HTMLButtonElement>(".note-delete")?.focus();
}

function remove(id: string) {
  if (persist(current => current.filter(note => note.id !== id), "笔记已删除。")) {
    pendingDelete.value = undefined;
    editor.value?.focus();
  }
}

watch(key, () => {
  draft.value = "";
  frozenPlayback.value = undefined;
  pendingDelete.value = undefined;
  status.value = "";
  refresh();
}, { immediate: true });
onMounted(() => window.addEventListener("storage", sync));
onUnmounted(() => window.removeEventListener("storage", sync));
defineExpose({ focusEditor: () => editor.value?.focus() });
</script>

<template>
  <section class="notes" aria-labelledby="course-notes-title">
    <header>
      <h2 id="course-notes-title">个人笔记</h2>
      <p>仅保存在此浏览器和当前账户。</p>
    </header>

    <form @submit.prevent="save">
      <div v-if="anchor" class="note-location">
        <span class="note-time">{{ formatMillisToClock(anchor.milliseconds) }} · {{ anchor.kind === 'evidence' ? '当前证据' : '播放位置' }}</span>
        <button v-if="citation" class="note-button" type="button" @click="$emit('clearCitation')">改用播放位置</button>
      </div>
      <p v-else class="note-muted">暂无播放位置，笔记将仅保存文字。</p>
      <label for="course-note-text">记录你的理解</label>
      <textarea id="course-note-text" ref="editor" rows="4" :value="draft" @input="updateDraft" />
      <div class="note-actions">
        <button v-if="draft || citation" class="note-button" type="button" @click="clearDraft">取消</button>
        <button class="note-button note-button--primary" type="submit" :disabled="!draft.trim()">保存笔记</button>
      </div>
    </form>

    <p v-if="status" class="note-status" role="status">{{ status }}</p>
    <div v-if="error" class="note-error" role="alert">{{ error }} <button class="note-button" type="button" @click="refresh">重新读取</button></div>
    <p v-if="jumpError" class="note-error" role="alert">{{ jumpError }}</p>

    <h3>已保存的笔记</h3>
    <p v-if="!notes.length && !error" class="note-muted">本课程还没有个人笔记。</p>
    <ul v-if="notes.length" class="note-list">
      <li v-for="note in notes" :key="note.id">
        <button v-if="note.anchor" class="note-time note-time--link" type="button" @click="$emit('jump', note.anchor)">
          {{ note.anchor.kind === 'evidence' ? '定位出处' : '跳到播放位置' }} {{ formatMillisToClock(note.anchor.milliseconds) }}
        </button>
        <p>{{ note.text }}</p>
        <div v-if="pendingDelete === note.id" class="note-actions">
          <button class="note-button" type="button" @click="cancelDelete">保留笔记</button>
          <button class="note-button note-button--danger note-confirm-delete" type="button" @click="remove(note.id)">确认删除</button>
        </div>
        <button v-else class="note-button note-button--danger note-delete" type="button" @click="requestDelete(note.id, $event)">删除笔记</button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.notes { display: grid; gap: 12px; min-width: 0; }
.notes h2, .notes h3, .notes p { margin: 0; overflow-wrap: anywhere; }
.notes header p, .note-muted { color: var(--color-ink-soft); font-size: 14px; line-height: 1.65; }
.notes form, .note-list li { min-width: 0; padding: 16px; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); }
.notes form, .note-list li, .note-list { display: grid; gap: 12px; }
.notes label { font-weight: 650; }
.notes textarea { width: 100%; min-width: 0; padding: 12px; border: 1px solid var(--color-border-strong); border-radius: var(--radius-md); color: var(--color-ink); background: var(--color-surface); font-size: 16px; line-height: 1.65; resize: vertical; }
.note-list { list-style: none; margin: 0; padding: 0; }
.note-list li p { white-space: pre-wrap; line-height: 1.65; }
.note-location, .note-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.note-actions { justify-content: flex-end; }
.note-button, .note-time { justify-self: start; padding: 8px 12px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-ink); }
.note-button, .note-time--link { cursor: pointer; }
.note-time { color: var(--color-warning); background: var(--color-evidence-surface); font-size: 13px; font-variant-numeric: tabular-nums; }
.note-button--primary { background: var(--color-brand); color: white; border-color: var(--color-brand); }
.note-button--primary:disabled { opacity: .55; cursor: default; }
.note-button--danger, .note-error { color: var(--color-danger); }
.note-status { color: var(--color-success); }
.note-error { padding: 8px 12px; background: var(--color-danger-surface); border-radius: var(--radius-md); }
@media (max-width: 1024px) { button { min-height: 44px; } }
</style>
