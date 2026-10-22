<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  downloadTaskEmbeddedSubtitle,
  probeTaskEmbeddedSubtitles,
  toReadableEmbeddedSubtitleError,
} from "../api/embeddedSubtitles";
import { requestTaskPlaybackToken, toReadablePlaybackError } from "../api/media";
import CourseScopePicker from "../components/task-detail/CourseScopePicker.vue";
import type { LearningScope } from "../api/learningScope";
import { fetchTaskResult } from "../api/result";
import { getEvidenceIndexStatus } from "../api/qa";
import { createEvidenceSeekGuard } from "../components/task-detail/evidenceSeekGuard";
import type { EvidenceSeekContext } from "../components/task-detail/evidenceSeekGuard";
import { fetchPublicRuntimeConfiguration } from "../api/runtimeConfiguration";
import { cancelTask, fetchTaskDetail, retryTask, toReadableTaskError } from "../api/task";
import CourseContentPanel from "../components/task-detail/CourseContentPanel.vue";
import CourseFilesPanel from "../components/task-detail/CourseFilesPanel.vue";
import CourseOverviewPanel from "../components/task-detail/CourseOverviewPanel.vue";
import CourseAgentPanel from "../components/task-detail/CourseAgentPanel.vue";
import CourseModelUsagePanel from "../components/task-detail/CourseModelUsagePanel.vue";
import CourseQaPanel from "../components/task-detail/CourseQaPanel.vue";
import CourseStudyPanel from "../components/task-detail/CourseStudyPanel.vue";
import CourseTechnicalPanel from "../components/task-detail/CourseTechnicalPanel.vue";
import CourseVideoAside from "../components/task-detail/CourseVideoAside.vue";
import CourseWorkspaceHeader from "../components/task-detail/CourseWorkspaceHeader.vue";
import CourseWorkspaceNav from "../components/task-detail/CourseWorkspaceNav.vue";
import { readCourseLocation, validPosition } from "../components/task-detail/courseLocation";
import type { ContentView, SeekRequest } from "../components/task-detail/courseLocation";
import type { CourseWorkspace } from "../components/task-detail/workspace";
import { useTaskEventsStore } from "../stores/taskEvents";
import { useTaskResultStore } from "../stores/taskResult";
import type { TaskDetailResponse } from "../types/task";
import { isRetryableTaskStatus, shouldReloadTerminalTaskDetail } from "../utils/taskStatus";
import { normalizeSubtitleLanguage } from "../utils/subtitleLanguage";

type SubtitleStatus = "none" | "loading" | "loaded" | "not_found" | "unsupported" | "failed";

const route = useRoute();
const router = useRouter();
const taskEventsStore = useTaskEventsStore();
const taskResultStore = useTaskResultStore();

const activeWorkspace = ref<CourseWorkspace>("agent");
const readingView = ref<ContentView>();
const positionMs = ref(0);
const seekRequest = ref<SeekRequest>();
const locateSequence = ref(0);
const reviewingEvidence = ref(false);
const evidenceRef = ref<HTMLElement | null>(null);
let seekSequence = 0;
let returnFocus: HTMLElement | null = null;
let returnScroll = 0;
let locationTimer: ReturnType<typeof setTimeout> | undefined;
const pendingLocations = new Set<string>();
const evidenceNavigationError = ref("");
const learningScope = ref<LearningScope | null>(null);
const agentScope = ref<LearningScope | null | undefined>();
const qaScope = ref<LearningScope | null | undefined>();
const scopeRefresh = ref(0);
const evidenceSeekGuard = createEvidenceSeekGuard(
  async id => (await getEvidenceIndexStatus(id)).revision,
  message => { evidenceNavigationError.value = message; },
  async id => {
    const source = await fetchTaskResult(id);
    if (!source || source.taskId !== id) throw new Error("Course source mismatch");
    return () => taskResultStore.acceptVerified(id, source);
  },
);
const taskDetail = ref<TaskDetailResponse | null>(null);
const taskDetailRequestVersion = ref(0);
const cancelLoading = ref(false);
const retryLoading = ref(false);
const playbackUrl = ref("");
const playbackExpiresAt = ref("");
const playbackLoading = ref(false);
const playbackError = ref("");
const playbackRequestVersion = ref(0);
const subtitleTrackUrl = ref("");
const subtitleText = ref("");
const subtitleLanguage = ref("und");
const subtitleStatus = ref<SubtitleStatus>("none");
const subtitleMessage = ref("");
const subtitleRequestVersion = ref(0);
const commandVersion = ref(0);
const completedResultReloadTaskId = ref("");
const terminalDetailReloadTaskId = ref("");

