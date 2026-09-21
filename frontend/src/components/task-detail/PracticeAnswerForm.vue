<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { studyCommand } from "../../api/study";
import type { StudyAttempt, StudyCommand } from "../../api/study";

const props = defineProps<{
  taskId: string; sessionId: string; runId: string; artifactId: string; questionIndex: number;
  attempt?: StudyAttempt;
}>();
const emit = defineEmits<{ saved: [attempt: StudyAttempt] }>();
const text = ref("");
const latest = ref<StudyAttempt>();
const saving = ref(false);
const loadingHistory = ref(false);
const history = ref<StudyAttempt[] | null>(null);
const nextBefore = ref<number | null>(null);
const message = ref("");
let generation = 0;
let pending: StudyCommand | null = null;
const dirty = computed(() => text.value !== (latest.value?.answer_text ?? ""));
const canSave = computed(() => dirty.value && text.value.trim().length > 0 && text.value.length <= 4000 && !saving.value);
const scope = () => ({ session_id: props.sessionId, run_id: props.runId, artifact_id: props.artifactId, question_index: props.questionIndex });

watch(() => [props.taskId, props.sessionId, props.runId, props.artifactId, props.questionIndex], () => {
  generation++; pending = null; latest.value = props.attempt; text.value = props.attempt?.answer_text ?? "";
  history.value = null; message.value = ""; saving.value = false; loadingHistory.value = false; nextBefore.value = null;
}, { immediate: true });
watch(() => props.attempt, value => {
  if (!value || (latest.value && value.version <= latest.value.version)) return;
  if (!dirty.value) text.value = value.answer_text;
  latest.value = value;
});
onBeforeUnmount(() => { generation++; });

function accept(attempt: StudyAttempt) {
  latest.value = attempt; emit("saved", attempt); pending = null; history.value = null;
  message.value = "作答已保存，刷新后可以继续。";
}

async function save() {
  if (!canSave.value) return;
  const current = generation; const task = props.taskId;
  if (!pending || pending.answer_text !== text.value) pending = {
    ...scope(), operation: "SAVE_ATTEMPT", request_key: crypto.randomUUID(),
    expected_version: latest.value?.version ?? 0, answer_text: text.value,
  };
  const command = pending;
  saving.value = true; message.value = "";
  try {
    const result = await studyCommand(task, command);
    if (current === generation && result.attempt) accept(result.attempt);
  } catch {
    if (current !== generation) return;
    message.value = "保存未确认，你的文字仍在本页。请重试保存。";
    try {
      const result = await studyCommand(task, { ...scope(), operation: "READ" });
      if (current !== generation) return;
      const saved = result.attempts?.find(row => row.question_index === props.questionIndex);
      if (saved && saved.answer_text === command.answer_text && saved.version === (command.expected_version ?? 0) + 1) accept(saved);
      else if (saved && saved.version !== (latest.value?.version ?? 0)) {
        latest.value = saved; pending = null; history.value = null; emit("saved", saved);
        message.value = "发现另一份已保存修改。你的文字仍保留，请核对修改记录后再保存。";
      }
    } catch { /* Keep the request key and the learner's text for a safe retry. */ }
  } finally { if (current === generation) saving.value = false; }
}

async function showHistory(more = false) {
  if (loadingHistory.value) return;
  const current = generation;
  loadingHistory.value = true;
  try {
    const result = await studyCommand(props.taskId, {
      ...scope(), operation: "ATTEMPT_HISTORY", ...(more && nextBefore.value ? { before_version: nextBefore.value } : {}),
    });
    if (current !== generation) return;
    history.value = [...(more ? history.value ?? [] : []), ...result.attempts ?? []];
    nextBefore.value = result.next_before_version ?? null;
  } catch { if (current === generation) message.value = "修改记录暂不可用，请重试。"; }
  finally { if (current === generation) loadingHistory.value = false; }
}
</script>

<template>
  <div class="practice-answer">
    <el-input v-model="text" type="textarea" :rows="3" maxlength="4000" :disabled="saving" placeholder="写下你的理解，然后保存作答。" :aria-label="`第 ${questionIndex + 1} 题作答`" />
    <div class="answer-actions">
      <el-button :disabled="!canSave" :loading="saving" @click="save">保存作答</el-button>
      <span role="status">{{ dirty ? '有尚未保存的修改' : latest ? `已保存第 ${latest.version} 版` : '尚未作答' }}</span>
      <el-button v-if="latest" text :loading="loadingHistory" @click="showHistory()">修改记录</el-button>
    </div>
    <p v-if="message" role="status">{{ message }}</p>
    <div v-if="history" class="answer-history">
      <h4>已保存的作答</h4>
      <article v-for="entry in history" :key="entry.attempt_id"><strong>第 {{ entry.version }} 版</strong><p>{{ entry.answer_text }}</p></article>
      <el-button v-if="nextBefore" :loading="loadingHistory" @click="showHistory(true)">更早的修改</el-button>
    </div>
  </div>
</template>

<style scoped>
.practice-answer { display: grid; gap: 8px; }
.answer-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.answer-actions span { color: var(--color-ink-soft); font-size: 13px; }
.answer-history { padding: 12px; background: var(--color-canvas); border-radius: var(--radius-md); }
p { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; }
</style>
