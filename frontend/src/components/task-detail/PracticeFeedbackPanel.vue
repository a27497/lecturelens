<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { studyCommand } from "../../api/study";
import type { FeedbackNote, StudyAttempt, StudyCommand, StudyFeedbackRun, StudyResponse } from "../../api/study";
import StudyApprovalPanel from "./StudyApprovalPanel.vue";
import { randomUuid } from "../../utils/randomUuid";
import { mayHaveLostCourseAccess } from "../../api/courseAccess";

import type { EvidenceSeekContext } from "./evidenceSeekGuard";

const props = defineProps<{
  readOnly?: boolean;
  sourceRevision?: number;
  taskId: string; sessionId: string; runId: string; artifactId: string; questionIndex: number;
  answerDirty?: boolean; approvalRequired?: boolean; enabled: boolean; attempt?: StudyAttempt; initial?: StudyFeedbackRun; history?: StudyFeedbackRun[];
}>();
const emit = defineEmits<{ seek: [startMillis: number, context: EvidenceSeekContext]; revise: []; draftChange: [dirty: boolean]; accessFailure: [] }>();
const currentRun = ref<StudyFeedbackRun>();
const previewRun = ref<StudyFeedbackRun>();
const observedRuns = ref<StudyFeedbackRun[]>([]);
const approval = ref<StudyResponse["approval"]>(null);
const starting = ref(false);
const savingNote = ref(false);
const message = ref("");
const noteText = ref("");
const disposition = ref<"disputed" | "acknowledged">("disputed");
const notes = ref<FeedbackNote[] | null>(null);
const nextBefore = ref<number | null>(null);
const loadingNotes = ref(false);
let generation = 0;
let readSequence = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
let pendingStart: StudyCommand | null = null;
let pendingNote: StudyCommand | null = null;
const active = computed(() => currentRun.value && ["queued", "running", "awaiting_approval"].includes(currentRun.value.status));
const feedback = computed(() => currentRun.value?.feedback);
const noteDirty = computed(() => Boolean(noteText.value.trim()) && noteText.value !== (feedback.value?.note?.note_text ?? ""));
watch(noteDirty, value => emit("draftChange", value), { immediate: true });
const historyRuns = computed(() => {
  const rows = new Map((props.history ?? []).map(row => [row.run_id, row]));
  for (const row of observedRuns.value) rows.set(row.run_id, row);
  if (currentRun.value) rows.set(currentRun.value.run_id, currentRun.value);
  return [...rows.values()].filter(row => row.question_index === props.questionIndex);
});
const historyStatus = { awaiting_approval: "等待发布审批", queued: "等待开始", running: "进行中", succeeded: "已完成", cancelled: "已取消", failed: "未完成", budget_exceeded: "达到执行上限" };
const scope = () => ({ session_id: props.sessionId, run_id: props.runId, artifact_id: props.artifactId, question_index: props.questionIndex });

watch(() => [props.taskId, props.sessionId, props.runId, props.artifactId, props.questionIndex], () => {
  previewRun.value = undefined;
  generation++; clearTimeout(timer); pendingStart = null; pendingNote = null;
  observedRuns.value = []; currentRun.value = props.initial; starting.value = false; savingNote.value = false;
  message.value = ""; noteText.value = ""; notes.value = null; nextBefore.value = null;
  if (active.value || currentRun.value?.status === "awaiting_approval") schedule();
  else if (props.readOnly && currentRun.value) void refresh();
}, { immediate: true });
watch(() => props.initial, value => {
  if (value && !starting.value && !active.value && !noteDirty.value) currentRun.value = value;
  if (props.readOnly && value) void refresh();
  if (active.value) schedule();
});
onBeforeUnmount(() => { generation++; clearTimeout(timer); });