const taskId = computed(() => {
  const value = route.params.taskId;
  return Array.isArray(value) ? value[0] || "" : value || "";
});
const task = computed(() => taskEventsStore.task);
const result = computed(() => taskResultStore.result);
const hasTaskId = computed(() => taskId.value.trim().length > 0);
const canCancelTask = computed(() => ["CREATED", "QUEUED", "RUNNING", "RETRYING"].includes(task.value?.status || ""));
const canRetryTask = computed(() => isRetryableTaskStatus(task.value?.status));
const isDemoMode = ref(false);

onMounted(() => {
  void loadPublicRuntimeConfiguration();
});

watch(taskId, (nextTaskId) => {
  learningScope.value=null; agentScope.value=undefined; qaScope.value=undefined;
  commandVersion.value += 1;
  cancelLoading.value = false;
  retryLoading.value = false;
  taskEventsStore.connect(nextTaskId);
  void loadTaskDetail(nextTaskId);
  void taskResultStore.load(nextTaskId);
  void refreshTaskPlayback(nextTaskId);
  void refreshTaskEmbeddedSubtitles(nextTaskId);
  clearTimeout(locationTimer);
  pendingLocations.clear();
  reviewingEvidence.value = false;
  returnFocus = null;
  applyLocation();
  completedResultReloadTaskId.value = "";
  terminalDetailReloadTaskId.value = "";
}, { immediate: true });

watch(() => route.query, () => {
  const signature = locationSignature(route.query);
  if (pendingLocations.delete(signature)) return;
  clearTimeout(locationTimer);
  applyLocation();
});

watch(() => task.value?.status, (status) => {
  const currentTaskId = taskId.value.trim();
  if (!currentTaskId) return;
  if (shouldReloadTerminalTaskDetail(status, currentTaskId, terminalDetailReloadTaskId.value)) {
    evidenceSeekGuard.cancel();
    reviewingEvidence.value = false;
    terminalDetailReloadTaskId.value = currentTaskId;
    void loadTaskDetail(currentTaskId);
  }
  if (status === "SUCCEEDED" && completedResultReloadTaskId.value !== currentTaskId) {
    completedResultReloadTaskId.value = currentTaskId;
    void taskResultStore.load(currentTaskId);
  }
});

onBeforeUnmount(() => {
  evidenceSeekGuard.cancel();
  clearTimeout(locationTimer);
  taskEventsStore.disconnect();
  taskResultStore.clear();
  clearTaskDetail();
  clearTaskPlayback();
  clearTaskEmbeddedSubtitles();
});

