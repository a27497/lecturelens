<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { getEvidenceIndexStatus } from "../../api/qa";
import { studyCommand, studyEvents, studyStatus } from "../../api/study";
import type { StudyArtifact, StudyEvent, StudyRun, PracticeQuestion, StudyAttempt, StudyResponse, StudyFeedbackRun } from "../../api/study";
import PracticeAnswerForm from "./PracticeAnswerForm.vue";
import PracticeFeedbackPanel from "./PracticeFeedbackPanel.vue";
import { toUserFriendlyError } from "../../utils/errorMessage";
import { modelError } from "../../api/models";
import { formatMillisRange } from "../../utils/time";

const props = defineProps<{ taskId: string; status?: string }>();
defineEmits<{ seek: [startTimeMillis: number]; navigate: [workspace: "overview" | "content"] }>();
const enabled = ref<boolean | null>(null);
const readinessText = ref("课程资料正在准备，完成后即可开始学习。");
const ready = ref(false);
const loading = ref(true);
const submitting = ref(false);
const error = ref("");
const goal = ref("");
const sessionId = ref("");
const run = ref<StudyRun | null>(null);
const artifact = ref<StudyArtifact | null>(null);
const events = ref<StudyEvent[]>([]);
const answers = ref<PracticeQuestion[] | null>(null);
const revealing = ref(false);
const attempts = ref<StudyAttempt[]>([]);
const sessions = ref<NonNullable<StudyResponse['sessions']>>([]);
const recentRuns = ref<NonNullable<StudyResponse['runs']>>([]);
const feedbackEnabled = ref(false);
const feedbackRuns = ref<StudyFeedbackRun[]>([]);
const preparing = computed(() => Boolean(props.status && props.status !== "SUCCEEDED"));
let version = 0;
let controller: AbortController | null = null;
let timer: ReturnType<typeof setTimeout> | undefined;
let requestKey = "";
let requestGoal = "";
let sessionKey = "";
let cursor = 0;
const active = computed(() => run.value !== null && ["queued", "running"].includes(run.value.status));
const canStart = computed(() => enabled.value && ready.value && !active.value && !submitting.value && goal.value.trim().length > 0);
const stateText = computed(() => artifact.value?.kind === "insufficient_evidence" ? "课程证据不足" : ({ queued: "等待开始", running: "正在学习课程内容", succeeded: "解释与练习已完成", failed: "本次执行未完成", cancelled: "已取消", budget_exceeded: "本次执行已达到时间或调用上限" })[run.value?.status ?? "queued"]);
const toolText: Record<string, string> = { search_course_evidence: "查找课程证据", read_evidence_window: "补读片段上下文", check_python_example: "核算例题", create_practice_set: "生成解释与练习", create_python_practice: "生成代码练习", create_interval_practice: "生成区间练习", create_sequence_practice: "生成排序步骤练习", report_insufficient_evidence: "确认课程证据不足" };

watch(() => [props.taskId, props.status], () => { void load(); }, { immediate: true });
onBeforeUnmount(() => { version++; controller?.abort(); clearTimeout(timer); });

async function load(fresh = false, selectedSession?: string, selectedRun?: string) {
  const current = ++version;
  const task = props.taskId;
  controller?.abort(); clearTimeout(timer);
  controller = null; cursor = 0;
  enabled.value = null; ready.value = false; loading.value = true; error.value = "";
  submitting.value = false; revealing.value = false;
  sessionId.value = ""; run.value = null; artifact.value = null; events.value = []; answers.value = null; attempts.value = [];
  requestKey = ""; requestGoal = ""; sessionKey = crypto.randomUUID();
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
      if (sessionId.value) {
        await refresh(current, task, undefined, selectedRun);
        const history = await studyCommand(task, { operation: "RUNS", session_id: sessionId.value });
        if (current !== version) return;
        recentRuns.value = history.runs ?? [];
      }
    }
    if (current === version && active.value) connect(current, task);
  } catch (failure) { if (current === version) error.value = toUserFriendlyError(failure, "学习助手暂不可用"); }
  finally { if (current === version) loading.value = false; }
}

async function refresh(current: number, task: string, expectedKey?: string, selectedRun?: string) {
  const id = selectedRun ?? run.value?.run_id;
  const response = await studyCommand(task, { operation: "READ", session_id: sessionId.value, ...(id ? { run_id: id } : {}) });
  if (current !== version || (expectedKey && response.run?.request_key !== expectedKey)) return;
  run.value = response.run ?? null; artifact.value = response.artifact ?? null;
  attempts.value = response.attempts ?? [];
  feedbackEnabled.value = response.feedback_enabled ?? false;
  feedbackRuns.value = response.feedback_runs ?? [];
  if (!goal.value && run.value) goal.value = run.value.goal;
}

