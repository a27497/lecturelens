<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { getEvidenceIndexStatus } from "../../api/qa";
import { studyCommand as sendStudyCommand, studyEvents, studyStatus } from "../../api/study";
import type { StudyArtifact, StudyEvent, StudyRun, PracticeQuestion, StudyAttempt, StudyResponse, StudyFeedbackRun, StudyCommand, PracticeResult } from "../../api/study";
import { mayHaveLostCourseAccess } from "../../api/courseAccess";
import type { LearningTaskPosition } from "./learningTaskPosition";
import StudyApprovalPanel from "./StudyApprovalPanel.vue";
import RunTracePanel from "./RunTracePanel.vue";
import { recruiterDemo, recruiterDemoEnabled, demoGoals } from "../../recruiterDemo";
import { practiceContinuation } from "./practiceContinuation";
import PracticeResultsPanel from "./PracticeResultsPanel.vue";
import PracticeAnswerForm from "./PracticeAnswerForm.vue";
import PracticeFeedbackPanel from "./PracticeFeedbackPanel.vue";
import { toUserFriendlyError } from "../../utils/errorMessage";
import { modelError } from "../../api/models";
import { formatMillisRange } from "../../utils/time";
import { randomUuid } from "../../utils/randomUuid";

import type { EvidenceSeekContext } from "./evidenceSeekGuard";

import type { LearningScope } from "../../api/learningScope";
const props = defineProps<{ taskId: string; status?: string; compact?: boolean; learningScope?: LearningScope | null }>();
const emit = defineEmits<{ frozenScope: [scope: LearningScope | null | undefined]; seek: [startTimeMillis: number, context: EvidenceSeekContext]; navigate: [workspace: "overview" | "content"]; position: [position: LearningTaskPosition | null]; accessFailure: [] }>();
const enabled = ref<boolean | null>(null);
const readinessText = ref("课程资料正在准备，完成后即可开始学习。");
const ready = ref(false);
const loading = ref(true);
const submitting = ref(false);
const error = ref("");
const goal = ref("");
const sessionId = ref("");
const sourceRevision = ref<number>();
const run = ref<StudyRun | null>(null);
const artifact = ref<StudyArtifact | null>(null);
const events = ref<StudyEvent[]>([]);
const answers = ref<PracticeQuestion[] | null>(null);
const revealing = ref(false);
const attempts = ref<StudyAttempt[]>([]);
const sessions = ref<NonNullable<StudyResponse['sessions']>>([]);
const recentRuns = ref<NonNullable<StudyResponse['runs']>>([]);
const approvalRequired = ref(false);
const approval = ref<StudyResponse["approval"]>(null);
const feedbackEnabled = ref(false);
const feedbackRuns = ref<StudyFeedbackRun[]>([]);
const questionIndex = ref(0);
const resultsOpen = ref(false);
const progressRows = ref<PracticeResult[] | null>(null);
const progressLoading = ref(false);
const progressError = ref("");
let progressSequence = 0;
const continuation = computed(() => progressRows.value ? practiceContinuation(progressRows.value, feedbackRuns.value) : null);
function acceptProgress(response: StudyResponse) {
  const rows = response.practice_results;
  const count = artifact.value?.questions.length ?? 0;
  const validRows = rows && rows.length === count && new Set(rows.map(row => row.question_index)).size === count
    && rows.every(row => Number.isInteger(row.question_index) && row.question_index >= 0 && row.question_index < count);
  if (!artifact.value || response.run?.run_id !== run.value?.run_id || response.artifact?.artifact_id !== artifact.value.artifact_id || !validRows) {
    progressRows.value = null;
    progressError.value = "学习进度暂时无法读取，请刷新重试；已保存记录不受影响。";
    return false;
  }
  progressRows.value = rows!; progressError.value = "";
  feedbackRuns.value = response.feedback_runs ?? [];
  observeAttempts(response.attempts ?? rows!.flatMap(row => row.attempt ? [row.attempt] : []));
  return true;
}
async function refreshProgress() {
  if (!run.value || !artifact.value) return false;
  const current = version; const request = ++progressSequence;
  const task = props.taskId; const id = run.value.run_id; const artifactId = artifact.value.artifact_id;
  progressLoading.value = true; progressError.value = "";
  try {
    const response = await studyCommand(task, { operation: "READ", session_id: sessionId.value, run_id: id });
    if (current !== version || request !== progressSequence || run.value?.run_id !== id || artifact.value?.artifact_id !== artifactId) return false;
    return acceptProgress(response);
  } catch (failure) {
    if (current === version && request === progressSequence) {
      progressRows.value = null;
      progressError.value = (failure as { response?: { status?: number } })?.response?.status === 409 ? "课程版本或学习记录已变化，请重新打开课程核对；已保存记录不受影响。" : "学习进度暂时无法读取，请刷新重试；已保存记录不受影响。";
      if (mayHaveLostCourseAccess(failure)) emit("accessFailure");
    }
    return false;
  } finally { if (current === version && request === progressSequence) progressLoading.value = false; }
}
async function continuePractice() {
  const expected = continuation.value; const current = version;
  if (!expected || progressLoading.value || !await refreshProgress()) return;
  if (current !== version) return;
  const next = continuation.value;
  // Recheck before navigating: another tab may have saved a different answer or note.
  if (!next || next.index !== expected.index || next.label !== expected.label || next.feedback?.run_id !== expected.feedback?.run_id) {
    progressError.value = "学习进度已更新，请按最新提示继续。";
    return;
  }
  await openResult(next.index, next.feedback ? "feedback" : "question", next.feedback);
}
function savedAttempt(value: StudyAttempt) {
  observeAttempts([value]);
  void refreshProgress();
}
const resultsElement = ref<HTMLElement>();
async function toggleResults() {
  if (resultsOpen.value) { await chooseQuestion(questionIndex.value); return; }
  resultsOpen.value = true;
  await nextTick();
  resultsElement.value?.scrollIntoView({ block: "start" });
  resultsElement.value?.focus({ preventScroll: true });
}
const answerForms = new Map<number, { showHistory: () => Promise<void> }>();
function observeAttempts(rows: StudyAttempt[]) {
  const latest = new Map(attempts.value.map(row => [row.question_index, row]));
  for (const row of rows) if (row.artifact_id === artifact.value?.artifact_id && row.version > (latest.get(row.question_index)?.version ?? 0)) latest.set(row.question_index, row);
  attempts.value = [...latest.values()];
}
const feedbackPanels = new Map<number, { showFeedback: (row: StudyFeedbackRun) => Promise<void> }>();
async function openResult(index: number, kind: "question" | "history" | "feedback", feedback?: StudyFeedbackRun) {
  const current = version;
  await chooseQuestion(index);
  if (current !== version) return;
  if (kind === "history") await answerForms.get(index)?.showHistory();
  if (kind === "feedback" && feedback) {
    // An older persisted result may be outside the recent-feedback window, including when generation is disabled.
    if (!feedbackPanels.has(index)) { feedbackRuns.value = [...feedbackRuns.value, feedback]; await nextTick(); }
    await feedbackPanels.get(index)?.showFeedback(feedback);
  }
}