function locationSignature(query: typeof route.query) {
  return JSON.stringify([taskId.value, query.view, query.text, query.at]);
}
function applyLocation() {
  evidenceSeekGuard.cancel();
  evidenceNavigationError.value = "";
  clearTimeout(locationTimer);
  locationTimer = undefined;
  const location = readCourseLocation(route.query);
  activeWorkspace.value = location.workspace;
  readingView.value = location.textView;
  positionMs.value = location.milliseconds;
  seekRequest.value = { milliseconds: location.milliseconds, sequence: ++seekSequence };
  locateSequence.value++;
  reviewingEvidence.value = false;
}
function writeLocation(push = false) {
  clearTimeout(locationTimer);
  locationTimer = undefined;
  const query = { view: activeWorkspace.value, ...(readingView.value ? { text: readingView.value } : {}), at: String(positionMs.value) };
  const signature = locationSignature(query);
  if (signature === locationSignature(route.query)) return;
  pendingLocations.add(signature);
  // Explicit view changes create history; playback updates replace only the current entry.
  void router[push ? "push" : "replace"]({ path: route.path, query }).finally(() => pendingLocations.delete(signature));
}
function updatePosition(milliseconds: number) {
  if (!validPosition(milliseconds)) return;
  positionMs.value = milliseconds;
  if (!locationTimer) locationTimer = setTimeout(() => { locationTimer = undefined; writeLocation(); }, 1500);
}
function changeWorkspace(workspace: CourseWorkspace) {
  evidenceSeekGuard.cancel();
  evidenceNavigationError.value = "";
  activeWorkspace.value = workspace;
  reviewingEvidence.value = false;
  writeLocation(true);
}
function changeReadingView(view: ContentView) { evidenceSeekGuard.cancel(); readingView.value = view; writeLocation(); }
async function returnToLearning() {
  evidenceSeekGuard.cancel();
  reviewingEvidence.value = false;
  await nextTick();
  returnFocus?.focus({ preventScroll: true });
  window.scrollTo({ top: returnScroll });
}

async function loadPublicRuntimeConfiguration() {
  try {
    isDemoMode.value = (await fetchPublicRuntimeConfiguration()).demoMode === true;
  } catch {
    // Do not show a Demo notice when the backend cannot verify the active provider mode.
    isDemoMode.value = false;
  }
}

function seekTo(startTimeMillis: number, context?: EvidenceSeekContext) {
  if (!validPosition(startTimeMillis)) return;
  evidenceNavigationError.value = "";
  void evidenceSeekGuard.seek(taskId.value, context, () => applySeek(startTimeMillis));
}
function applySeek(startTimeMillis: number) {
  positionMs.value = startTimeMillis;
  seekRequest.value = { milliseconds: startTimeMillis, sequence: ++seekSequence };
  readingView.value = "timeline";
  locateSequence.value++;
  if (activeWorkspace.value !== "content") {
    if (!reviewingEvidence.value) {
      returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      returnScroll = window.scrollY;
    }
    reviewingEvidence.value = true;
    void nextTick(() => evidenceRef.value?.scrollIntoView({ block: "start" }));
  }
  writeLocation();
}

function reconnect() {
  scopeRefresh.value++;
  evidenceSeekGuard.cancel();
  reviewingEvidence.value = false;
  taskEventsStore.reconnect();
  void loadTaskDetail(taskId.value);
  void taskResultStore.load(taskId.value);
  void refreshTaskPlayback(taskId.value);
  void refreshTaskEmbeddedSubtitles(taskId.value);
}

function clearTaskDetail() {
  taskDetailRequestVersion.value += 1;
  taskDetail.value = null;
}

async function loadTaskDetail(currentTaskId: string) {
  const normalizedTaskId = currentTaskId.trim();
  if (!normalizedTaskId) { clearTaskDetail(); return; }
  const version = taskDetailRequestVersion.value + 1;
  taskDetailRequestVersion.value = version;
  taskDetail.value = null;
  try {
    const response = await fetchTaskDetail(normalizedTaskId);
    if (version === taskDetailRequestVersion.value) taskDetail.value = response;
  } catch {
    if (version === taskDetailRequestVersion.value) taskDetail.value = null;
  }
}

function clearTaskPlayback() {
  playbackRequestVersion.value += 1;
  playbackUrl.value = "";
  playbackExpiresAt.value = "";
  playbackLoading.value = false;
  playbackError.value = "";
}