async function start() {
  if (!canStart.value) return;
  const current = ++version; const task = props.taskId; const text = goal.value.trim();
  controller?.abort(); clearTimeout(timer); revealing.value = false;
  submitting.value = true; error.value = ""; artifact.value = null; answers.value = null; events.value = []; attempts.value = []; cursor = 0;
  if (requestGoal !== text || !requestKey) { requestKey = crypto.randomUUID(); requestGoal = text; }
  try {
    if (!sessionId.value) {
      const response = await studyCommand(task, { operation: "CREATE_SESSION", request_key: sessionKey });
      if (current !== version) return;
      sessionId.value = response.session_id!;
    }
    const response = await studyCommand(task, { operation: "START", session_id: sessionId.value, request_key: requestKey, goal: text });
    if (current !== version) return;
    run.value = response.run ?? null; artifact.value = response.artifact ?? null;
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
  controller?.abort();
  const connection = new AbortController(); controller = connection;
  const session = sessionId.value; const id = run.value!.run_id;
  void studyEvents(task, session, id, cursor, connection.signal, event => {
    if (current !== version || connection.signal.aborted) return;
    cursor = Math.max(cursor, event.sequence);
    if (!events.value.some(e => e.sequence === event.sequence)) events.value.push(event);
    if (event.event_type === "run_started" || event.event_type === "run_resumed") run.value!.status = "running";
    if (event.event_type === "run_finished") void refresh(current, task);
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
  <section class="agent-panel workspace-panel" aria-labelledby="agent-title">
    <header><h2 id="agent-title">学习助手</h2><p>提出一个学习目标，结合课程证据获得解释与两道自测题。<RouterLink to="/settings/models">管理模型</RouterLink></p></header>
    <p v-if="loading" role="status">正在读取学习会话…</p>
    <div v-else-if="preparing" role="status"><p>课程内容尚未处理完成。请先查看处理进度，完成后即可开始学习。</p><el-button @click="$emit('navigate', 'overview')">查看处理进度</el-button></div>
    <div v-else-if="enabled === false" role="status">
      <p>学习助手尚未启用。你可以先阅读课程内容，或联系维护者启用。</p>
      <el-button @click="$emit('navigate', 'content')">阅读课程内容</el-button>
      <el-button @click="load()">重新检查</el-button>
    </div>
    <div v-else-if="enabled">
      <div v-if="!ready" role="status"><p>{{ readinessText }}</p><el-button text @click="$emit('navigate', 'overview')">查看处理进度</el-button><el-button text @click="load()">刷新状态</el-button></div>
      <p v-if="run?.model_mode === 'mock'" class="mode-label">演示模式：固定测试模型，用于验证流程。</p>
      <el-input v-model="goal" type="textarea" :rows="3" maxlength="1000" placeholder="例如：解释算法为什么需要停止条件，并结合课程给我两道题。" aria-label="学习目标" />
      <div class="actions">
        <el-button type="primary" :disabled="!canStart" :loading="submitting" @click="start">解释并出题</el-button>
        <el-button v-if="active" :disabled="submitting" @click="cancel">取消本次执行</el-button>
        <el-button v-else :disabled="submitting" @click="load(true)">新会话</el-button>
      </div>
      <details v-if="sessions.length || recentRuns.length" class="learning-history">
        <summary>最近学习记录</summary>
        <label v-if="sessions.length > 1">学习会话
          <select :value="sessionId" @change="load(false, ($event.target as HTMLSelectElement).value)">
            <option v-for="(session, index) in sessions" :key="session.session_id" :value="session.session_id">{{ session.created_at ? new Date(session.created_at).toLocaleString() : `会话 ${index + 1}` }}</option>
          </select>
        </label>
        <p>显示最近 20 次执行，选择后可继续查看练习和已保存作答。</p>
        <ol><li v-for="previous in recentRuns" :key="previous.run_id"><el-button text @click="load(false, sessionId, previous.run_id)">{{ previous.goal }}</el-button></li></ol>
      </details>
      <div v-if="run" class="run-progress" aria-live="polite">
        <strong>{{ stateText }}</strong>
        <p class="run-goal">{{ run.goal }}</p>
        <p v-if="run.model_selection?.decision">决策：{{ run.model_selection.decision.name }} · {{ run.model_selection.decision.model }}<br />复核：{{ run.model_selection.review?.name }} · {{ run.model_selection.review?.model }}</p>
        <ol v-if="events.length">
          <li v-for="event in events.filter(e => ['tool_started', 'run_resumed', 'quality_checked', 'protocol_retry_scheduled'].includes(e.event_type))" :key="event.sequence">
            {{ event.event_type === 'quality_checked' ? (event.payload.accepted ? '模型复核已完成' : '草稿需要修订') : event.event_type === 'protocol_retry_scheduled' ? '模型返回格式有误，正在尝试纠正（最多一次）' : event.event_type === 'run_resumed' ? '已从保存的进度继续' : toolText[event.payload.tool ?? ''] ?? '处理学习任务' }}
          </li>
        </ol>
        <p v-if="run.error_code === 'COURSE_UNAVAILABLE_OR_CHANGED'">课程已更新或不可用，请检查课程后开启新会话。</p>
        <p v-else-if="run.error_code === 'QUALITY_REPAIR_EXHAUSTED'">草稿修订后仍未通过复核，本次未生成练习。可以缩小学习目标后重试。</p>
        <p v-else-if="run.error_code === 'INVALID_TOOL_ARGUMENTS'">模型返回的工具或复核参数不符合要求，本次未保存产物。可检查模型兼容性后重试。</p>
        <p v-else-if="run.error_code?.startsWith('MODEL_')">{{ modelError(new Error(run.error_code), '模型调用未完成，请检查模型管理中的配置后重试。') }}</p>
        <p v-else-if="run.status === 'failed'">本次没有完成学习产物，可开启新会话重试。</p>
      </div>
      <article v-if="artifact" class="study-artifact">
        <h3>{{ artifact.title }}</h3><p class="explanation">{{ artifact.explanation }}</p>
        <details v-if="artifact.citations.length"><summary>查看课程证据</summary>
          <div v-for="citation in artifact.citations" :key="citation.evidence_id" class="citation">
            <el-button text @click="$emit('seek', citation.start_ms)">{{ formatMillisRange(citation.start_ms, citation.end_ms) }} · 跳到视频</el-button>
            <p>{{ citation.text }}</p>
          </div>
        </details>
        <h3 v-if="artifact.questions.length">两道自测题</h3>
        <div v-for="(question, index) in artifact.questions" :key="index" class="practice-question">
          <p class="question-text"><strong>{{ index + 1 }}.</strong> {{ question.question }}</p>
          <PracticeAnswerForm v-if="run" :key="`${artifact.artifact_id}:${index}`" :task-id="taskId" :session-id="sessionId" :run-id="run.run_id" :artifact-id="artifact.artifact_id" :question-index="index" :attempt="attempts.find(a => a.question_index === index)" @saved="value => { attempts = [...attempts.filter(a => a.question_index !== index), value]; }" />
          <PracticeFeedbackPanel v-if="run && (feedbackEnabled || feedbackRuns.some(f => f.question_index === index))" :key="`feedback:${artifact.artifact_id}:${index}`" :task-id="taskId" :session-id="sessionId" :run-id="run.run_id" :artifact-id="artifact.artifact_id" :question-index="index" :enabled="feedbackEnabled" :attempt="attempts.find(a => a.question_index === index)" :initial="feedbackRuns.find(f => f.question_index === index)" :history="feedbackRuns.filter(f => f.question_index === index)" @seek="$emit('seek', $event)" />
          <div v-if="answers?.[index]" class="answer"><p>参考答案：{{ answers[index]?.answer }}</p><p>自查要点：{{ answers[index]?.rubric }}</p></div>
        </div>
        <el-button v-if="artifact.questions.length && !answers" :loading="revealing" @click="reveal">查看参考答案与自查要点</el-button>
      </article>
    </div>
    <div v-if="error" role="alert"><el-alert :title="error" type="error" :closable="false" /><el-button v-if="!run && !loading" @click="load()">重新连接</el-button><RouterLink to="/settings/models">检查模型配置</RouterLink></div>
  </section>
</template>

<style scoped>
.agent-panel { display: grid; gap: 20px; padding: 24px; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); }
header h2, header p { margin: 0; } header { display: grid; gap: 8px; } header p, .run-goal, .mode-label { color: var(--color-ink-soft); }
.actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }.run-progress { margin-top: 20px; padding: 16px; background: var(--color-canvas); border-radius: var(--radius-md); }.run-progress ol { line-height: 1.9; }
.study-artifact { display: grid; gap: 16px; margin-top: 24px; border-top: 1px solid var(--color-border); padding-top: 18px; }.study-artifact h3,.study-artifact p { margin: 0; }.explanation { white-space: pre-wrap; line-height: 1.8; }.practice-question { display: grid; gap: 10px; padding: 14px 0; }.citation { margin-top: 14px; line-height: 1.7; }.answer { display: grid; gap: 8px; padding: 12px; background: var(--color-canvas); line-height: 1.7; }summary { cursor: pointer; }
@media (max-width: 520px) { .agent-panel { padding: 16px; } }
.question-text, .answer p { white-space: pre-wrap; overflow-wrap: anywhere; }
.learning-history .el-button { max-width: 100%; height: auto; min-height: 32px; white-space: normal; text-align: left; line-height: 1.6; }
.learning-history .el-button :deep(span) { min-width: 0; overflow-wrap: anywhere; }
</style>
