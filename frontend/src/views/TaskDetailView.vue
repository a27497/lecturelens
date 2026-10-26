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
import { mayHaveLostCourseAccess } from "../api/courseAccess";
import type { LearningTaskPosition } from "../components/task-detail/learningTaskPosition";
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
import CourseFlashcardsPanel from "../components/task-detail/CourseFlashcardsPanel.vue";
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
const classicLayout = ref(false);
const narrowQuery = window.matchMedia("(max-width: 900px)");
const narrowScreen = ref(narrowQuery.matches);
function updateNarrowScreen() { narrowScreen.value = narrowQuery.matches; }
const lastLearningWorkspace = ref<"agent" | "qa" | "flashcards">("agent");
const learningWorkspace = computed(() => !classicLayout.value && activeWorkspace.value === "content" ? lastLearningWorkspace.value : activeWorkspace.value);
const materialsRef = ref<HTMLElement | null>(null);
const readingTarget = ref<HTMLElement | null>(null);
const mobileNavTarget = ref<HTMLElement | null>(null);
// A verified citation stays anchored as playback advances; plain timeline seeks are not citations.
const referenceMs = ref<number>();
const readerRef = ref<{ currentView: () => ContentView } | null>(null);
const evidenceErrorRef = ref<HTMLElement | null>(null);
const learningRef = ref<HTMLElement | null>(null);
const learningTask = ref<LearningTaskPosition | null>(null);
const courseBlocked = ref(false);
const verifyingEvidence = ref(false);
const readerVisible = computed(() => !verifyingEvidence.value && !evidenceNavigationError.value &&
  (classicLayout.value ? activeWorkspace.value === "content" || reviewingEvidence.value :
    !narrowScreen.value || activeWorkspace.value === "content" || reviewingEvidence.value));
let evidenceRequest = 0;
const readingView = ref<ContentView>();
const positionMs = ref(0);
const seekRequest = ref<SeekRequest>();
const locateSequence = ref(0);
const reviewingEvidence = ref(false);
// Match both the mobile material-column CSS and the citation v-show, without remounting media.
const playerVisible = computed(() => classicLayout.value || !narrowScreen.value ||
  (!evidenceNavigationError.value && activeWorkspace.value === "content" && !reviewingEvidence.value));
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
  async id => {
    try { return (await getEvidenceIndexStatus(id)).revision; }
    catch (failure) { if (id === taskId.value && mayHaveLostCourseAccess(failure)) void loadTaskDetail(id); throw failure; }
  },
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
  narrowQuery.addEventListener("change", updateNarrowScreen);
  void loadPublicRuntimeConfiguration();
});