async function seekResult(milliseconds: number, context: EvidenceSeekContext, index: number) {
  await chooseQuestion(index);
  emit("seek", milliseconds, context);
}
const newGoalOpen = ref(false);
const historyElement = ref<HTMLDetailsElement>();
function showHistory() {
  if (!historyElement.value) return;
  historyElement.value.open = true;
  historyElement.value.scrollIntoView({ block: "nearest" });
  historyElement.value.querySelector<HTMLElement>("summary")?.focus();
}
const hasDrafts = computed(() => [...Object.values(questionDrafts.value), ...Object.values(feedbackDrafts.value)].some(Boolean));
const questionDrafts = ref<Record<number, boolean>>({});
const feedbackDrafts = ref<Record<number, boolean>>({});
const questionElements = new Map<number, HTMLElement>();
const preparing = computed(() => Boolean(props.status && props.status !== "SUCCEEDED"));
let version = 0;
let controller: AbortController | null = null;
let timer: ReturnType<typeof setTimeout> | undefined;
let requestKey = "";
let requestGoal = "";
let sessionKey = "";
let cursor = 0;
watch(() => run.value?.run_id, () => { newGoalOpen.value = false; });
watch(run, value => emit("frozenScope", value ? value.learning_scope ?? null : undefined), { immediate: true });
watch(() => artifact.value?.artifact_id, () => { questionIndex.value = 0; resultsOpen.value = false; questionDrafts.value = {}; feedbackDrafts.value = {}; });
watch(() => ({ run: run.value, artifact: artifact.value, index: questionIndex.value, saved: attempts.value.length }), ({ run, artifact, index, saved }) => {
  emit("position", run ? { goal: run.goal, question: artifact?.questions[index]?.question ?? "", questionIndex: index, totalQuestions: artifact?.questions.length ?? 0, savedQuestions: saved } : null);
}, { immediate: true });

async function chooseQuestion(index: number) {
  if (!artifact.value?.questions[index]) return;
  resultsOpen.value = false;
  questionIndex.value = index;
  await nextTick();
  const question = questionElements.get(index);
  question?.scrollIntoView({ block: "start" });
  question?.querySelector<HTMLTextAreaElement>("textarea")?.focus({ preventScroll: true });
}