function rememberRun() {
  if (currentRun.value) observedRuns.value = [...observedRuns.value.filter(row => row.run_id !== currentRun.value!.run_id), currentRun.value].slice(-20);
}
async function changeFeedback(event: Event) {
  const select = event.target as HTMLSelectElement;
  const selected = select.value;
  select.value = currentRun.value?.run_id ?? "";
  await selectRun(selected);
}
async function selectRun(id: string) {
  if (starting.value || savingNote.value || loadingNotes.value) { message.value = "正在保存或读取记录，请完成后再打开反馈。"; return; }
  const selected = historyRuns.value.find(row => row.run_id === id);
  if (!selected) return;
  if (selected.run_id === currentRun.value?.run_id) { await refresh(); return; }
  if (active.value) {
    if (selected.status === "succeeded" && selected.feedback) previewRun.value = { ...selected };
    else message.value = "新版反馈仍在执行，仅可只读打开已完成反馈。";
    return;
  }
  if (noteDirty.value && !window.confirm("切换反馈会放弃本页未保存的核对文字。确定继续吗？")) return;
  rememberRun(); generation++; clearTimeout(timer);
  currentRun.value = selected; pendingStart = null; pendingNote = null;
  noteText.value = ""; notes.value = null; nextBefore.value = null; message.value = "";
  await refresh();
}