async function refreshTaskPlayback(currentTaskId = taskId.value) {
  const normalizedTaskId = currentTaskId.trim();
  if (!normalizedTaskId) { clearTaskPlayback(); return; }
  const version = playbackRequestVersion.value + 1;
  playbackRequestVersion.value = version;
  playbackLoading.value = true;
  playbackError.value = "";
  playbackUrl.value = "";
  playbackExpiresAt.value = "";
  try {
    const response = await requestTaskPlaybackToken(normalizedTaskId);
    if (version !== playbackRequestVersion.value) return;
    playbackUrl.value = response.playbackUrl;
    playbackExpiresAt.value = response.expiresAt;
  } catch (error) {
    if (version !== playbackRequestVersion.value) return;
    playbackUrl.value = "";
    playbackExpiresAt.value = "";
    playbackError.value = toReadablePlaybackError(error);
  } finally {
    if (version === playbackRequestVersion.value) playbackLoading.value = false;
  }
}

function revokeSubtitleUrl() {
  if (subtitleTrackUrl.value) {
    URL.revokeObjectURL(subtitleTrackUrl.value);
    subtitleTrackUrl.value = "";
  }
}

function clearTaskEmbeddedSubtitles(status: SubtitleStatus = "none") {
  subtitleRequestVersion.value += 1;
  subtitleText.value = "";
  subtitleLanguage.value = "und";
  subtitleStatus.value = status;
  subtitleMessage.value = "";
  revokeSubtitleUrl();
}

async function refreshTaskEmbeddedSubtitles(currentTaskId: string) {
  const normalizedTaskId = currentTaskId.trim();
  if (!normalizedTaskId) { clearTaskEmbeddedSubtitles(); return; }
  const version = subtitleRequestVersion.value + 1;
  subtitleRequestVersion.value = version;
  subtitleStatus.value = "loading";
  subtitleMessage.value = "";
  subtitleText.value = "";
  subtitleLanguage.value = "und";
  revokeSubtitleUrl();
  try {
    const probe = await probeTaskEmbeddedSubtitles(normalizedTaskId);
    if (version !== subtitleRequestVersion.value) return;
    if (probe.status === "NOT_FOUND" || probe.selectedStreamIndex === null) { subtitleStatus.value = "not_found"; return; }
    if (probe.status === "UNSUPPORTED") { subtitleStatus.value = "unsupported"; return; }
    const selectedTrack = probe.tracks.find((track) => track.streamIndex === probe.selectedStreamIndex);
    subtitleLanguage.value = normalizeSubtitleLanguage(selectedTrack?.language);
    const vttText = await downloadTaskEmbeddedSubtitle(normalizedTaskId, probe.selectedStreamIndex);
    if (version !== subtitleRequestVersion.value) return;
    subtitleText.value = vttText;
    subtitleTrackUrl.value = URL.createObjectURL(new Blob([vttText], { type: "text/vtt;charset=utf-8" }));
    subtitleStatus.value = "loaded";
  } catch (error) {
    if (version !== subtitleRequestVersion.value) return;
    subtitleStatus.value = "failed";
    subtitleMessage.value = toReadableEmbeddedSubtitleError(error);
    subtitleText.value = "";
    subtitleLanguage.value = "und";
    revokeSubtitleUrl();
  }
}

function refreshTaskVideo() {
  void refreshTaskPlayback(taskId.value);
  void refreshTaskEmbeddedSubtitles(taskId.value);
}

async function confirmCancelTask() {
  if (!taskId.value || cancelLoading.value) return;
  const currentTaskId = taskId.value;
  const version = commandVersion.value;
  try {
    await ElMessageBox.confirm("取消后课程将停止继续处理，已生成的数据会保留。确定取消吗？", "取消处理", {
      confirmButtonText: "确认取消",
      cancelButtonText: "继续等待",
      type: "warning",
    });
  } catch { return; }
  if (version !== commandVersion.value || taskId.value !== currentTaskId) return;
  cancelLoading.value = true;
  try {
    await cancelTask(currentTaskId);
    if (version !== commandVersion.value || taskId.value !== currentTaskId) return;
    ElMessage.success("取消请求已提交");
    reconnect();
  } catch (error) {
    if (version === commandVersion.value && taskId.value === currentTaskId) ElMessage.error(toReadableTaskError(error));
  } finally {
    if (version === commandVersion.value && taskId.value === currentTaskId) cancelLoading.value = false;
  }
}