async function studyCommand(task: string, command: StudyCommand) {
  const current = version;
  try { return await sendStudyCommand(task, command); }
  catch (failure) {
    if (current === version && task === props.taskId && mayHaveLostCourseAccess(failure)) emit("accessFailure");
    throw failure;
  }
}
const active = computed(() => run.value !== null && ["queued", "running", "awaiting_approval"].includes(run.value.status));
const canStart = computed(() => props.learningScope !== null && enabled.value && ready.value && !active.value && !submitting.value && goal.value.trim().length > 0);
const stateText = computed(() => artifact.value?.kind === "insufficient_evidence" ? "课程证据不足" : ({ awaiting_approval: "等待发布审批", queued: "等待开始", running: "正在学习课程内容", succeeded: "解释与练习已完成", failed: "本次执行未完成", cancelled: "已取消", budget_exceeded: "本次执行已达到时间或调用上限" })[run.value?.status ?? "queued"]);
const toolText: Record<string, string> = { search_course_evidence: "查找课程证据", read_evidence_window: "补读片段上下文", check_python_example: "核算例题", create_practice_set: "生成解释与练习", create_python_practice: "生成代码练习", create_interval_practice: "生成区间练习", create_sequence_practice: "生成排序步骤练习", report_insufficient_evidence: "确认课程证据不足" };

watch(() => [props.taskId, props.status], () => { void load(); }, { immediate: true });
onBeforeUnmount(() => { version++; controller?.abort(); clearTimeout(timer); });

async function openHistory(fresh = false, selectedSession?: string, selectedRun?: string) {
  const goalDraft = goal.value.trim() && goal.value.trim() !== (run.value?.goal ?? "");
  if ((hasDrafts.value || goalDraft) && !window.confirm("切换学习记录会离开本次未保存输入（目标、作答或核对文字）。请先保存，或确认放弃这些修改。")) return;
  await load(fresh, selectedSession, selectedRun);
}

async function changeSession(event: Event) {
  const select = event.target as HTMLSelectElement;
  const selected = select.value;
  select.value = sessionId.value;
  await openHistory(false, selected);
}

async function load(fresh = false, selectedSession?: string, selectedRun?: string) {
  const current = ++version;
  const task = props.taskId;
  controller?.abort(); clearTimeout(timer);
  controller = null; cursor = 0;
  enabled.value = null; ready.value = false; loading.value = true; error.value = "";
  progressSequence++; progressRows.value = null; progressLoading.value = false; progressError.value = "";
  submitting.value = false; revealing.value = false;
  sessionId.value = ""; sourceRevision.value = undefined; run.value = null; artifact.value = null; events.value = []; answers.value = null; attempts.value = [];
  requestKey = ""; requestGoal = ""; sessionKey = randomUuid();
  recentRuns.value = [];
  sessions.value = []; feedbackRuns.value = []; feedbackEnabled.value = false;
  if (selectedSession || fresh) goal.value = "";
  try {
    if (preparing.value) return;
    const config = await studyStatus(task);
    if (current !== version) return;
    enabled.value = config.enabled;
    if (!config.enabled) return;
    const index = await getEvidenceIndexStatus(task);
    if (current !== version) return;
    ready.value = index.status === "READY";
    readinessText.value = index.status === "FAILED" ? "课程资料准备失败，请查看处理进度并重试。" : index.status === "DISABLED" ? "课程检索尚未启用，请联系维护者完成配置。" : "课程资料正在准备，完成后即可开始学习。";
    if (config.enabled && !fresh) {
      const list = await studyCommand(task, { operation: "LIST" });
      if (current !== version) return;
      sessions.value = list.sessions ?? [];
      sessionId.value = selectedSession ?? sessions.value[0]?.session_id ?? "";
      sourceRevision.value = sessions.value.find(session => session.session_id === sessionId.value)?.revision;
      if (sessionId.value) {
        await refresh(current, task, undefined, selectedRun);
        const history = await studyCommand(task, { operation: "RUNS", session_id: sessionId.value });
        if (current !== version) return;
        recentRuns.value = history.runs ?? [];
      }
    }
    if (current === version && active.value) connect(current, task);
  } catch (failure) {
    if (current === version) {
      error.value = toUserFriendlyError(failure, "学习助手暂不可用");
      if (mayHaveLostCourseAccess(failure)) emit("accessFailure");
    }
  }
  finally { if (current === version) loading.value = false; }
}

