<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { studyCommand } from '../../api/study';
import type { PracticeQuestion, StudyAttempt, StudyCommand } from '../../api/study';
import { mayHaveLostCourseAccess } from '../../api/courseAccess';
import { randomUuid } from '../../utils/randomUuid';
import { formatMillisRange } from '../../utils/time';
import type { EvidenceSeekContext } from './evidenceSeekGuard';
const props = defineProps<{ taskId: string; sessionId: string; runId: string; artifactId: string; questionIndex: number; question: PracticeQuestion; attempt?: StudyAttempt; sourceRevision?: number }>();
const emit = defineEmits<{ saved: [attempt: StudyAttempt]; draftChange: [dirty: boolean]; accessFailure: []; seek: [milliseconds: number, context: EvidenceSeekContext] }>();
const selected = ref('');
const latest = ref<StudyAttempt>();
const saving = ref(false), loadingHistory = ref(false);
const message = ref('');
const history = ref<StudyAttempt[] | null>(null);
const nextBefore = ref<number | null>(null);
let generation = 0;
let pending: StudyCommand | null = null;
const dirty = computed(() => selected.value !== (latest.value?.selected_option_id ?? ''));
const canSubmit = computed(() => dirty.value && props.question.options?.some(o => o.id === selected.value) && !saving.value);
const scope = () => ({ session_id: props.sessionId, run_id: props.runId, artifact_id: props.artifactId, question_index: props.questionIndex });
const optionText = (id: string) => props.question.options?.find(o => o.id === id)?.text ?? id;
watch(dirty, value => emit('draftChange', value), { immediate: true });
watch(() => [props.taskId, props.sessionId, props.runId, props.artifactId, props.questionIndex], () => {
  generation++; pending = null; latest.value = props.attempt; selected.value = props.attempt?.selected_option_id ?? '';
  history.value = null; nextBefore.value = null; message.value = ''; saving.value = false; loadingHistory.value = false;
}, { immediate: true });
watch(() => props.attempt, value => {
  if (!value || (latest.value && value.version <= latest.value.version)) return;
  const hasDraft = dirty.value;
  if (!hasDraft) selected.value = value.selected_option_id ?? '';
  latest.value = value; pending = null; history.value = null;
  message.value = hasDraft ? '服务器已有新版作答；你的未提交选择仍保留，请核对后再提交。' : '';
});
onBeforeUnmount(() => { generation++; });
function accept(attempt: StudyAttempt) {
  latest.value = attempt; pending = null; history.value = null; emit('saved', attempt);
  message.value = '选择与判分结果已保存，刷新后可以回看。';
}
async function submit() {
  if (!canSubmit.value) return;
  const current = generation;
  if (!pending || pending.selected_option_id !== selected.value) pending = { ...scope(), operation: 'SAVE_ATTEMPT', request_key: randomUuid(), expected_version: latest.value?.version ?? 0, selected_option_id: selected.value };
  const command = pending;
  saving.value = true; message.value = '';
  try {
    const result = await studyCommand(props.taskId, command);
    if (current === generation && result.attempt) accept(result.attempt);
  } catch (failure) {
    if (current !== generation) return;
    if (mayHaveLostCourseAccess(failure)) emit('accessFailure');
    message.value = '提交未确认，选择仍保留。请重试同一次提交。';
    try {
      const result = await studyCommand(props.taskId, { ...scope(), operation: 'READ' });
      if (current !== generation) return;
      const saved = result.attempts?.find(a => a.question_index === props.questionIndex);
      if (saved && saved.selected_option_id === command.selected_option_id && saved.version === (command.expected_version ?? 0) + 1) accept(saved);
      else if (saved && saved.version !== latest.value?.version) {
        latest.value = saved; pending = null; history.value = null; emit('saved', saved);
        message.value = '发现另一份已保存选择；你的选择仍保留，请核对修改记录后再提交。';
      }
    } catch { /* Retain the replay key on an unknown outcome. */ }
  } finally { if (current === generation) saving.value = false; }
}
async function showHistory(more = false) {
  if (loadingHistory.value) return;
  const current = generation; loadingHistory.value = true;
  try {
    const result = await studyCommand(props.taskId, { ...scope(), operation: 'ATTEMPT_HISTORY', ...(more && nextBefore.value ? { before_version: nextBefore.value } : {}) });
    if (current !== generation) return;
    history.value = [...(more ? history.value ?? [] : []), ...result.attempts ?? []];
    nextBefore.value = result.next_before_version ?? null;
  } catch (failure) {
    if (current === generation) { message.value = '修改记录暂不可用，请重试。'; if (mayHaveLostCourseAccess(failure)) emit('accessFailure'); }
  } finally { if (current === generation) loadingHistory.value = false; }
}
defineExpose({ showHistory });
</script>
<template>
  <div class="practice-choice">
    <fieldset :disabled="saving"><legend>第 {{ questionIndex + 1 }} 题选项 · 单选</legend>
      <label v-for="option in question.options" :key="option.id" class="choice-option"><input v-model="selected" type="radio" :name="`${artifactId}:${questionIndex}`" :value="option.id" /> <strong>{{ option.id }}.</strong> {{ option.text }}</label>
    </fieldset>
    <div class="answer-actions"><el-button type="primary" :disabled="!canSubmit" :loading="saving" @click="submit">提交并判分</el-button><span role="status">{{ dirty ? '有未提交的选择' : latest ? `已保存第 ${latest.version} 版` : '尚未选择，未判分' }}</span><el-button v-if="latest" :loading="loadingHistory" @click="showHistory()">修改记录</el-button></div>
    <article v-if="latest?.choice_result" class="choice-result" aria-label="选择题判分结果" aria-live="polite">
      <h4>第 {{ latest.version }} 版 · {{ latest.choice_result.is_correct ? '正确' : '错误' }}</h4>
      <p>程序对照本题答案键判分，不代表掌握程度。</p><p>本版选择：{{ latest.selected_option_id }}. {{ optionText(latest.selected_option_id!) }}</p>
      <p v-if="dirty">以下结果仅对应已保存第 {{ latest.version }} 版；当前选择尚未提交。</p>
      <p class="correct-option">正确选项：{{ latest.choice_result.correct_option_id }}. {{ optionText(latest.choice_result.correct_option_id) }}</p>
      <div v-for="citation in latest.choice_result.citations" :key="citation.evidence_id" class="choice-source"><blockquote>{{ citation.text }}</blockquote><el-button @click="emit('seek', citation.start_ms, { evidenceId: citation.evidence_id, revision: sourceRevision })">{{ formatMillisRange(citation.start_ms, citation.end_ms) }} · 回看判分依据</el-button></div>
    </article>
    <p v-if="message" role="status">{{ message }}</p>
    <div v-if="history" class="answer-history"><h4>已保存的选择</h4><article v-for="entry in history" :key="entry.attempt_id"><strong>第 {{ entry.version }} 版 · {{ entry.selected_option_id }} · {{ entry.choice_result ? (entry.choice_result.is_correct ? '正确' : '错误') : '未判分' }}</strong><p>{{ entry.answer_text }}</p></article><el-button v-if="nextBefore" :loading="loadingHistory" @click="showHistory(true)">更早的修改</el-button></div>
  </div>
</template>
<style scoped>
.practice-choice { display: grid; gap: 12px; } fieldset { display: grid; gap: 10px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: 12px; min-width: 0; } legend { font-size: 13px; } .choice-option { display: flex; gap: 8px; padding: 10px; border-radius: var(--radius-sm); background: var(--color-canvas); line-height: 1.7; overflow-wrap: anywhere; } .choice-option strong { flex-shrink: 0; white-space: nowrap; } .choice-option input { flex-shrink: 0; margin-top: 6px; } .answer-actions { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; } .choice-result,.answer-history { padding: 14px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); } p,blockquote { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; } blockquote { border-left: 3px solid var(--color-border); padding-left: 12px; margin: 10px 0; }
</style>