watch(taskId, (nextTaskId) => {
  courseBlocked.value = false; learningTask.value = null; lastLearningWorkspace.value = "agent";
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

watch([evidenceNavigationError, narrowScreen], ([message, narrow]) => {
  if (!message || !narrow) return;
  const currentTaskId = taskId.value;
  void nextTick(() => {
    if (taskId.value === currentTaskId && evidenceNavigationError.value === message && narrowScreen.value) {
      evidenceErrorRef.value?.scrollIntoView({ block: "start" });
    }
  });
});

watch(() => task.value?.status, (status) => {
  const currentTaskId = taskId.value.trim();
  if (!currentTaskId) return;
  if (shouldReloadTerminalTaskDetail(status, currentTaskId, terminalDetailReloadTaskId.value)) {
    cancelEvidenceNavigation();
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
  narrowQuery.removeEventListener("change", updateNarrowScreen);
  cancelEvidenceNavigation();
  clearTimeout(locationTimer);
  taskEventsStore.disconnect();
  taskResultStore.clear();
  clearTaskDetail();
  clearTaskPlayback();
  clearTaskEmbeddedSubtitles();
});

function locationSignature(query: typeof route.query) {
  return JSON.stringify([taskId.value, query.view, query.text, query.at, query.layout]);
}
function applyLocation() {
  cancelEvidenceNavigation();
  evidenceNavigationError.value = "";
  clearTimeout(locationTimer);
  locationTimer = undefined;
  const location = readCourseLocation(route.query);
  classicLayout.value = location.classic;
  activeWorkspace.value = location.workspace;
  if (location.workspace === "qa" || location.workspace === "agent" || location.workspace === "flashcards") lastLearningWorkspace.value = location.workspace;
  readingView.value = location.textView;
  positionMs.value = location.milliseconds;
  seekRequest.value = { milliseconds: location.milliseconds, sequence: ++seekSequence };
  locateSequence.value++;
  reviewingEvidence.value = false;
}
function writeLocation(push = false) {
  clearTimeout(locationTimer);
  locationTimer = undefined;
  const query = { view: activeWorkspace.value, ...(readingView.value ? { text: readingView.value } : {}), at: String(positionMs.value), ...(classicLayout.value ? { layout: "classic" } : {}) };
  const signature = locationSignature(query);
  // A return to the current URL must also supersede an earlier queued navigation.
  if (signature === locationSignature(route.query) && pendingLocations.size === 0) return;
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
  cancelEvidenceNavigation();
  evidenceNavigationError.value = "";
  activeWorkspace.value = workspace;
  if (workspace === "qa" || workspace === "agent" || workspace === "flashcards") lastLearningWorkspace.value = workspace;
  reviewingEvidence.value = false;
  writeLocation(true);
}
function changeLayout() {
  readingView.value = readerRef.value?.currentView() ?? readingView.value;
  classicLayout.value = !classicLayout.value;
  writeLocation(true);
}
async function showMaterials() {
  changeWorkspace("content");
  await nextTick();
  materialsRef.value?.scrollTo({ top: 0 });
  (classicLayout.value ? evidenceRef.value : materialsRef.value)?.scrollIntoView({ block: "start" });
}
async function showLearning() {
  changeWorkspace(lastLearningWorkspace.value);
  await nextTick();
  learningRef.value?.scrollIntoView({ block: "start" });
  const input = learningRef.value?.querySelector<HTMLTextAreaElement>(".practice-question.is-current textarea") ?? learningRef.value?.querySelector<HTMLTextAreaElement>(".qa-form textarea, .agent-panel textarea");
  input?.focus({ preventScroll: true });
}
function changeReadingView(view: ContentView) { cancelEvidenceNavigation(); readingView.value = view; writeLocation(); }
async function returnToLearning() {
  if (activeWorkspace.value === "content") {
    await showLearning();
    return;
  }
  cancelEvidenceNavigation();
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

async function seekTo(startTimeMillis: number, context?: EvidenceSeekContext) {
  if (!validPosition(startTimeMillis)) return;
  const request = ++evidenceRequest;
  referenceMs.value = undefined;
  evidenceNavigationError.value = "";
  verifyingEvidence.value = Boolean(context);
  let applied = false;
  try { await evidenceSeekGuard.seek(taskId.value, context, () => { applySeek(startTimeMillis, Boolean(context)); applied = true; }); }
  finally {
    if (request === evidenceRequest) {
      verifyingEvidence.value = false;
      // Wait until the verified reader is visible before measuring or moving it.
      if (applied && reviewingEvidence.value) {
        await nextTick();
        if (request === evidenceRequest) {
          if (classicLayout.value || narrowScreen.value) {
            evidenceRef.value?.scrollIntoView({ block: "start" });
            if (!classicLayout.value) evidenceRef.value?.querySelector<HTMLElement>(".timeline-row[data-reference=true]")?.scrollIntoView({ block: "start" });
          }
          else if (materialsRef.value && evidenceRef.value) {
            materialsRef.value.scrollTop += evidenceRef.value.getBoundingClientRect().top - materialsRef.value.getBoundingClientRect().top - 8;
          }
        }
      }
    }
  }
}
function applySeek(startTimeMillis: number, reference = false) {
  referenceMs.value = reference ? startTimeMillis : undefined;
  positionMs.value = startTimeMillis;
  seekRequest.value = { milliseconds: startTimeMillis, sequence: ++seekSequence };
  readingView.value = "timeline";
  locateSequence.value++;
  if (reference || activeWorkspace.value !== "content") {
    if (!reviewingEvidence.value) {
      returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      returnScroll = window.scrollY;
    }
    reviewingEvidence.value = true;
  }
  writeLocation();
}

function reconnect() {
  scopeRefresh.value++;
  cancelEvidenceNavigation();
  reviewingEvidence.value = false;
  evidenceNavigationError.value = "";
  taskEventsStore.reconnect();
  void loadTaskDetail(taskId.value);
  void taskResultStore.load(taskId.value);
  void refreshTaskPlayback(taskId.value);
  void refreshTaskEmbeddedSubtitles(taskId.value);
}

function blockCourse() {
  if (courseBlocked.value) return;
  courseBlocked.value = true;
  cancelEvidenceNavigation();
  taskEventsStore.disconnect(); taskResultStore.clear();
  clearTaskDetail(); clearTaskPlayback(); clearTaskEmbeddedSubtitles();
  learningScope.value = null; agentScope.value = undefined; qaScope.value = undefined;
  learningTask.value = null; returnFocus = null; reviewingEvidence.value = false;
}

function cancelEvidenceNavigation() {
  evidenceSeekGuard.cancel(); evidenceRequest++; verifyingEvidence.value = false;
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
  } catch (error) {
    if (version === taskDetailRequestVersion.value) {
      taskDetail.value = null;
      if (mayHaveLostCourseAccess(error)) blockCourse();
    }
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
  <main class="course-workspace-page" :class="{ 'is-mobile-evidence': !classicLayout && narrowScreen && reviewingEvidence }">
    <div class="course-workspace-page__inner">
      <CourseWorkspaceHeader
        :compact="!classicLayout"
        :demo-mode="isDemoMode"
        v-show="!courseBlocked && !(reviewingEvidence && narrowScreen && !classicLayout)"
        :status="task?.status"
        :can-cancel="canCancelTask"
        :can-retry="canRetryTask"
        :refreshing="taskEventsStore.isConnecting || taskResultStore.loading"
        :cancel-loading="cancelLoading"
        :retry-loading="retryLoading"
        @refresh="reconnect"
        @cancel="confirmCancelTask"
        @retry="confirmRetryTask"
      >
        <template v-if="!classicLayout" #workspace-actions><button type="button" class="layout-switch" @click="changeLayout">经典布局</button></template>
      </CourseWorkspaceHeader>

      <el-alert
        v-if="isDemoMode && classicLayout"
        class="demo-notice"
        :closable="false"
        title="当前使用本地演示数据，未调用外部 AI 服务。"
        type="info"
        show-icon
      />

      <div v-if="hasTaskId && !courseBlocked && classicLayout" v-show="!(reviewingEvidence && narrowScreen && !classicLayout)" class="workspace-wayfinding" aria-label="学习工作区导航">
        <div class="workspace-wayfinding__actions">
          <button type="button" :aria-pressed="activeWorkspace === 'content'" @click="showMaterials">看视频与原文</button>
          <button type="button" :aria-pressed="activeWorkspace !== 'content'" @click="showLearning">{{ lastLearningWorkspace === 'flashcards' ? '返回闪卡复习' : lastLearningWorkspace === 'qa' ? '返回课程问答' : learningTask?.totalQuestions ? `继续第 ${learningTask.questionIndex + 1} 题` : '解释与练习' }}</button>
        </div>
        <button type="button" class="layout-switch" @click="changeLayout">{{ classicLayout ? '连续工作区' : '经典布局' }}</button>
      </div>

      <div v-if="hasTaskId && !courseBlocked && !classicLayout" v-show="!reviewingEvidence" ref="mobileNavTarget" class="mobile-workspace-nav-target" />

      <el-empty v-if="!hasTaskId" description="课程地址中缺少任务 ID" />
      <section v-else-if="courseBlocked" role="alert" class="course-unavailable">
        <h2>课程不可用或权限已变化</h2>
        <p>已停止显示此课程的缓存内容。请从课程列表重新打开；已保存记录仍由服务端权限决定是否可读取。</p>
        <RouterLink to="/tasks">返回我的课程</RouterLink>
      </section>
      <div v-else class="course-layout" :class="{ 'course-layout--continuous': !classicLayout, 'is-reading': !evidenceNavigationError && (activeWorkspace === 'content' || reviewingEvidence) }">
        <div ref="materialsRef" class="course-layout__media" aria-label="视频与课程材料">
          <CourseVideoAside
            v-show="!(reviewingEvidence && narrowScreen && !classicLayout)"
            :key="taskId"
            :compact="!classicLayout"
            :inactive="!playerVisible"
            :seek-request="seekRequest"
            @position="updatePosition"
            @manual-seek="cancelEvidenceNavigation"
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
          <p v-if="verifyingEvidence" role="status">正在核对来源版本，当前学习任务保留。</p>
          <div ref="readingTarget" class="materials-reading-target" />
        </div>

        <section ref="learningRef" class="course-layout__content" aria-label="课程学习工作台">
          <div v-if="!classicLayout && !learningTask" class="learning-context">
            <p class="learning-context__eyebrow">同一节课 · 继续学习</p>
            <p>先阅读课程，向 Tutor 提问；需要自测时再发起解释与练习。</p>
          </div>
          <aside v-if="reviewingEvidence && learningTask && lastLearningWorkspace === 'agent' && !classicLayout" class="learning-evidence-context">
            <strong>正在核对第 {{ learningTask.questionIndex + 1 }} 题</strong>
            <p>{{ learningTask.question }}</p><button type="button" @click="returnToLearning">返回本题作答</button>
          </aside>
          <Teleport :to="mobileNavTarget || 'body'" :disabled="classicLayout || !narrowScreen || !mobileNavTarget">
            <CourseWorkspaceNav :active="activeWorkspace" :compact="!classicLayout" :materials="!classicLayout && narrowScreen" @change="changeWorkspace" />
          </Teleport>
          <div v-if="evidenceNavigationError" ref="evidenceErrorRef" class="evidence-navigation-error"><el-alert :closable="false" :title="evidenceNavigationError" type="warning" show-icon /></div>
          <el-alert v-if="taskResultStore.errorMessage" :closable="false" :title="taskResultStore.errorMessage" type="error" show-icon />
          <el-skeleton v-if="taskResultStore.loading && !result" :rows="6" animated />
          <!-- Move one reader between layouts; do not duplicate or remount its local state. -->
          <Teleport :to="readingTarget || 'body'" :disabled="classicLayout || !readingTarget">
            <div v-show="readerVisible" ref="evidenceRef" class="evidence-reading">
              <div v-if="reviewingEvidence" class="evidence-reading__return">
                <span><small v-if="isDemoMode" class="review-mode">本地演示 · 无外部 AI</small> {{ learningTask && lastLearningWorkspace === 'agent' ? `正在核对第 ${learningTask.questionIndex + 1} 题：${learningTask.question}` : '回看课程原文，当前提问与草稿保留。' }}</span>
                <button type="button" @click="returnToLearning">返回当前学习任务</button>
              </div>
              <CourseContentPanel :reference-ms="reviewingEvidence ? referenceMs : undefined" :compact="!classicLayout" ref="readerRef" :key="taskId" :task-id="taskId" :status="task?.status" :result="result" :position-ms="positionMs" :view="readingView ?? (classicLayout ? undefined : 'timeline')" :visible="readerVisible" :locate-sequence="locateSequence" @update:view="changeReadingView" @seek="seekTo" />
            </div>
          </Teleport>
          <CourseScopePicker :key="taskId" :compact="!classicLayout" v-show="learningWorkspace === 'agent' || learningWorkspace === 'qa'" @access-failure="loadTaskDetail(taskId)" v-model="learningScope" :task-id="taskId" :refresh-key="scopeRefresh" :frozen-scope="learningWorkspace === 'agent' ? agentScope : qaScope" @seek="seekTo" />
          <KeepAlive :key="taskId">
            <CourseOverviewPanel
              v-if="learningWorkspace === 'overview'"
              :task="task"
              :task-detail="taskDetail"
              :result="result"
              :can-retry="canRetryTask"
              :retry-loading="retryLoading"
              @navigate="changeWorkspace"
              @retry="confirmRetryTask"
            />
            <CourseFlashcardsPanel v-else-if="learningWorkspace === 'flashcards'" :task-id="taskId" @seek="seekTo" @access-failure="loadTaskDetail(taskId)" />
            <CourseStudyPanel v-else-if="learningWorkspace === 'study'" :task-id="taskId" :status="task?.status" :result="result" @seek="seekTo" />
            <CourseAgentPanel :compact="!classicLayout" @position="learningTask = $event" @access-failure="loadTaskDetail(taskId)" :learning-scope="learningScope" @frozen-scope="agentScope = $event" v-else-if="learningWorkspace === 'agent'" :task-id="taskId" :status="task?.status" @seek="seekTo" @navigate="changeWorkspace" />
            <CourseQaPanel @access-failure="loadTaskDetail(taskId)" :learning-scope="learningScope" @frozen-scope="qaScope = $event" v-else-if="learningWorkspace === 'qa'" :task-id="taskId" @seek="seekTo" />
            <CourseFilesPanel v-else-if="learningWorkspace === 'files'" :task-id="taskId" :status="task?.status" :artifacts="result?.artifacts ?? []" />
            <CourseTechnicalPanel
              v-else-if="learningWorkspace === 'technical'"
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
      <details v-if="hasTaskId && !courseBlocked" v-show="!(reviewingEvidence && narrowScreen && !classicLayout)" class="workspace-recovery">
        <summary>保存、恢复与课程记录</summary>
        <p>服务端保存学习会话、执行、作答版本、反馈与核对意见。刷新后读取最近的已保存学习记录。</p>
        <p>网址只恢复课程视图、布局与视频位置，恢复后保持暂停。未提交的问题、目标、作答和核对文字仅留在当前页面；刷新或离开后不会恢复。</p>
        <CourseModelUsagePanel v-if="task" :key="taskId" :task-id="taskId" />
      </details>
    </div>
  </main>
</template>

<style scoped>
.course-workspace-page { min-height: calc(100vh - var(--header-height)); background: var(--color-canvas); }
.course-workspace-page__inner { width: min(1360px, calc(100% - 48px)); margin: 0 auto; padding: 30px 0 64px; }
.evidence-navigation-error { scroll-margin-top: calc(var(--header-height) + 76px); }
.evidence-reading { min-width: 0; scroll-margin-top: calc(var(--header-height) + 12px); }
.evidence-reading__return { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; margin-bottom: 12px; color: var(--color-ink-soft); }
.review-mode { display: inline-block; margin-right: 6px; padding: 1px 5px; border-radius: var(--radius-sm); background: var(--color-brand-soft); color: var(--color-brand); font-size: 11px; }
.evidence-reading__return button { font: inherit; color: var(--color-brand); padding: 8px 12px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); cursor: pointer; }
.demo-notice { margin-top: 8px; }
.course-layout { display: grid; grid-template-columns: minmax(360px, 420px) minmax(0, 1fr); gap: 24px; align-items: start; margin-top: 24px; }
.course-layout__media { position: sticky; top: calc(var(--header-height) + 24px); min-width: 0; }
.course-layout__content { display: grid; gap: 16px; min-width: 0; }
@media (max-width: 1080px) { .course-layout { grid-template-columns: minmax(320px, 370px) minmax(0, 1fr); gap: 18px; } }
@media (max-width: 1024px) { .course-workspace-page :deep(button) { min-height: 40px; } }
@media (max-width: 900px) { .course-workspace-page__inner { width: min(100% - 32px, 760px); }.course-layout { grid-template-columns: 1fr; }.course-layout__media { position: static; } }
@media (max-width: 520px) { .course-workspace-page__inner { width: min(100% - 24px, 760px); padding-top: 22px; }.course-layout { margin-top: 18px; } }


.workspace-wayfinding { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; padding: 10px 0; position: sticky; top: var(--header-height); z-index: 5; background: var(--color-canvas); border-bottom: 1px solid var(--color-border); }
.workspace-wayfinding__actions { display: flex; flex-wrap: wrap; gap: 8px; }
.workspace-wayfinding button { font: inherit; padding: 8px 12px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); color: var(--color-brand); cursor: pointer; }
.workspace-wayfinding .layout-switch { font-size: 13px; color: var(--color-ink-soft); }
.course-layout--continuous { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
.course-layout--continuous .course-layout__media { display: grid; gap: 16px; max-height: calc(100dvh - var(--header-height) - 88px); overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; top: calc(var(--header-height) + 68px); }
.materials-reading-target:empty { display: none; }
.course-layout__content { scroll-margin-top: calc(var(--header-height) + 76px); }
.course-layout--continuous :deep(.content-panel), .course-layout--continuous :deep(.qa-panel), .course-layout--continuous :deep(.agent-panel) { padding: 20px; }
.course-layout--continuous :deep(.reading-copy) { max-height: 46vh; overflow-y: auto; overscroll-behavior: contain; }
.course-layout--continuous :deep(.timeline-list) { max-height: 46vh; }
.course-layout--continuous :deep(.course-video-player) { max-height: 28vh; object-fit: contain; }
.course-layout--continuous .evidence-reading { scroll-margin-top: calc(var(--header-height) + 76px); }
.course-layout--continuous :deep(.timeline-row) { grid-template-columns: minmax(0, 1fr); gap: 6px; }
.course-layout--continuous :deep(.timeline-row__time) { display: flex; gap: 12px; }
.learning-context p { margin: 0; line-height: 1.6; overflow-wrap: anywhere; }
.learning-context__eyebrow { font-size: 13px; color: var(--color-brand); font-weight: 700; margin-bottom: 5px !important; }
.workspace-recovery, .course-unavailable { margin-top: 20px; padding: 16px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); line-height: 1.7; }
.workspace-recovery summary { cursor: pointer; font-weight: 650; }
@media (max-width: 900px) {
  .course-layout--continuous { grid-template-columns: 1fr; }
  .course-layout--continuous .course-layout__media { position: static; max-height: none; overflow: visible; }
  .course-layout--continuous:not(.is-reading) .course-layout__media { display: none; }
  .course-layout--continuous.is-reading .course-layout__content { display: none; }
  .course-layout--continuous :deep(.timeline-list) { max-height: 40vh; }
  .evidence-reading__return { position: sticky; top: calc(var(--header-height) + 66px); z-index: 4; padding: 10px; background: var(--color-surface); border: 1px solid var(--color-border); }
}
@media (max-width: 520px) {
  .workspace-wayfinding { align-items: stretch; }.workspace-wayfinding .layout-switch { padding: 4px 8px; }
  .course-layout--continuous :deep(.content-panel), .course-layout--continuous :deep(.qa-panel), .course-layout--continuous :deep(.agent-panel) { padding: 14px; }
}


.course-workspace-page__inner { padding-top: 16px; }
.learning-evidence-context { position: sticky; top: calc(var(--header-height) + 58px); z-index: 7; padding: 12px; border: 1px solid var(--color-brand); border-radius: var(--radius-md); background: var(--color-brand-soft); }
.learning-evidence-context p { margin: 6px 0; font-size: 14px; line-height: 1.6; }
.learning-evidence-context button { font: inherit; padding: 8px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); color: var(--color-brand); cursor: pointer; }
.course-layout--continuous { gap: 24px; margin-top: 20px; }
.course-layout--continuous .course-layout__content { padding: 18px; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); gap: 12px; }
.course-layout--continuous :deep(.agent-panel), .course-layout--continuous :deep(.qa-panel) { padding: 0; border: 0; box-shadow: none; }
.course-layout--continuous :deep(.scope-picker) { margin: 0; padding: 10px 12px; background: var(--color-canvas); font-size: 13px; }

.course-layout--continuous .learning-context__eyebrow { margin: 0 !important; font-size: 12px; letter-spacing: .04em; }
.course-layout--continuous :deep(.agent-panel > header h2), .course-layout--continuous :deep(.qa-panel h2) { font-size: 20px; }
.course-layout--continuous :deep(.agent-panel > header p) { font-size: 13px; line-height: 1.6; }
.course-layout--continuous :deep(.study-artifact) { margin-top: 12px; gap: 12px; }
.course-layout--continuous :deep(.question-text) { font-size: 17px; line-height: 1.7; }
.course-layout--continuous :deep(.el-textarea__inner) { font-size: 15px; line-height: 1.7; }
.course-layout--continuous :deep(.practice-feedback h4) { margin-block: 8px; }
.course-layout--continuous :deep(.run-progress) { margin-top: 10px; }
.workspace-wayfinding [aria-pressed=true] { background: var(--color-brand-soft); border-color: var(--color-brand); }
button:focus-visible { outline: 2px solid var(--color-brand); outline-offset: 3px; }
@media (max-width: 900px) {
  .course-workspace-page__inner { padding-top: 14px; }
  .course-layout--continuous .course-layout__content { padding: 14px; }
  .course-layout--continuous :deep(.el-textarea__inner) { font-size: 16px; }
  .course-layout--continuous :deep(.agent-panel), .course-layout--continuous :deep(.qa-panel) { padding: 0; }
  .is-mobile-evidence .course-layout { margin-top: 0; }
  .is-mobile-evidence .course-layout__media { gap: 0; }
  .is-mobile-evidence .evidence-reading__return { top: var(--header-height); z-index: 6; margin-bottom: 8px; padding: 10px; flex-direction: column; gap: 8px; }
  .is-mobile-evidence .evidence-reading__return > span { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-size: 13px; }
  .is-mobile-evidence .evidence-reading__return button { width: 100%; min-height: 44px; }
  .is-mobile-evidence :deep(.timeline-list) { max-height: none; overflow: visible; }
  .is-mobile-evidence :deep(.timeline-row) { scroll-margin-top: calc(var(--header-height) + 136px); font-size: 15px; }
}


.mobile-workspace-nav-target { display: none; }
.course-layout--continuous { margin-top: 18px; gap: 22px; }
.course-layout--continuous .course-layout__media, .course-layout--continuous .course-layout__content { border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); padding: 18px; box-shadow: 0 3px 16px rgb(29 36 33 / 3%); }
.course-layout--continuous .course-layout__media { max-height: calc(100dvh - var(--header-height) - 30px); top: calc(var(--header-height) + 14px); gap: 16px; }
.course-layout--continuous :deep(.content-panel) { padding: 16px 0 0; border: 0; border-top: 1px solid var(--color-border); border-radius: 0; box-shadow: none; gap: 12px; }
.course-layout--continuous :deep(.content-panel > header) { display: none; }
.course-layout--continuous :deep(.course-video-player) { max-height: 25vh; border-radius: var(--radius-md); }
.course-layout--continuous :deep(.video-card__header h2) { font-size: 15px; font-weight: 650; }
.course-layout--continuous :deep(.video-card__header .el-button) { font-size: 12px; }
.course-layout--continuous :deep(.video-card) { gap: 10px; }
.course-layout--continuous :deep(.scope-picker) { padding: 0 0 10px; background: transparent; border: 0; border-bottom: 1px solid var(--color-border); border-radius: 0; }
.course-layout--continuous .learning-evidence-context { top: calc(var(--header-height) + 10px); }
.layout-switch { font: inherit; border: 1px solid var(--color-border); background: var(--color-surface); color: var(--color-ink-soft); border-radius: var(--radius-sm); padding: 7px 12px; cursor: pointer; }
@media (max-width: 900px) {
  .mobile-workspace-nav-target { display: block; position: sticky; top: var(--header-height); z-index: 10; background: var(--color-canvas); padding-block: 8px; }
  .mobile-workspace-nav-target :deep(.workspace-nav) { background: transparent; padding-bottom: 0; border: 0; }
  .mobile-workspace-nav-target :deep(.workspace-nav button) { font-size: 13px; min-height: 42px; padding: 8px 6px; }
  .mobile-workspace-nav-target :deep(.workspace-more) { flex: 0 0 auto; }
  .mobile-workspace-nav-target :deep(.workspace-more summary) { padding: 12px 8px; font-size: 12px; }
  .course-layout--continuous { margin-top: 8px; }
  .course-layout--continuous .course-layout__media, .course-layout--continuous .course-layout__content { padding: 14px; }
  .course-layout--continuous .course-layout__media { max-height: none; }
  .course-layout--continuous :deep(.scope-picker) { padding-bottom: 8px; }
  .is-mobile-evidence .course-layout__media { padding: 10px; }
  .is-mobile-evidence .evidence-reading__return { border: 0; border-bottom: 1px solid var(--color-border); border-radius: 0; padding: 8px 0; }
  .is-mobile-evidence :deep(.timeline-row[data-reference=true]) { scroll-margin-top: calc(var(--header-height) + 128px); }
}
</style>