function schedule() {
  clearTimeout(timer);
  timer = setTimeout(() => { void refresh(); }, 1500);
}
async function refresh() {
  if (!currentRun.value) return;
  const current = generation; const id = currentRun.value.run_id; const request = ++readSequence;
  try {
    const result = await studyCommand(props.taskId, { operation: "READ", session_id: props.sessionId, run_id: id });
    if (current !== generation || request !== readSequence || currentRun.value?.run_id !== id) return;
    const hadDraft = noteDirty.value;
    const priorNoteVersion = feedback.value?.note?.version ?? 0;
    if (result.run) currentRun.value = { ...currentRun.value, status: result.run.status, error_code: result.run.error_code, feedback: result.feedback ?? null };
    approval.value = result.approval ?? null;
    const changedNote = priorNoteVersion !== (feedback.value?.note?.version ?? 0);
    if (changedNote) { notes.value = null; pendingNote = null; }
    message.value = hadDraft && changedNote ? "服务器核对记录已更新；本页未保存文字已保留，请核对后再保存。" : "";
  } catch (error) {
    if (current === generation && request === readSequence) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status && [401, 403, 404, 409].includes(status) && currentRun.value) {
        currentRun.value = { ...currentRun.value, status: "failed", error_code: "COURSE_UNAVAILABLE_OR_CHANGED", feedback: null };
        notes.value = null; approval.value = null;
        if (mayHaveLostCourseAccess(error)) emit("accessFailure");
        message.value = "课程、会话或登录状态已变化，请重新打开课程。";
      } else message.value = "反馈连接暂时中断，正在恢复。";
    }
  }
  finally { if (current === generation && request === readSequence && active.value) schedule(); }
}
async function start() {
  if (props.readOnly || props.answerDirty) return;
  if (!props.enabled || !props.attempt || active.value || currentRun.value?.status === "awaiting_approval" || starting.value || savingNote.value) return;
  const current = generation;
  const answer = props.attempt;
  if (!pendingStart || pendingStart.attempt_id !== answer.attempt_id) pendingStart = {
    ...scope(), operation: "START_FEEDBACK", attempt_id: answer.attempt_id, request_key: randomUuid(), approval_required: props.approvalRequired ?? false,
  };
  const command = pendingStart;
  starting.value = true; message.value = "";
  try {
    const result = await studyCommand(props.taskId, command);
    if (current !== generation) return;
    if (result.run) {
      rememberRun();
      currentRun.value = { run_id: result.run.run_id, status: result.run.status, error_code: result.run.error_code,
        attempt_id: answer.attempt_id, answer_version: answer.version, question_index: props.questionIndex, feedback: result.feedback ?? null };
      pendingStart = null; pendingNote = null; noteText.value = ""; notes.value = null;
      if (active.value) schedule();
    }
  } catch (failure) {
    if (current !== generation) return;
    if (mayHaveLostCourseAccess(failure)) emit("accessFailure");
    message.value = "反馈请求未确认。请等待当前学习任务结束，或重试同一请求。";
    try {
      const result = await studyCommand(props.taskId, { ...scope(), operation: "READ" });
      if (current !== generation) return;
      const recovered = result.feedback_runs?.find(run => run.request_key === command.request_key);
      if (recovered) { rememberRun(); currentRun.value = recovered; pendingStart = null; message.value = ""; if (active.value) schedule(); }
    } catch { /* Retain the idempotency key. */ }
  } finally { if (current === generation) starting.value = false; }
}
async function cancel() {
  readSequence++;
  if (!currentRun.value || !active.value) return;
  const current = generation;
  try {
    const result = await studyCommand(props.taskId, { operation: "CANCEL", session_id: props.sessionId, run_id: currentRun.value.run_id });
    if (current === generation && result.run && currentRun.value) {
      currentRun.value = { ...currentRun.value, status: result.run.status }; clearTimeout(timer);
    }
  } catch (failure) { if (current === generation) { message.value = "取消未确认，请重试。"; if (mayHaveLostCourseAccess(failure)) emit("accessFailure"); if (active.value) schedule(); } }
}
async function saveNote() {
  if (props.readOnly || !feedback.value || !currentRun.value || !noteText.value.trim() || noteText.value.length > 2000 || savingNote.value) return;
  const current = generation;
  if (!pendingNote || pendingNote.note_text !== noteText.value || pendingNote.disposition !== disposition.value) pendingNote = {
    operation: "SAVE_FEEDBACK_NOTE", session_id: props.sessionId, run_id: currentRun.value.run_id,
    feedback_id: feedback.value.feedback_id, request_key: randomUuid(), expected_version: feedback.value.note?.version ?? 0,
    note_text: noteText.value, disposition: disposition.value,
  };
  const command = pendingNote;
  readSequence++; savingNote.value = true;
  try {
    const result = await studyCommand(props.taskId, command);
    if (current !== generation || feedback.value?.feedback_id !== command.feedback_id) return;
    if (result.note) { feedback.value.note = result.note; pendingNote = null; notes.value = null; message.value = "你的核对意见已保存，原反馈和作答保持可查看。"; }
  } catch (failure) {
    if (current !== generation) return;
    if (mayHaveLostCourseAccess(failure)) emit("accessFailure");
    await refresh();
    if (current !== generation || feedback.value?.feedback_id !== command.feedback_id) return;
    const saved = feedback.value?.note;
    if (saved?.note_text === command.note_text && saved?.disposition === command.disposition && saved?.version === (command.expected_version ?? 0) + 1) {
      pendingNote = null; message.value = "核对意见已保存。";
    } else {
      if (saved && saved.version !== command.expected_version) pendingNote = null;
      message.value = "核对意见保存未确认，请查看最新记录后重试；你的文字仍在本页。";
    }
  } finally { if (current === generation) savingNote.value = false; }
}
async function showNotes(more = false) {
  if (!feedback.value || !currentRun.value || loadingNotes.value) return;
  const current = generation; const feedbackId = feedback.value.feedback_id; loadingNotes.value = true;
  try {
    const result = await studyCommand(props.taskId, { operation: "FEEDBACK_NOTES", session_id: props.sessionId,
      run_id: currentRun.value.run_id, feedback_id: feedback.value.feedback_id, ...(more && nextBefore.value ? { before_version: nextBefore.value } : {}) });
    if (current === generation && feedback.value?.feedback_id === feedbackId) { notes.value = [...(more ? notes.value ?? [] : []), ...result.notes ?? []]; nextBefore.value = result.next_before_version ?? null; }
  } catch (failure) { if (current === generation) { message.value = "核对记录暂不可用，请重试。"; if (mayHaveLostCourseAccess(failure)) emit("accessFailure"); } }
  finally { if (current === generation) loadingNotes.value = false; }
}
async function showFeedback(row: StudyFeedbackRun) {
  if (row.question_index !== props.questionIndex) return;
  observedRuns.value = [...observedRuns.value.filter(item => item.run_id !== row.run_id), row];
  await selectRun(row.run_id);
}
defineExpose({ showFeedback });
</script>