async function confirmRetryTask() {
  if (!taskId.value || retryLoading.value) return;
  const currentTaskId = taskId.value;
  const version = commandVersion.value;
  try {
    await ElMessageBox.confirm("系统会基于原视频创建新的处理任务，原失败记录会保留。确定重新处理吗？", "重新处理", {
      confirmButtonText: "重新处理",
      cancelButtonText: "取消",
      type: "warning",
    });
  } catch { return; }
  if (version !== commandVersion.value || taskId.value !== currentTaskId) return;
  retryLoading.value = true;
  try {
    const response = await retryTask(currentTaskId);
    if (version !== commandVersion.value || taskId.value !== currentTaskId) return;
    ElMessage.success("已创建新的处理任务，正在打开课程详情。");
    await router.push(`/tasks/${encodeURIComponent(response.newTaskId)}`);
  } catch (error) {
    if (version === commandVersion.value && taskId.value === currentTaskId) ElMessage.error(toReadableTaskError(error));
  } finally {
    if (version === commandVersion.value && taskId.value === currentTaskId) retryLoading.value = false;
  }
}
</script>

<template>
  <main class="course-workspace-page">
    <div class="course-workspace-page__inner">
      <CourseWorkspaceHeader
        :status="task?.status"
        :can-cancel="canCancelTask"
        :can-retry="canRetryTask"
        :refreshing="taskEventsStore.isConnecting || taskResultStore.loading"
        :cancel-loading="cancelLoading"
        :retry-loading="retryLoading"
        @refresh="reconnect"
        @cancel="confirmCancelTask"
        @retry="confirmRetryTask"
      />

      <el-alert
        v-if="isDemoMode"
        class="demo-notice"
        :closable="false"
        title="当前使用本地演示数据，未调用外部 AI 服务。"
        type="info"
        show-icon
      />

      <CourseModelUsagePanel v-if="hasTaskId && task" :key="taskId" :task-id="taskId" />

      <el-empty v-if="!hasTaskId" description="课程地址中缺少任务 ID" />
      <div v-else class="course-layout">
        <div class="course-layout__media">
          <CourseVideoAside
            :key="taskId"
            :seek-request="seekRequest"
            @position="updatePosition"
            @manual-seek="evidenceSeekGuard.cancel()"
            :task="task"
            :task-detail="taskDetail"
            :connection-status="taskEventsStore.connectionStatus"
            :connection-error="taskEventsStore.errorMessage"
            :last-heartbeat-at="taskEventsStore.lastHeartbeatAt"
            :playback-url="playbackUrl"
            :playback-loading="playbackLoading"
            :playback-error="playbackError"
            :playback-expires-at="playbackExpiresAt"
            :subtitle-track-url="subtitleTrackUrl"
            :subtitle-text="subtitleText"
            :subtitle-language="subtitleLanguage"
            :subtitle-status="subtitleStatus"
            :subtitle-message="subtitleMessage"
            @refresh-video="refreshTaskVideo"
          />
        </div>

        <section class="course-layout__content" aria-label="课程学习工作台">
          <CourseWorkspaceNav :active="activeWorkspace" @change="changeWorkspace" />
          <el-alert v-if="evidenceNavigationError" :closable="false" :title="evidenceNavigationError" type="warning" show-icon />
          <el-alert v-if="taskResultStore.errorMessage" :closable="false" :title="taskResultStore.errorMessage" type="error" show-icon />
          <el-skeleton v-if="taskResultStore.loading && !result" :rows="6" animated />
          <div v-show="activeWorkspace === 'content' || reviewingEvidence" ref="evidenceRef" class="evidence-reading">
            <div v-if="reviewingEvidence" class="evidence-reading__return"><span>回看课程原文，当前学习任务保留在下方。</span><button type="button" @click="returnToLearning">返回当前学习任务</button></div>
            <CourseContentPanel :key="taskId" :task-id="taskId" :status="task?.status" :result="result" :position-ms="positionMs" :view="readingView" :visible="activeWorkspace === 'content' || reviewingEvidence" :locate-sequence="locateSequence" @update:view="changeReadingView" @seek="seekTo" />
          </div>
          <CourseScopePicker :key="taskId" v-show="activeWorkspace === 'agent' || activeWorkspace === 'qa'" v-model="learningScope" :task-id="taskId" :refresh-key="scopeRefresh" :frozen-scope="activeWorkspace === 'agent' ? agentScope : qaScope" @seek="seekTo" />
          <KeepAlive :key="taskId">
            <CourseOverviewPanel
              v-if="activeWorkspace === 'overview'"
              :task="task"
              :task-detail="taskDetail"
              :result="result"
              :can-retry="canRetryTask"
              :retry-loading="retryLoading"
              @navigate="changeWorkspace"
              @retry="confirmRetryTask"
            />
            <CourseStudyPanel v-else-if="activeWorkspace === 'study'" :task-id="taskId" :status="task?.status" :result="result" @seek="seekTo" />
            <CourseAgentPanel :learning-scope="learningScope" @frozen-scope="agentScope = $event" v-else-if="activeWorkspace === 'agent'" :task-id="taskId" :status="task?.status" @seek="seekTo" @navigate="changeWorkspace" />
            <CourseQaPanel :learning-scope="learningScope" @frozen-scope="qaScope = $event" v-else-if="activeWorkspace === 'qa'" :task-id="taskId" @seek="seekTo" />
            <CourseFilesPanel v-else-if="activeWorkspace === 'files'" :task-id="taskId" :status="task?.status" :artifacts="result?.artifacts ?? []" />
            <CourseTechnicalPanel
              v-else-if="activeWorkspace === 'technical'"
              :task-id="taskId"
              :task="task"
              :task-detail="taskDetail"
              :result="result"
              :connection-status="taskEventsStore.connectionStatus"
              :last-heartbeat-at="taskEventsStore.lastHeartbeatAt"
            />
          </KeepAlive>
        </section>
      </div>
    </div>
  </main>
