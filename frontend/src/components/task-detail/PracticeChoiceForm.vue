<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { studyCommand } from '../../api/study';
import type { PracticeQuestion, StudyAttempt, StudyCommand } from '../../api/study';
import { mayHaveLostCourseAccess } from '../../api/courseAccess';
import { randomUuid } from '../../utils/randomUuid';
import { formatMillisRange, formatMillisToClock } from '../../utils/time';
import { readDemoPracticeExplanation } from '../../api/round3Demo';
import type { EvidenceSeekContext } from './evidenceSeekGuard';
const props = defineProps<{ taskId: string; sessionId: string; runId: string; artifactId: string; questionIndex: number; question: PracticeQuestion; attempt?: StudyAttempt; sourceRevision?: number; lesson?: boolean; demoPractice?: boolean }>();
const emit = defineEmits<{ saved: [attempt: StudyAttempt]; draftChange: [dirty: boolean]; accessFailure: []; seek: [milliseconds: number, context: EvidenceSeekContext] }>();
const selected = ref('');
const latest = ref<StudyAttempt>();
const explanation = ref("");
const explanationLoading = ref(false);
const explanationError = ref("");
let explanationRequest: AbortController | undefined;
async function explain() {
  if (!props.demoPractice || !latest.value?.choice_result || explanationLoading.value) return;
  explanationRequest?.abort();
  const request = new AbortController();
  explanationRequest = request;
  explanationLoading.value = true;
  explanationError.value = "";
  try { explanation.value = await readDemoPracticeExplanation(props.artifactId, props.questionIndex, request.signal); }
  catch { if (!request.signal.aborted) explanationError.value = "解析暂时无法打开，请重试。"; }
  finally { if (!request.signal.aborted) explanationLoading.value = false; }
}
const clock = (value: number) => formatMillisToClock(value).replace(/^00:/, "");
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
  explanationRequest?.abort(); explanation.value = ''; explanationError.value = ''; explanationLoading.value = false;
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
onBeforeUnmount(() => { generation++; explanationRequest?.abort(); });
function accept(attempt: StudyAttempt) {
  latest.value = attempt; pending = null; history.value = null; emit('saved', attempt);
  message.value = props.lesson ? '答案已保存。' : '选择与判分结果已保存，刷新后可以回看。';
  if (props.demoPractice && !explanation.value) void explain();
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
  <div v-if="lesson" class="practice-choice choice-lesson">
    <fieldset :disabled="saving"><legend class="sr-only">第 {{ questionIndex + 1 }} 题选项 · 单选</legend>
      <label v-for="(option, index) in question.options" :key="option.id" class="choice-option" :class="{ selected: selected === option.id }">
        <strong aria-hidden="true">{{ String.fromCharCode(65 + index) }}</strong><span>{{ option.text }}</span>
        <input v-model="selected" type="radio" :name="`${artifactId}:${questionIndex}`" :value="option.id" />
      </label>
    </fieldset>
    <button class="choice-submit" type="button" :disabled="!canSubmit" @click="submit">
      {{ saving ? '正在保存…' : '提交答案' }} <span aria-hidden="true">→</span>
    </button>
    <article v-if="latest?.choice_result" class="choice-result" :class="{ correct: latest.choice_result.is_correct }"
      aria-label="选择题判分结果" aria-live="polite">
      <h4>{{ latest.choice_result.is_correct ? '答对了' : '再想一想' }}</h4>
      <p v-if="dirty">当前选项尚未提交。以下是上次答案的解析。</p>
      <p>正确选项：{{ optionText(latest.choice_result.correct_option_id) }}</p>
      <p v-if="explanation">{{ explanation }}</p>
      <p v-if="explanationError" role="status">{{ explanationError }}</p>
      <button v-if="demoPractice && !explanation" type="button" :disabled="explanationLoading" @click="explain">
        {{ explanationLoading ? '正在加载解析…' : '查看解析' }}
      </button>
      <details v-if="latest.choice_result.citations.length"><summary>核对课程出处</summary>
        <div v-for="citation in latest.choice_result.citations" :key="citation.evidence_id">
          <blockquote>{{ citation.text }}</blockquote>
          <button type="button" @click="emit('seek', citation.start_ms, { evidenceId: citation.evidence_id, revision: sourceRevision })">回看 {{ clock(citation.start_ms) }}</button>
        </div>
      </details>
      <button v-if="!demoPractice" type="button" :disabled="loadingHistory" @click="showHistory()">作答记录</button>
    </article>
    <p v-if="message" role="status">{{ message }}</p>
    <div v-if="history" class="answer-history">
      <h4>作答记录</h4>
      <article v-for="entry in history" :key="entry.attempt_id"><p>第 {{ entry.version }} 次 · {{ entry.answer_text }}</p></article>
      <button v-if="nextBefore" type="button" :disabled="loadingHistory" @click="showHistory(true)">更早的作答</button>
    </div>
  </div>
  <div v-else class="practice-choice">
    <fieldset :disabled="saving"><legend>第 {{ questionIndex + 1 }} 题选项 · 单选</legend>
      <label v-for="option in question.options" :key="option.id" class="choice-option"><input v-model="selected" type="radio" :name="`${artifactId}:${questionIndex}`" :value="option.id" /> <strong>{{ option.id }}.</strong> {{ option.text }}</label>
    </fieldset>
    <div class="answer-actions"><el-button type="primary" :disabled="!canSubmit" :loading="saving" @click="submit">提交并判分</el-button><span role="status">{{ dirty ? '有未提交的选择' : latest ? `已保存第 ${latest.version} 版` : '尚未选择，未判分' }}</span><el-button v-if="latest" :loading="loadingHistory" @click="showHistory()">修改记录</el-button></div>
    <article v-if="latest?.choice_result" class="choice-result" aria-label="选择题判分结果" aria-live="polite">
      <h4>第 {{ latest.version }} 版 · {{ latest.choice_result.is_correct ? '正确' : '错误' }}</h4>
      <p>结果按本题答案判定。</p><p>本版选择：{{ latest.selected_option_id }}. {{ optionText(latest.selected_option_id!) }}</p>
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

.choice-lesson fieldset { padding: 0; margin: 0; border: 0; gap: 8px; }
.choice-lesson .choice-option { align-items: center; gap: 11px; padding: 10px 12px; min-height: 46px; border: 1px solid var(--color-border); border-radius: 9px; background: var(--color-canvas); cursor: pointer; }
.choice-lesson .choice-option.selected { background: var(--color-brand-soft); border-color: var(--color-brand); }
.choice-lesson .choice-option strong { width: 24px; height: 24px; display: inline-grid; place-items: center; border-radius: 6px; font-size: 13px; color: var(--color-brand); }
.choice-lesson .selected strong { color: white; background: var(--color-brand); }
.choice-lesson .choice-option input { margin: 0 0 0 auto; accent-color: var(--color-brand); }
.choice-lesson button { border: 0; border-radius: 7px; background: transparent; color: var(--color-brand); padding: 7px 9px; font: inherit; font-weight: 650; cursor: pointer; }
.choice-lesson .choice-submit { display: flex; justify-content: space-between; align-items: center; padding: 12px; background: var(--color-brand); color: white; min-height: 46px; }
.choice-lesson .choice-submit:disabled { background: var(--color-surface-subtle); color: var(--color-ink-soft); cursor: default; }
.choice-lesson .choice-result { background: var(--color-evidence-surface); }
.choice-lesson .choice-result.correct { background: var(--color-success-surface); border-color: var(--color-success); }
.choice-lesson .choice-result h4 { margin: 0; }
.choice-lesson .choice-result p { margin: 5px 0; }
.choice-lesson summary { cursor: pointer; color: var(--color-brand); }
</style>