<template>
  <section class="practice-feedback" :aria-label="`第 ${questionIndex + 1} 题证据反馈`">
    <label v-if="historyRuns.length > 1" class="feedback-history">最近反馈
      <select :value="currentRun?.run_id" :aria-label="`第 ${questionIndex + 1} 题反馈记录`" :disabled="Boolean(active) || starting || savingNote || loadingNotes" @change="changeFeedback">
        <option v-for="(previous, index) in historyRuns" :key="previous.run_id" :value="previous.run_id">{{ index + 1 }} · 第 {{ previous.answer_version }} 版作答 · {{ historyStatus[previous.status] }}</option>
      </select>
    </label>
    <div class="feedback-actions">
      <el-button v-if="enabled && !readOnly" :type="feedback ? 'default' : 'primary'" :disabled="answerDirty || !attempt || Boolean(active) || currentRun?.status === 'awaiting_approval' || starting || savingNote" :loading="starting" @click="start">{{ currentRun ? '重新获取证据反馈' : '获取证据反馈' }}</el-button>
      <span v-if="answerDirty" role="status">请先保存本页修改，再获取新版反馈；下方已有反馈仍对应其已保存版本。</span>
      <span v-else-if="attempt" class="feedback-version">将使用已保存第 {{ attempt.version }} 版作答</span>
      <span v-if="!attempt">先保存作答，再结合课程证据获取建议。</span>
      <span v-if="active" role="status">{{ currentRun?.status === 'awaiting_approval' ? '等待发布审批' : '正在阅读证据并复核反馈…' }}</span>
      <el-button v-if="active" @click="cancel">取消反馈</el-button>
    </div>
    <StudyApprovalPanel v-if="currentRun?.status === 'awaiting_approval' && approval" :task-id="taskId" :session-id="sessionId" :run-id="currentRun.run_id" :approval="approval" @decided="refresh" />
    <p v-if="currentRun && ['failed', 'cancelled', 'budget_exceeded'].includes(currentRun.status)" role="status">{{ currentRun.status === 'cancelled' ? '反馈已取消。' : '本次未完成可靠反馈，可以重试。' }}已保存作答不受影响。</p>
    <article v-if="feedback">
      <h4>第 {{ feedback.answer_version }} 版作答的证据反馈</h4>
      <p v-if="feedback.content.mode === 'mock'">演示反馈，不代表模型判断。</p>
      <p v-else>实验阶段的学习建议，可核对和更正，不作为成绩或掌握程度记录。</p>
      <p v-if="attempt && feedback.attempt_id !== attempt.attempt_id" role="status">你已保存新版作答，下面反馈仅对应旧版。</p>
      <el-button @click="$emit('revise')">修订本题作答</el-button>
      <details><summary>查看本次反馈对应的作答</summary><p>{{ feedback.answer_text }}</p></details>
      <p v-if="feedback.content.kind === 'insufficient_evidence'">{{ feedback.content.reason }}</p>
      <p v-if="feedback.content.human_guidance">人工修改建议：{{ feedback.content.human_guidance }}</p>
      <div v-for="(item, index) in feedback.content.observations" :key="index" class="feedback-observation">
        <p>你的表述：“{{ item.learner_quote }}”</p><p>{{ item.observation }}</p><p>下一步：{{ item.next_step }}</p>
        <details :open="(item.evidence_ids?.length ?? 1) === 1">
          <summary>查看课程证据（{{ item.evidence_ids?.length ?? 1 }} 段）</summary>
          <blockquote>{{ item.evidence_quote }}</blockquote>
          <template v-for="(id, citationIndex) in item.evidence_ids ?? [item.evidence_id]" :key="id">
            <el-button v-if="feedback.content.citations.some(c => c.evidence_id === id)" text @click="$emit('seek', feedback.content.citations.find(c => c.evidence_id === id)!.start_ms, { evidenceId: id, revision: sourceRevision })">{{ (item.evidence_ids?.length ?? 1) > 1 ? `回看课程证据 ${citationIndex + 1}` : '回看这段课程证据' }}</el-button>
          </template>
        </details>
      </div>
      <details v-if="!feedback.content.observations?.length && feedback.content.citations.length" class="feedback-sources" open>
        <summary>反馈使用的课程材料（不代表已判断作答）</summary>
        <div v-for="citation in feedback.content.citations" :key="citation.evidence_id">
          <blockquote>{{ citation.text }}</blockquote>
          <el-button text @click="$emit('seek', citation.start_ms, { evidenceId: citation.evidence_id, revision: sourceRevision })">回看这段课程证据</el-button>
        </div>
      </details>
      <div v-if="feedback.note" class="feedback-note"><strong>{{ feedback.note.disposition === 'disputed' ? '你已标记反馈不准确' : '你已核对反馈' }}</strong><p>{{ feedback.note.note_text }}</p></div>
      <details v-if="!readOnly"><summary>核对或更正反馈</summary>
        <label>核对结果 <select v-model="disposition" :disabled="savingNote"><option value="disputed">反馈不准确</option><option value="acknowledged">已核对</option></select></label>
        <el-input v-model="noteText" type="textarea" :rows="2" maxlength="2000" :disabled="savingNote" placeholder="说明你核对到的问题或更正依据。" aria-label="反馈核对意见" />
        <el-button :disabled="!noteText.trim() || savingNote" :loading="savingNote" @click="saveNote">保存核对意见</el-button>
        <el-button v-if="feedback.note" :loading="loadingNotes" @click="showNotes()">核对记录</el-button>
        <div v-if="notes"><p v-for="note in notes" :key="note.note_id">第 {{ note.version }} 版 · {{ note.disposition === 'disputed' ? '反馈不准确' : '已核对' }}：{{ note.note_text }}</p><el-button v-if="nextBefore" @click="showNotes(true)">更早的核对记录</el-button></div>
      </details>
    </article>
    <aside v-if="previewRun" class="feedback-preview" aria-label="旧版反馈只读预览">
      <p>正在只读查看旧版反馈；新版反馈继续执行，本页核对草稿保留。</p>
      <el-button @click="previewRun = undefined">关闭旧版反馈</el-button>
      <PracticeFeedbackPanel :key="previewRun.run_id" :read-only="true" :enabled="false" :task-id="taskId" :session-id="sessionId" :run-id="runId" :artifact-id="artifactId" :question-index="questionIndex" :source-revision="sourceRevision" :initial="previewRun" :attempt="attempt" @seek="(milliseconds, context) => $emit('seek', milliseconds, context)" @revise="$emit('revise')" @access-failure="$emit('accessFailure')" />
    </aside>
    <p v-if="message" role="status">{{ message }}</p>
  </section>
</template>

<style scoped>
.practice-feedback { display: grid; gap: 8px; border-top: 1px solid var(--color-border); padding-top: 12px; }
.feedback-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
p, blockquote { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; }
blockquote { margin: 8px 0; border-left: 3px solid var(--color-border); padding-left: 12px; }
.feedback-note { background: var(--color-canvas); padding: 12px; }
summary { cursor: pointer; } select { max-width: 100%; margin: 8px; }


.practice-feedback article { padding: 14px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface-subtle); }
.practice-feedback h4 { color: var(--color-ink); margin-block: 0 8px; }
.feedback-version { font-size: 12px; color: var(--color-ink-soft); }
.feedback-observation { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--color-border); }
</style>