async function refresh(current: number, task: string, expectedKey?: string, selectedRun?: string) {
  const progressAtRead = progressSequence;
  const id = selectedRun ?? run.value?.run_id;
  const response = await studyCommand(task, { operation: "READ", session_id: sessionId.value, ...(id ? { run_id: id } : {}) });
  if (current !== version || (expectedKey && response.run?.request_key !== expectedKey)) return;
  run.value = response.run ?? null; artifact.value = response.artifact ?? null;
  approvalRequired.value = response.run?.approval_required ?? approvalRequired.value;
  approval.value = response.approval ?? null;
  observeAttempts(response.attempts ?? []);
  feedbackEnabled.value = response.feedback_enabled ?? false;
  // A completion snapshot can predate a save followed by a newer progress read,
  // including its feedback status and persisted check note.
  if (progressAtRead === progressSequence) {
    feedbackRuns.value = response.feedback_runs ?? [];
    if (artifact.value?.questions.length) acceptProgress(response);
  }
  if (!goal.value && run.value) goal.value = run.value.goal;
}

async function start() {
  if (!canStart.value) return;
  if (hasDrafts.value && !window.confirm("开始新的练习会离开本次未保存作答或核对文字。请先保存，或确认放弃这些修改。")) return;
  const current = ++version; const task = props.taskId; const text = goal.value.trim();
  controller?.abort(); clearTimeout(timer); revealing.value = false;
  submitting.value = true; error.value = ""; progressSequence++; progressRows.value = null; progressLoading.value = false; progressError.value = ""; artifact.value = null; answers.value = null; events.value = []; attempts.value = []; cursor = 0;
  const selectedScope = props.learningScope ? JSON.parse(JSON.stringify(props.learningScope)) as LearningScope : undefined;
  const fingerprint=JSON.stringify([text, selectedScope, approvalRequired.value]);
  if (requestGoal !== fingerprint || !requestKey) { requestKey = randomUuid(); requestGoal = fingerprint; }
  try {
    if (!sessionId.value) {
      const response = await studyCommand(task, { operation: "CREATE_SESSION", request_key: sessionKey });
      if (current !== version) return;
      sessionId.value = response.session_id!;
      sourceRevision.value = response.revision;
    }
    const response = await studyCommand(task, { operation: "START", session_id: sessionId.value, request_key: requestKey, goal: text, approval_required: approvalRequired.value, ...(selectedScope ? { learning_scope: selectedScope } : {}) });
    if (current !== version) return;
    run.value = response.run ?? null; artifact.value = response.artifact ?? null;
    approval.value = response.approval ?? null;
  attempts.value = response.attempts ?? [];
    feedbackEnabled.value = response.feedback_enabled ?? false;
    feedbackRuns.value = response.feedback_runs ?? [];
    requestKey = "";
    if (active.value) connect(current, task);
  } catch (failure) {
    if (current === version) {
      error.value = modelError(failure, toUserFriendlyError(failure, "执行未能确认，可重试同一请求。"));
      // A lost START response may already have created a run. Recover it before allowing another start.
      if (sessionId.value) {
        try { run.value = null; await refresh(current, task, requestKey); if (current === version && active.value) connect(current, task); } catch { /* Preserve original error. */ }
      }
    }
  } finally { if (current === version) submitting.value = false; }
}

function connect(current: number, task: string) {
  if (run.value?.status === "awaiting_approval") return;
  controller?.abort();
  const connection = new AbortController(); controller = connection;
  const session = sessionId.value; const id = run.value!.run_id;
  void studyEvents(task, session, id, cursor, connection.signal, event => {
    if (current !== version || connection.signal.aborted) return;
    cursor = Math.max(cursor, event.sequence);
    if (!events.value.some(e => e.sequence === event.sequence)) events.value.push(event);
    if (event.event_type === "run_started" || event.event_type === "run_resumed") run.value!.status = "running";
    if (["run_finished", "approval_waiting"].includes(event.event_type)) void refresh(current, task);
  }).catch(failure => {
    if (current === version && !connection.signal.aborted) error.value = failure instanceof Error ? failure.message : "正在重新连接…";
  }).finally(async () => {
    if (current !== version || connection.signal.aborted) return;
    try { await refresh(current, task); if (current === version) error.value = ""; } catch { /* Retry with cursor below. */ }
    if (current === version && active.value) timer = setTimeout(() => connect(current, task), 1500);
  });
}

async function cancel() {
  if (!run.value || submitting.value) return;
  const current = version; submitting.value = true;
  try {
    const response = await studyCommand(props.taskId, { operation: "CANCEL", session_id: sessionId.value, run_id: run.value.run_id });
    if (current !== version) return;
    run.value = response.run ?? null; controller?.abort();
  } catch (failure) { if (current === version) error.value = toUserFriendlyError(failure, "取消未确认，请重试"); }
  finally { if (current === version) submitting.value = false; }
}