</template>

<style scoped>
.course-workspace-page { min-height: calc(100vh - var(--header-height)); background: var(--color-canvas); }
.course-workspace-page__inner { width: min(1360px, calc(100% - 48px)); margin: 0 auto; padding: 30px 0 64px; }
.evidence-reading { min-width: 0; scroll-margin-top: calc(var(--header-height) + 12px); }
.evidence-reading__return { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; margin-bottom: 12px; color: var(--color-ink-soft); }
.evidence-reading__return button { font: inherit; color: var(--color-brand); padding: 8px 12px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); cursor: pointer; }
.demo-notice { margin-top: 18px; }
.course-layout { display: grid; grid-template-columns: minmax(360px, 420px) minmax(0, 1fr); gap: 24px; align-items: start; margin-top: 24px; }
.course-layout__media { position: sticky; top: calc(var(--header-height) + 24px); min-width: 0; }
.course-layout__content { display: grid; gap: 16px; min-width: 0; }
@media (max-width: 1080px) { .course-layout { grid-template-columns: minmax(320px, 370px) minmax(0, 1fr); gap: 18px; } }
@media (max-width: 1024px) { .course-workspace-page :deep(button) { min-height: 40px; } }
@media (max-width: 900px) { .course-workspace-page__inner { width: min(100% - 32px, 760px); }.course-layout { grid-template-columns: 1fr; }.course-layout__media { position: static; } }
@media (max-width: 520px) { .course-workspace-page__inner { width: min(100% - 24px, 760px); padding-top: 22px; }.course-layout { margin-top: 18px; } }
</style>