async function reveal() {
  if (!run.value || revealing.value) return;
  const current = version; revealing.value = true;
  try {
    const response = await studyCommand(props.taskId, { operation: "ANSWERS", session_id: sessionId.value, run_id: run.value.run_id });
    if (current === version) answers.value = response.questions ?? [];
  } catch (failure) { if (current === version) error.value = toUserFriendlyError(failure, "答案暂不可用"); }
  finally { if (current === version) revealing.value = false; }
}
</script>

<template>
  <section class="agent-panel workspace-panel" :class="{ 'agent-panel--compact': compact, 'has-practice': Boolean(artifact?.questions.length) }" aria-labelledby="agent-title">
    <header><div class="agent-heading"><h2 id="agent-title">{{ compact && artifact?.questions.length ? artifact.title : '解释与练习' }}</h2><button v-if="sessions.length || recentRuns.length" type="button" @click="showHistory">学习记录</button></div><p v-if="!run">继续已保存的任务，或明确开始一次新练习。单次提问请使用课程问答。</p></header>
    <p v-if="loading" role="status">正在读取学习会话…</p>
    <div v-else-if="preparing" role="status"><p>课程内容尚未处理完成。请先查看处理进度，完成后即可开始学习。</p><el-button @click="$emit('navigate', 'overview')">查看处理进度</el-button></div>
    <div v-else-if="enabled === false" role="status">
      <p>学习助手尚未启用。你可以先阅读课程内容，或联系维护者启用。</p>
      <el-button @click="$emit('navigate', 'content')">阅读课程内容</el-button>
      <el-button @click="load()">重新检查</el-button>
    </div>
    <div v-else-if="enabled">
      <div v-if="!ready" role="status"><p>{{ readinessText }}</p><el-button text @click="$emit('navigate', 'overview')">查看处理进度</el-button><el-button text @click="load()">刷新状态</el-button></div>
      <p v-if="run?.model_mode === 'mock' && !artifact" class="mode-label">演示模式：固定测试模型，用于验证流程。</p>
      <div v-if="run" class="run-progress" :class="{ 'run-progress--ready': artifact }" aria-live="polite">
        <strong>{{ compact && artifact?.questions.length && run.status === 'succeeded' ? '练习已生成' : stateText }}</strong><small v-if="artifact && run.model_mode === 'mock'">Mock 流程测试</small>
        <p v-if="!artifact" class="run-goal">{{ run.goal }}</p>
        <el-button v-if="active" :disabled="submitting" @click="cancel">取消本次执行</el-button>
        <details v-if="events.length"><summary>执行进度详情</summary><ol>
          <li v-for="event in events.filter(e => ['tool_started', 'run_resumed', 'quality_checked', 'protocol_retry_scheduled'].includes(e.event_type))" :key="event.sequence">
            {{ event.event_type === 'quality_checked' ? (event.payload.accepted ? '模型复核已完成' : '草稿需要修订') : event.event_type === 'protocol_retry_scheduled' ? '模型返回格式有误，正在尝试纠正（最多一次）' : event.event_type === 'run_resumed' ? '已从保存的进度继续' : toolText[event.payload.tool ?? ''] ?? '处理学习任务' }}
          </li>
        </ol></details>
        <p v-if="run.error_code === 'COURSE_UNAVAILABLE_OR_CHANGED'">课程已更新或不可用，请检查课程后开启新会话。</p>
        <p v-else-if="run.error_code === 'QUALITY_REPAIR_EXHAUSTED'">草稿修订后仍未通过复核，本次未生成练习。可以缩小学习目标后重试。</p>
        <p v-else-if="run.error_code === 'INVALID_TOOL_ARGUMENTS'">模型返回的工具或复核参数不符合要求，本次未保存产物。可检查模型兼容性后重试。</p>
        <p v-else-if="run.error_code?.startsWith('MODEL_')">{{ modelError(new Error(run.error_code), '模型调用未完成，请检查模型管理中的配置后重试。') }}</p>
        <p v-else-if="run.status === 'failed'">本次没有完成学习产物，可开启新会话重试。</p>
      </div>
      <StudyApprovalPanel v-if="run?.status === 'awaiting_approval' && approval" :task-id="taskId" :session-id="sessionId" :run-id="run.run_id" :approval="approval" @decided="async () => { await refresh(version, taskId); if (active) connect(version, taskId); }" />
      <article v-if="artifact" class="study-artifact">
        <h3 v-if="!compact || !artifact.questions.length">{{ artifact.title }}</h3><p v-if="artifact.human_edited">说明经课程所有者人工修改。</p>
        <details class="artifact-explanation" :open="!artifact.questions.length"><summary>阅读课程解释</summary><p class="explanation">{{ artifact.explanation }}</p>
        <details v-if="artifact.citations.length"><summary>查看课程证据</summary>
          <div v-for="citation in artifact.citations" :key="citation.evidence_id" class="citation">
            <el-button text @click="$emit('seek', citation.start_ms, { evidenceId: citation.evidence_id, revision: sourceRevision })">{{ formatMillisRange(citation.start_ms, citation.end_ms) }} · 跳到视频</el-button>
            <code class="evidence-id">{{ citation.evidence_id }}</code><p>{{ citation.text }}</p>
          </div>
        </details></details>
        <template v-if="artifact.questions.length">
          <section v-if="run" class="practice-continuation" aria-label="继续本次练习" :aria-busy="progressLoading">
            <div><strong>继续本次练习</strong><p v-if="progressLoading" role="status">正在核对已保存进度…</p><template v-else-if="progressRows"><p v-if="continuation">{{ continuation.reason }}</p><p v-else>本次作答均已保存并有核对记录，可回看练习结果。</p></template><p class="continuation-boundary">依据已保存记录提示，不代表答案正确。未保存文字仍保留在本页。</p><p v-if="progressError" role="status">{{ progressError }}</p></div>
            <div class="continuation-actions"><el-button v-if="continuation" class="continue-practice" type="primary" :disabled="progressLoading" @click="continuePractice">{{ continuation.label }}</el-button><el-button v-else-if="progressRows && !progressLoading" @click="toggleResults">回看练习结果</el-button><button class="refresh-practice-progress" type="button" :disabled="progressLoading" @click="refreshProgress">刷新学习进度</button></div>
          </section>
          <div class="practice-toolbar"><el-button @click="toggleResults">{{ resultsOpen ? '返回当前题' : '练习结果' }}</el-button><p class="practice-guidance" title="仅统计已保存的作答记录，不代表掌握程度">已保存 {{ attempts.length }}/{{ artifact.questions.length }} 题</p>
          <nav class="question-nav" aria-label="练习题目">
            <button v-for="(_question, index) in artifact.questions" :key="index" type="button" :aria-current="questionIndex === index ? 'step' : undefined" @click="chooseQuestion(index)">第 {{ index + 1 }} 题<span v-if="questionDrafts[index]"> · 有未保存修改</span><span v-else-if="attempts.find(a => a.question_index === index)"> · 已保存</span></button>
          </nav></div>
        </template>
        <div v-if="resultsOpen && run && artifact" ref="resultsElement" tabindex="-1"><PracticeResultsPanel :task-id="taskId" :session-id="sessionId" :run-id="run.run_id" :artifact="artifact" @open="openResult" @observed-attempts="observeAttempts" @access-failure="$emit('accessFailure')" @seek="seekResult" /></div>
        <div v-for="(question, index) in artifact.questions" v-show="!resultsOpen && questionIndex === index" :key="index" :ref="el => { if (el) questionElements.set(index, el as HTMLElement); else questionElements.delete(index); }" class="practice-question" :class="{ 'is-current': questionIndex === index }">
          <p class="question-text"><strong>{{ index + 1 }}.</strong> {{ question.question }}</p>
          <PracticeAnswerForm :ref="el => { if (el) answerForms.set(index, el as unknown as { showHistory: () => Promise<void> }); else answerForms.delete(index); }" v-if="run" :key="`${artifact.artifact_id}:${index}`" :task-id="taskId" :session-id="sessionId" :run-id="run.run_id" :artifact-id="artifact.artifact_id" :question-index="index" :attempt="attempts.find(a => a.question_index === index)" @draft-change="questionDrafts[index] = $event" @access-failure="$emit('accessFailure')" @saved="savedAttempt" />
          <PracticeFeedbackPanel :ref="el => { if (el) feedbackPanels.set(index, el as unknown as { showFeedback: (row: StudyFeedbackRun) => Promise<void> }); else feedbackPanels.delete(index); }" v-if="run && (feedbackEnabled || feedbackRuns.some(f => f.question_index === index))" :key="`feedback:${artifact.artifact_id}:${index}`" :task-id="taskId" :session-id="sessionId" :run-id="run.run_id" :artifact-id="artifact.artifact_id" :question-index="index" :source-revision="sourceRevision" :enabled="feedbackEnabled" :answer-dirty="questionDrafts[index]" @draft-change="feedbackDrafts[index] = $event" :approval-required="approvalRequired" :attempt="attempts.find(a => a.question_index === index)" :initial="feedbackRuns.find(f => f.question_index === index)" :history="feedbackRuns.filter(f => f.question_index === index)" @progress-change="refreshProgress" @revise="chooseQuestion(index)" @access-failure="$emit('accessFailure')" @seek="(milliseconds, context) => $emit('seek', milliseconds, context)" />
          <p v-else-if="!feedbackEnabled">证据反馈尚未启用，已保存作答和修改记录仍可查看。</p>
          <div v-if="answers?.[index]" class="answer"><p>参考答案：{{ answers[index]?.answer }}</p><p>自查要点：{{ answers[index]?.rubric }}</p></div>
        </div>
        <div v-if="artifact.questions.length > 1" class="actions">
          <el-button :disabled="questionIndex === 0" @click="chooseQuestion(questionIndex - 1)">上一题</el-button>
          <el-button :disabled="questionIndex === artifact.questions.length - 1" @click="chooseQuestion(questionIndex + 1)">下一题</el-button>
          <el-button v-if="!resultsOpen && questionIndex === artifact.questions.length - 1" @click="toggleResults">查看练习结果</el-button>
        </div>
        <el-button v-if="artifact.questions.length && !answers" :loading="revealing" @click="reveal">查看参考答案与自查要点</el-button>
      </article>
      <details class="new-study-goal" :open="!run || newGoalOpen" @toggle="newGoalOpen = ($event.target as HTMLDetailsElement).open">
        <summary>{{ run ? '开始新的解释与练习' : '开始一次解释与练习' }}</summary>
        <p>填写目标并点击“解释并出题”才会开始新的学习执行。未保存输入只保留在本页。</p>
      <div v-if="recruiterDemoEnabled && taskId === recruiterDemo.taskId" class="sample-goals"><p>Sample Course · 无需上传。先选一个目标，再执行；完成后可作答、查看反馈和 Trace。</p><el-button v-for="sample in demoGoals" :key="sample.label" :disabled="Boolean(active || submitting)" @click="goal = sample.goal">{{ sample.label }}</el-button><RouterLink to="/demo">演示说明与课程来源</RouterLink></div>
      <el-input v-model="goal" type="textarea" :rows="3" maxlength="1000" placeholder="例如：解释算法为什么需要停止条件，并结合课程给我两道题。" aria-label="学习目标" />
      <label><input v-model="approvalRequired" type="checkbox" :disabled="Boolean(active)" />发布前由我审批</label>

      <div class="actions">
        <el-button type="primary" :disabled="!canStart" :loading="submitting" @click="start">解释并出题</el-button>
        <el-button v-if="!active" :disabled="submitting" @click="openHistory(true)">新会话</el-button>
      </div>
      </details>
      <details v-if="sessions.length || recentRuns.length" ref="historyElement" class="learning-history">
        <summary>最近学习记录</summary>
        <label v-if="sessions.length > 1">学习会话
          <select :value="sessionId" @change="changeSession">
            <option v-for="(session, index) in sessions" :key="session.session_id" :value="session.session_id">{{ session.created_at ? new Date(session.created_at).toLocaleString() : `会话 ${index + 1}` }}</option>
          </select>
        </label>
        <p>显示最近 20 次执行，选择后可继续查看练习和已保存作答。</p>
        <ol><li v-for="previous in recentRuns" :key="previous.run_id"><el-button text @click="openHistory(false, sessionId, previous.run_id)">{{ previous.goal }}</el-button></li></ol>
      </details>
      <details class="execution-details" :open="!compact"><summary>执行与模型详情</summary>
      <RunTracePanel v-if="run" :task-id="taskId" :session-id="sessionId" :run="run" :artifact="artifact" />
      <details class="agent-settings"><summary>模型设置与执行说明</summary><p>Trace 和模型记录展示已保存的执行事实；打开不会创建学习任务。</p><RouterLink to="/settings/models">管理模型</RouterLink></details>
      </details>
    </div>
    <div v-if="error" role="alert"><el-alert :title="error" type="error" :closable="false" /><el-button v-if="!run && !loading" @click="load()">重新连接</el-button><RouterLink to="/settings/models">检查模型配置</RouterLink></div>
  </section>
</template>

<style scoped>
.run-progress--ready { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 8px 10px !important; font-size: 13px; }
.run-progress--ready small { color: var(--color-ink-soft); font-size: 12px; }
.mode-label { font-size: 12px; margin: 8px 0; line-height: 1.5; }
.practice-guidance { font-size: 13px; }
.agent-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.agent-heading button { font: inherit; background: transparent; color: var(--color-brand); border: 0; padding: 8px; cursor: pointer; }
.new-study-goal, .learning-history { margin-top: 18px; padding: 14px; border: 1px solid var(--color-border); border-radius: var(--radius-md); }
.new-study-goal > summary, .learning-history > summary { font-weight: 650; color: var(--color-brand); }
.new-study-goal > p { line-height: 1.6; color: var(--color-ink-soft); }
.artifact-explanation > summary { color: var(--color-brand); }

.sample-goals { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; align-items: center; }.sample-goals p { width: 100%; }.sample-goals .el-button + .el-button { margin-left: 0; }.evidence-id { display: block; overflow-wrap: anywhere; font-size: 12px; }
.agent-panel { display: grid; gap: 12px; padding: 24px; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); }
header h2, header p { margin: 0; } header { display: grid; gap: 8px; } header p, .run-goal, .mode-label { color: var(--color-ink-soft); }
.actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }.run-progress { margin-top: 12px; padding: 12px; background: var(--color-canvas); border-radius: var(--radius-md); }.run-progress ol { line-height: 1.9; }
.study-artifact { display: grid; gap: 16px; margin-top: 14px; border-top: 1px solid var(--color-border); padding-top: 18px; }.study-artifact h3,.study-artifact p { margin: 0; }.explanation { white-space: pre-wrap; line-height: 1.8; }.practice-question { display: grid; gap: 10px; padding: 14px 0; }.citation { margin-top: 14px; line-height: 1.7; }.answer { display: grid; gap: 8px; padding: 12px; background: var(--color-canvas); line-height: 1.7; }summary { cursor: pointer; }
@media (max-width: 520px) { .agent-panel { padding: 16px; } }
.question-text, .answer p { white-space: pre-wrap; overflow-wrap: anywhere; }
.learning-history .el-button { max-width: 100%; height: auto; min-height: 32px; white-space: normal; text-align: left; line-height: 1.6; }
.learning-history .el-button :deep(span) { min-width: 0; overflow-wrap: anywhere; }
.question-nav { display: flex; flex-wrap: wrap; gap: 8px; }.question-nav button { font: inherit; padding: 8px 12px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); color: var(--color-brand); cursor: pointer; }
.question-nav [aria-current] { background: var(--color-brand-soft); border-color: var(--color-brand); }.practice-guidance { color: var(--color-ink-soft); line-height: 1.6; }.practice-question { scroll-margin-top: calc(var(--header-height) + 92px); }
.agent-settings { margin-top: 16px; color: var(--color-ink-soft); }


.agent-panel--compact { gap: 10px; }
.agent-panel--compact header h2 { font-size: 18px; line-height: 1.5; }
.agent-panel--compact .agent-heading { align-items: flex-start; }
.agent-panel--compact .agent-heading button { flex-shrink: 0; font-size: 12px; }
.agent-panel--compact .run-progress--ready { margin-top: 2px; padding: 0 !important; border-radius: 0; background: transparent; color: var(--color-ink-soft); }
.agent-panel--compact .run-progress--ready strong { font-weight: 500; font-size: 12px; }
.agent-panel--compact .study-artifact { margin-top: 10px; padding-top: 12px; gap: 10px; }
.practice-continuation { display: grid; gap: 10px; padding: 12px 14px; border: 1px solid var(--color-border); border-left: 3px solid var(--color-brand); border-radius: var(--radius-sm); background: var(--color-canvas); }
.practice-continuation strong { font-size: 14px; }.practice-continuation p { font-size: 13px; line-height: 1.65; margin-top: 5px; }.practice-continuation .continuation-boundary { color: var(--color-ink-soft); font-size: 12px; }.continuation-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }.refresh-practice-progress { border: 0; background: transparent; color: var(--color-brand); font: inherit; font-size: 12px; padding: 6px 0; cursor: pointer; }.refresh-practice-progress:disabled { cursor: wait; opacity: .65; }
.practice-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
.practice-toolbar .practice-guidance { order: 2; font-size: 12px; }
.agent-panel--compact .question-nav button { font-size: 13px; padding: 7px 12px; }
.agent-panel--compact .question-nav { gap: 6px; }
.agent-panel--compact .practice-question { padding-top: 6px; }
.agent-panel--compact .artifact-explanation > summary { font-size: 13px; }
.execution-details { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--color-border); font-size: 13px; color: var(--color-ink-soft); }
.execution-details > summary { padding-block: 4px; }
@media (max-width: 520px) {
  .agent-panel--compact header h2 { font-size: 16px; }
  .agent-panel--compact .study-artifact { margin-top: 6px; padding-top: 10px; }
  .agent-panel--compact .question-nav button { min-height: 38px; }
}
</style>
