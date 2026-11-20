<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from "vue-router";
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
import { checkAuthSession } from "../api/authToken";
import { cancelTask, fetchTaskDetail, retryTask, toReadableTaskError } from "../api/task";
import CourseContentPanel from "../components/task-detail/CourseContentPanel.vue";
import CourseFilesPanel from "../components/task-detail/CourseFilesPanel.vue";
import CourseOverviewPanel from "../components/task-detail/CourseOverviewPanel.vue";
import CourseAgentPanel from "../components/task-detail/CourseAgentPanel.vue";
import CourseModelUsagePanel from "../components/task-detail/CourseModelUsagePanel.vue";
import CourseQaPanel from "../components/task-detail/CourseQaPanel.vue";
import CoursePreparationStatus from "../components/task-detail/CoursePreparationStatus.vue";
import CourseNotesPanel from "../components/task-detail/CourseNotesPanel.vue";
import type { NoteAnchor } from "../components/task-detail/courseNotes";
import CourseTutorPanel from "../components/task-detail/CourseTutorPanel.vue";
import CourseFlashcardsPanel from "../components/task-detail/CourseFlashcardsPanel.vue";
import CourseStudyPanel from "../components/task-detail/CourseStudyPanel.vue";
import CourseTechnicalPanel from "../components/task-detail/CourseTechnicalPanel.vue";
import CourseVideoAside from "../components/task-detail/CourseVideoAside.vue";
import CourseWorkspaceHeader from "../components/task-detail/CourseWorkspaceHeader.vue";
import CourseWorkspaceNav from "../components/task-detail/CourseWorkspaceNav.vue";
import { readCourseLocation, validPosition } from "../components/task-detail/courseLocation";
import type { ContentView, SeekRequest } from "../components/task-detail/courseLocation";
import type { CourseWorkspace } from "../components/task-detail/workspace";
import { courseLearnable, DEFAULT_LEARNING_WORKSPACE, isLearningWorkspace } from "../components/task-detail/workspace";
import { forgetLastCourseLocation, saveLastCourseLocation } from "../components/task-detail/lastCourseLocation";
import { useAuthStore } from "../stores/auth";
import { useTaskEventsStore } from "../stores/taskEvents";
import { useTaskResultStore } from "../stores/taskResult";
import type { TaskDetailResponse } from "../types/task";
import { isRetryableTaskStatus, shouldReloadTerminalTaskDetail } from "../utils/taskStatus";
import { formatMillisToClock } from "../utils/time";
import { normalizeSubtitleLanguage } from "../utils/subtitleLanguage";
import { isValidTimeRange } from "../utils/timeIndex";

import CourseLessonNav from "../components/task-detail/CourseLessonNav.vue";
import CourseLessonReader from "../components/task-detail/CourseLessonReader.vue";
import { loadRound3Course, round3Course, round3Enabled } from "../api/round3Demo";
import { courseNotesKey } from "../components/task-detail/courseNotes";

type SubtitleStatus = "none" | "loading" | "loaded" | "not_found" | "unsupported" | "failed";

const route = useRoute();
const router = useRouter();
const taskEventsStore = useTaskEventsStore();
const taskResultStore = useTaskResultStore();
const authStore = useAuthStore();

const activeWorkspace = ref<CourseWorkspace>(DEFAULT_LEARNING_WORKSPACE);
const classicLayout = ref(false);
const legacyLayout = ref(false);
const followLayout = computed(() => !classicLayout.value && !legacyLayout.value);
const tutorRef = ref<{ compose: (text?: string) => void }>();
const demo = computed(() => round3Course.value?.taskId === taskId.value && notesAccountId.value !== undefined ? round3Course.value : undefined);
const lessonProgress = computed(() => demo.value?.learningPercent);
const lessonName = computed(() => demo.value?.title ?? taskDetail.value?.courseName ?? "课程学习");

const narrowQuery = window.matchMedia("(max-width: 1024px)");
const narrowScreen = ref(narrowQuery.matches);
function updateNarrowScreen() { narrowScreen.value = narrowQuery.matches; }
const lastLearningWorkspace = ref<CourseWorkspace>(DEFAULT_LEARNING_WORKSPACE);
const rememberedMode = computed(() => !isLearningWorkspace(activeWorkspace.value) && lastLearningWorkspace.value !== DEFAULT_LEARNING_WORKSPACE ? lastLearningWorkspace.value : undefined);
const learningWorkspace = computed(() => !classicLayout.value && activeWorkspace.value === "content" ? lastLearningWorkspace.value : activeWorkspace.value);
const layoutRef = ref<HTMLElement | null>(null);
const materialsRef = ref<HTMLElement | null>(null);
const materialsTitle = ref<HTMLElement | null>(null);
const videoTarget = ref<HTMLElement | null>(null);
const readingTarget = ref<HTMLElement | null>(null);
const reviewTarget = ref<HTMLElement | null>(null);
const mobileNavTarget = ref<HTMLElement | null>(null);
// A verified citation stays anchored as playback advances; plain timeline seeks are not citations.
const referenceMs = ref<number>();
const activeCitation = ref<Extract<NoteAnchor, { kind: "evidence" }>>();
const noteCitation = ref<NoteAnchor>();
const notesRef = ref<InstanceType<typeof CourseNotesPanel> | null>(null);
const noteJumpError = ref("");
const playbackPosition = ref<number>();
const readerRef = ref<{ currentView: () => ContentView } | null>(null);
const evidenceErrorRef = ref<HTMLElement | null>(null);
const learningRef = ref<HTMLElement | null>(null);
const learningTask = ref<LearningTaskPosition | null>(null);
const courseBlocked = ref(false);
const workspaceOpened = ref(false);
const verifyingEvidence = ref(false);
const readerVisible = computed(() => (!verifyingEvidence.value || activeCitation.value) && !evidenceNavigationError.value &&
  (classicLayout.value ? activeWorkspace.value === "content" || reviewingEvidence.value :
    !narrowScreen.value || activeWorkspace.value === "content" || reviewingEvidence.value));
let evidenceRequest = 0;
const readingView = ref<ContentView>();
const positionMs = ref(0);
const seekRequest = ref<SeekRequest>();
const locateSequence = ref(0);
const reviewingEvidence = ref(false);
const videoRequested = ref(false);
// Match both the mobile material-column CSS and the citation v-show, without remounting media.
const playerVisible = computed(() => followLayout.value || classicLayout.value || !narrowScreen.value ||
  (!evidenceNavigationError.value && (reviewingEvidence.value ? videoRequested.value : activeWorkspace.value === "content")));
const evidenceRef = ref<HTMLElement | null>(null);
let seekSequence = 0;
let returnFocus: HTMLElement | null = null;
let returnScroll = 0;
let lastLearningFocus: HTMLElement | null = null;
let materialReturn: { workspace: CourseWorkspace; focus: HTMLElement | null; scroll: number } | undefined;
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
const taskDetailAccount = ref<number>();
const taskDetailError = ref("");
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
const task = computed(() => workspaceOpened.value ? taskEventsStore.task : null);
const status = computed(() => task.value?.status ?? taskDetail.value?.status);
/** Subtitles-ready learning: the live event wins; task detail covers the time before the first event. */
const learningReady = computed(() => task.value?.learningReady ?? taskDetail.value?.learningReady ?? null);
const learnable = computed(() => courseLearnable(status.value, learningReady.value));
const result = computed(() => taskResultStore.result);
const videoCitation = computed(() => {
  const citation = activeCitation.value;
  if (reviewingEvidence.value && playbackUrl.value && citation && referenceMs.value === citation.milliseconds
    && hasTimedSource(citation.milliseconds)) return citation;
  return undefined;
});
function hasTimedSource(milliseconds: number) {
  const source = result.value;
  return source?.taskId === taskId.value && source.subtitles.some(({ startMillis, endMillis }) =>
    isValidTimeRange(startMillis, endMillis) && startMillis <= milliseconds && milliseconds < endMillis);
}
const hasTaskId = computed(() => taskId.value.trim().length > 0);
const canCancelTask = computed(() => ["CREATED", "QUEUED", "RUNNING", "RETRYING"].includes(status.value || ""));
const canRetryTask = computed(() => isRetryableTaskStatus(status.value));
const isDemoMode = ref(false);
const notesAccountId = computed(() => {
  const account = authStore.user?.userId;
  if (authStore.isAuthenticated && !courseBlocked.value && taskDetail.value?.taskId === taskId.value
    && typeof account === "number" && Number.isSafeInteger(account) && account > 0 && account === taskDetailAccount.value) return account;
  return undefined;
});
const returnLabel = computed(() => {
  if (lastLearningWorkspace.value === "tutor") return "返回 Tutor 对话";
  if (lastLearningWorkspace.value === "notes") return "返回个人笔记";
  if (lastLearningWorkspace.value === "qa") return "返回课程问答";
  if (lastLearningWorkspace.value === "flashcards") return "返回闪卡复习";
  return learningTask.value?.totalQuestions ? `继续第 ${learningTask.value.questionIndex + 1} 题` : "解释与练习";
});

onMounted(() => {
  narrowQuery.addEventListener("change", updateNarrowScreen);
  void loadPublicRuntimeConfiguration();
  if (round3Enabled && !round3Course.value) void loadRound3Course().catch(() => {});
});
// Capture the latest playback position even if the throttled URL update is still pending.
onBeforeRouteLeave(rememberLocation);
onBeforeRouteUpdate((to, from) => {
  if (to.params.taskId !== from.params.taskId) rememberLocation();
});

function rememberLocation() {
  const userId = authStore.user?.userId;
  if (userId === undefined || taskDetail.value?.taskId !== taskId.value) return;
  try {
    if (!checkAuthSession()) return;
    saveLastCourseLocation(userId, taskId.value, {
      view: activeWorkspace.value, learn: rememberedMode.value ?? null, text: readingView.value ?? null, at: String(positionMs.value),
    });
  } catch { /* Browser storage may be unavailable during navigation. */ }
}

watch([taskId, () => authStore.user?.userId], ([nextTaskId, account], previous) => {
  if (previous?.[0] === nextTaskId && previous[1] === undefined) {
    if (taskDetail.value?.taskId === nextTaskId) taskDetailAccount.value = account;
    return; // Authentication's initial /me fills in the existing session's identity.
  }
  courseBlocked.value = false;
  workspaceOpened.value = false;
  learningTask.value = null;
  lastLearningWorkspace.value = DEFAULT_LEARNING_WORKSPACE;
  lastLearningFocus = null;
  materialReturn = undefined;
  playbackPosition.value = undefined;
  noteCitation.value = undefined;
  noteJumpError.value = "";
  clearTaskDetail();
  learningScope.value=null; agentScope.value=undefined; qaScope.value=undefined;
  commandVersion.value += 1;
  cancelLoading.value = false;
  retryLoading.value = false;
  taskEventsStore.disconnect();
  taskResultStore.clear();
  clearTaskPlayback();
  clearTaskEmbeddedSubtitles();
  clearTimeout(locationTimer);
  pendingLocations.clear();
  reviewingEvidence.value = false;
  returnFocus = null;
  applyLocation();
  completedResultReloadTaskId.value = "";
  terminalDetailReloadTaskId.value = "";
  void openCourse(nextTaskId);
}, { immediate: true });

watch(() => route.query, () => {
  const signature = locationSignature(route.query);
  if (pendingLocations.delete(signature)) return;
  clearTimeout(locationTimer);
  applyLocation();
});
watch(() => [authStore.user?.userId, taskDetail.value, route.query] as const, rememberLocation);

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
  if (status !== taskDetail.value?.status && shouldReloadTerminalTaskDetail(status, currentTaskId, terminalDetailReloadTaskId.value)) {
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

// While a learnable course is still running, pick up subtitles, translations and materials as each
// background stage starts, without clearing what the learner is already reading.
watch(() => [learnable.value, task.value?.currentStage] as const, ([open, stage], previous) => {
  const currentTaskId = taskId.value.trim();
  if (!currentTaskId || !open || task.value?.status !== "RUNNING") return;
  if (previous && previous[0] === open && previous[1] === stage) return;
  void taskResultStore.refresh(currentTaskId);
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
  return JSON.stringify([taskId.value, query.view, query.learn, query.text, query.at, query.layout]);
}
function applyLocation() {
  cancelEvidenceNavigation();
  evidenceNavigationError.value = "";
  clearTimeout(locationTimer);
  locationTimer = undefined;
  const location = readCourseLocation(route.query);
  classicLayout.value = location.classic;
  legacyLayout.value = route.query.layout === "continuous";
  activeWorkspace.value = followLayout.value && !route.query.view ? (narrowScreen.value ? "content" : "tutor") : location.workspace;
  lastLearningWorkspace.value = followLayout.value && (!route.query.view || (location.workspace === "content" && !route.query.learn))
    ? "tutor" : location.learningWorkspace;
  readingView.value = location.textView;
  positionMs.value = !route.query.at && demo.value ? demo.value.positionMs : location.milliseconds;
  seekRequest.value = { milliseconds: positionMs.value, sequence: ++seekSequence };
  locateSequence.value++;
  reviewingEvidence.value = false;
}
function writeLocation(push = false) {
  clearTimeout(locationTimer);
  locationTimer = undefined;
  const query = { view: activeWorkspace.value, ...(rememberedMode.value ? { learn: rememberedMode.value } : {}), ...(readingView.value ? { text: readingView.value } : {}), at: String(positionMs.value), ...(classicLayout.value ? { layout: "classic" } : legacyLayout.value ? { layout: "continuous" } : {}) };
  const signature = locationSignature(query);
  // A return to the current URL must also supersede an earlier queued navigation.
  if (signature === locationSignature(route.query) && pendingLocations.size === 0) return;
  pendingLocations.add(signature);
  // Explicit view changes create history; playback updates replace only the current entry.
  void router[push ? "push" : "replace"]({ path: route.path, query }).finally(() => pendingLocations.delete(signature));
}
function updatePosition(milliseconds: number) {
  if (!validPosition(milliseconds)) return;
  playbackPosition.value = milliseconds;
  positionMs.value = milliseconds;
  if (!locationTimer) locationTimer = setTimeout(() => { locationTimer = undefined; writeLocation(); }, 1500);
}
function changeWorkspace(workspace: CourseWorkspace) {
  if (workspace === "notes" && activeCitation.value) noteCitation.value = activeCitation.value;
  if (isLearningWorkspace(workspace) && lastLearningWorkspace.value !== workspace) lastLearningFocus = null;
  cancelEvidenceNavigation();
  evidenceNavigationError.value = "";
  activeWorkspace.value = workspace;
  if (followLayout.value && workspace === "content" && lastLearningWorkspace.value === "agent") lastLearningWorkspace.value = "tutor";
  if (isLearningWorkspace(workspace)) lastLearningWorkspace.value = workspace;
  reviewingEvidence.value = false;
  writeLocation(true);
}
function rememberLearningFocus(event: FocusEvent) {
  if (event.target instanceof HTMLElement && isLearningWorkspace(activeWorkspace.value)) lastLearningFocus = event.target;
}

async function switchWorkspace(workspace: CourseWorkspace) {
  const previous = activeWorkspace.value;
  const course = taskId.value;
  const narrow = narrowScreen.value && !classicLayout.value;
  if (narrow && previous === workspace && !evidenceNavigationError.value) return;
  if (narrow && workspace === "content" && isLearningWorkspace(previous)) {
    materialReturn = { workspace: previous, focus: lastLearningFocus, scroll: window.scrollY };
  }
  changeWorkspace(workspace);
  if (!narrow || followLayout.value) return;
  await nextTick();
  if (taskId.value !== course || activeWorkspace.value !== workspace) return;
  if (workspace === "content") {
    materialsTitle.value?.focus({ preventScroll: true });
    materialsRef.value?.scrollIntoView({ block: "start" });
  } else if (previous === "content") {
    const saved = materialReturn;
    materialReturn = undefined;
    if (saved?.workspace === workspace && saved.focus?.isConnected && learningRef.value?.contains(saved.focus)) {
      saved.focus.focus({ preventScroll: true });
      window.scrollTo({ top: saved.scroll });
    } else {
      learningRef.value?.focus({ preventScroll: true });
      learningRef.value?.scrollIntoView({ block: "start" });
    }
  }
}
watch([demo, notesAccountId], ([course, account]) => {
  if (!course || account === undefined) return;
  try {
    const key = courseNotesKey(account, course.taskId);
    if (localStorage.getItem(key) === null) localStorage.setItem(key, JSON.stringify(course.notes));
  } catch { /* Course notes report storage failures when opened. */ }
  if (!route.query.at && playbackPosition.value === undefined) applyLocation();
}, { flush: "sync" });

async function askAt(milliseconds: number) {
  changeWorkspace("tutor");
  await nextTick();
  tutorRef.value?.compose(`关于 ${formatMillisToClock(milliseconds).replace(/^00:/, "")} 这段：`);
}
async function lessonNote() {
  changeWorkspace("notes");
  await nextTick();
  notesRef.value?.focusEditor();
}
function lessonSeek(milliseconds: number) {
  cancelEvidenceNavigation();
  positionMs.value = milliseconds;
  seekRequest.value = { milliseconds, sequence: ++seekSequence, pause: true };
  writeLocation();
}
async function reviewLessonSource(milliseconds: number, context: EvidenceSeekContext) {
  if (!playbackUrl.value) return;
  const id = taskId.value;
  const request = ++evidenceRequest;
  verifyingEvidence.value = true;
  evidenceNavigationError.value = "";
  try {
    await evidenceSeekGuard.seek(id, context, () => {
      if (!hasTimedSource(milliseconds)) {
        evidenceNavigationError.value = "这段出处暂时无法回看。";
        return;
      }
      positionMs.value = milliseconds;
      seekRequest.value = { milliseconds, sequence: ++seekSequence, pause: true };
      writeLocation();
      if (narrowScreen.value) videoTarget.value?.scrollIntoView({ block: "nearest" });
    });
  } finally {
    if (request === evidenceRequest) verifyingEvidence.value = false;
  }
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
  if (lastLearningWorkspace.value === "notes") notesRef.value?.focusEditor();
  else input?.focus({ preventScroll: true });
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

async function seekTo(startTimeMillis: number, context?: EvidenceSeekContext, action: "source" | "note" | "video" = "source") {
  if (!validPosition(startTimeMillis)) return;
  const jumpToVideo = action === "video";
  const origin = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const originScroll = window.scrollY;
  const request = ++evidenceRequest;
  if (!jumpToVideo) {
    referenceMs.value = undefined;
    activeCitation.value = undefined;
  }
  evidenceNavigationError.value = "";
  verifyingEvidence.value = Boolean(context);
  let applied = false;
  try {
    await evidenceSeekGuard.seek(taskId.value, context, () => {
      if (jumpToVideo && !hasTimedSource(startTimeMillis)) {
        evidenceNavigationError.value = "此处的课程原文不可定位。当前输入和作答仍保留。";
        return;
      }
      if (jumpToVideo && !playbackUrl.value) return;
      if (context?.evidenceId && typeof context.revision === "number") {
        activeCitation.value = { kind: "evidence", milliseconds: startTimeMillis, evidenceId: context.evidenceId, revision: context.revision };
      }
      if (action !== "note") {
        if (!reviewingEvidence.value) {
          returnFocus = origin;
          returnScroll = originScroll;
        }
        applySeek(startTimeMillis, Boolean(context), jumpToVideo);
      }
      applied = true;
    });
  }
  finally {
    if (request === evidenceRequest) {
      verifyingEvidence.value = false;
      if (!applied && evidenceNavigationError.value) {
        reviewingEvidence.value = false;
        referenceMs.value = undefined;
        activeCitation.value = undefined;
      }
      // Wait until the verified reader is visible before measuring or moving it.
      if (applied) {
        if (action === "note") {
          await openCitationNote();
          return;
        }
        await nextTick();
        if (request === evidenceRequest) {
          if (jumpToVideo) {
            if (narrowScreen.value || classicLayout.value) (videoTarget.value ?? materialsRef.value)?.scrollIntoView({ block: "start" });
          } else if (!context && narrowScreen.value && !classicLayout.value) {
            materialsRef.value?.scrollIntoView({ block: "start" });
          } else if (reviewingEvidence.value && (classicLayout.value || narrowScreen.value)) {
            evidenceRef.value?.scrollIntoView({ block: "start" });
            if (!classicLayout.value) evidenceRef.value?.querySelector<HTMLElement>(".timeline-row[data-reference=true]")?.scrollIntoView({ block: "start" });
          }
          // The grid's bottom edge can push a sticky material rail under the app header.
          if (reviewingEvidence.value && !classicLayout.value && !narrowScreen.value && materialsRef.value && reviewTarget.value) {
            const bounds = reviewTarget.value.getBoundingClientRect();
            const stickyTop = parseFloat(getComputedStyle(materialsRef.value).top);
            if (bounds.top < stickyTop || bounds.bottom > window.innerHeight) layoutRef.value?.scrollIntoView({ block: "start" });
          }
          if (context && !jumpToVideo) evidenceRef.value?.querySelector<HTMLElement>(".timeline-row[data-reference=true]")?.focus({ preventScroll: true });
        }
      }
    }
  }
}
function jumpFromCitation() {
  const citation = videoCitation.value;
  if (citation && !verifyingEvidence.value) void seekTo(citation.milliseconds, citation, "video");
}

async function openCitationNote() {
  if (!activeCitation.value || notesAccountId.value === undefined) return;
  changeWorkspace("notes");
  await nextTick();
  learningRef.value?.scrollIntoView({ block: "start" });
  notesRef.value?.focusEditor();
}

async function jumpFromNote(anchor: NoteAnchor) {
  noteJumpError.value = "";
  const account = notesAccountId.value;
  if (account === undefined) return;
  const course = taskId.value;
  cancelEvidenceNavigation();
  const request = evidenceRequest;
  try {
    const detail = await fetchTaskDetail(course);
    if (request !== evidenceRequest || course !== taskId.value || account !== notesAccountId.value || !checkAuthSession()) return;
    if (detail.taskId !== course) throw new Error("Course source mismatch");
    const context = anchor.kind === "evidence" ? { evidenceId: anchor.evidenceId, revision: anchor.revision } : undefined;
    if (!followLayout.value) await seekTo(anchor.milliseconds, context);
    else if (context) await reviewLessonSource(anchor.milliseconds, context);
    else lessonSeek(anchor.milliseconds);
  } catch (error) {
    if (request !== evidenceRequest || course !== taskId.value || account !== notesAccountId.value) return;
    if (mayHaveLostCourseAccess(error)) blockCourse();
    else noteJumpError.value = "无法核实课程，暂不能定位。请重试。";
  }
}

function applySeek(startTimeMillis: number, reference = false, revealVideo = false) {
  referenceMs.value = reference ? startTimeMillis : undefined;
  positionMs.value = startTimeMillis;
  seekRequest.value = { milliseconds: startTimeMillis, sequence: ++seekSequence, pause: !classicLayout.value };
  readingView.value = "timeline";
  locateSequence.value++;
  // The explicit jump reveals the narrow-screen player inside the same review session.
  videoRequested.value = revealVideo || !reference;
  if (reference || activeWorkspace.value !== "content") {
    reviewingEvidence.value = true;
  }
  writeLocation();
}

function reconnect() {
  scopeRefresh.value++;
  cancelEvidenceNavigation();
  reviewingEvidence.value = false;
  evidenceNavigationError.value = "";
  if (!workspaceOpened.value) {
    void openCourse(taskId.value);
    return;
  }
  taskEventsStore.reconnect();
  void loadTaskDetail(taskId.value);
  void taskResultStore.load(taskId.value);
  void refreshTaskPlayback(taskId.value);
  void refreshTaskEmbeddedSubtitles(taskId.value);
}

function blockCourse() {
  if (courseBlocked.value) return;
  courseBlocked.value = true;
  workspaceOpened.value = false;
  forgetLastCourseLocation(authStore.user?.userId, taskId.value);
  cancelEvidenceNavigation();
  taskEventsStore.disconnect(); taskResultStore.clear();
  clearTaskDetail(); clearTaskPlayback(); clearTaskEmbeddedSubtitles();
  learningScope.value = null; agentScope.value = undefined; qaScope.value = undefined;
  learningTask.value = null; returnFocus = null; lastLearningFocus = null; materialReturn = undefined; reviewingEvidence.value = false;
}

function cancelEvidenceNavigation() {
  evidenceSeekGuard.cancel(); evidenceRequest++; verifyingEvidence.value = false; activeCitation.value = undefined;
}

function clearTaskDetail() {
  taskDetailRequestVersion.value += 1;
  taskDetail.value = null;
  taskDetailAccount.value = undefined;
  taskDetailError.value = "";
}

async function openCourse(id: string) {
  // The owner check completes before opening streams or loading subordinate course data.
  if (!await loadTaskDetail(id) || id !== taskId.value || courseBlocked.value) return;
  if (taskDetail.value?.status === "SUCCEEDED") completedResultReloadTaskId.value = id;
  if (taskDetail.value?.status !== "SUCCEEDED") taskEventsStore.connect(id);
  workspaceOpened.value = true;
  void taskResultStore.load(id);
  void refreshTaskPlayback(id);
  void refreshTaskEmbeddedSubtitles(id);
}

async function loadTaskDetail(currentTaskId: string): Promise<boolean> {
  const normalizedTaskId = currentTaskId.trim();
  if (!normalizedTaskId) { clearTaskDetail(); return false; }
  const version = taskDetailRequestVersion.value + 1;
  taskDetailRequestVersion.value = version;
  taskDetailError.value = "";
  try {
    const response = await fetchTaskDetail(normalizedTaskId);
    if (version !== taskDetailRequestVersion.value) return false;
    if (response.taskId !== normalizedTaskId) throw new Error("Course source mismatch");
    taskDetail.value = response;
    taskDetailAccount.value = authStore.user?.userId;
    return true;
  } catch (error) {
    if (version === taskDetailRequestVersion.value) {
      taskDetail.value = null;
      if (mayHaveLostCourseAccess(error)) blockCourse();
      else taskDetailError.value = toReadableTaskError(error);
    }
    return false;
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
    <div class="course-workspace-page__inner" :class="{ 'follow-lesson': followLayout }">
      <header class="lesson-heading" v-if="followLayout && !courseBlocked">
        <h1>{{ lessonName }}</h1>
        <div v-if="lessonProgress !== undefined" class="lesson-progress"><span>已学 {{ lessonProgress }}%</span><progress :value="lessonProgress" max="100" aria-label="学习进度" /></div>
      </header>
      <CourseWorkspaceHeader v-if="!followLayout || canCancelTask || canRetryTask"
        :compact="!classicLayout"
        :demo-mode="isDemoMode"
        :course-name="taskDetail?.courseName"
        v-show="!courseBlocked && !(reviewingEvidence && narrowScreen && !classicLayout)"
        :status="status"
        :learning-ready="learningReady"
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

      <CoursePreparationStatus
        v-if="!classicLayout && !courseBlocked && status && status !== 'SUCCEEDED'"
        v-show="!(reviewingEvidence && narrowScreen)"
        class="workspace-preparation"
        :task="task"
        :task-detail="taskDetail"
        :connection-status="taskEventsStore.connectionStatus"
        :connection-error="taskEventsStore.errorMessage"
      />
      <el-alert
        v-if="isDemoMode && classicLayout"
        class="demo-notice"
        :closable="false"
        title="当前使用本地演示数据，未调用外部 AI 服务。"
        type="info"
        show-icon
      />

      <div v-if="workspaceOpened && classicLayout" v-show="!(reviewingEvidence && narrowScreen && !classicLayout)" class="workspace-wayfinding" aria-label="学习工作区导航">
        <div class="workspace-wayfinding__actions">
          <button type="button" :aria-pressed="activeWorkspace === 'content'" @click="showMaterials">看视频与原文</button>
          <button type="button" :aria-pressed="activeWorkspace !== 'content'" @click="showLearning">{{ returnLabel }}</button>
        </div>
        <button type="button" class="layout-switch" @click="changeLayout">{{ classicLayout ? '连续工作区' : '经典布局' }}</button>
      </div>

      <div v-if="workspaceOpened && !classicLayout && !followLayout" v-show="!reviewingEvidence" ref="mobileNavTarget" class="mobile-workspace-nav-target" />

      <el-empty v-if="!hasTaskId" description="课程地址中缺少任务 ID" />
      <section v-else-if="courseBlocked" role="alert" class="course-unavailable">
        <h2>课程不可用或权限已变化</h2>
        <p>已停止显示此课程的缓存内容。请从课程列表重新打开；已保存记录仍由服务端权限决定是否可读取。</p>
        <RouterLink to="/tasks">返回我的课程</RouterLink>
      </section>
      <section v-else-if="!workspaceOpened" class="workspace-preparation course-unavailable">
        <div v-if="taskDetailError" role="alert">
          <p>{{ taskDetailError }}</p>
          <el-button @click="reconnect">重新读取课程</el-button>
        </div>
        <div v-else role="status">
          <p>正在读取课程…</p>
          <div v-if="followLayout" class="lesson-skeleton" aria-hidden="true">
            <div /><el-skeleton :rows="4" animated />
          </div><el-skeleton v-else :rows="4" animated aria-hidden="true" />
        </div>
      </section>
      <div v-else ref="layoutRef" class="course-layout" :class="{ 'course-layout--continuous': !classicLayout, 'course-layout--follow': followLayout,
        'show-lesson-content': activeWorkspace === 'content' || reviewingEvidence,
        'is-reading': !evidenceNavigationError && (activeWorkspace === 'content' || reviewingEvidence) }">
        <div ref="materialsRef" class="course-layout__media" role="region" aria-label="视频与课程材料" :tabindex="!classicLayout && !narrowScreen ? 0 : undefined">
          <div v-if="!classicLayout && !followLayout" class="materials-heading" v-show="!reviewingEvidence || !narrowScreen">
            <h2 ref="materialsTitle" tabindex="-1">课程材料</h2>
            <span v-if="playbackUrl && playbackPosition !== undefined">播放位置 <time>{{ formatMillisToClock(playbackPosition) }}</time></span>
          </div>
          <div class="lesson-video" :class="{ 'lesson-video--sticky': followLayout }">
          <div v-if="!followLayout" ref="reviewTarget" class="materials-review-target" />
          <div v-show="playerVisible" ref="videoTarget" class="materials-video-target">
          <CourseVideoAside
            :key="taskId"
            :compact="!classicLayout"
            :inactive="!playerVisible"
            :lesson="followLayout"
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
          </div>
          <CourseLessonNav v-if="followLayout && narrowScreen" mobile :active="activeWorkspace" @change="switchWorkspace" />
          </div>
          <CourseLessonReader v-if="followLayout" v-show="(!narrowScreen || activeWorkspace === 'content') && !reviewingEvidence"
            :key="taskId" :task-id="taskId" :result="result" :position="positionMs" :mobile="narrowScreen"
            :visible="!narrowScreen || activeWorkspace === 'content'" :loading="taskResultStore.loading"
            :error="taskResultStore.errorMessage" @seek="lessonSeek" @ask="askAt" @retry="taskResultStore.load(taskId)" />
          <div v-if="followLayout" ref="reviewTarget" class="materials-review-target" />
          <div ref="readingTarget" class="materials-reading-target" />
        </div>

        <section ref="learningRef" class="course-layout__content" aria-label="课程学习工作台" tabindex="-1" @focusin="rememberLearningFocus">
          <header v-if="followLayout && !narrowScreen" class="lesson-assistant-header">
            <div class="lesson-assistant-title">
              <span class="lesson-assistant-icon" aria-hidden="true">✧</span><h2>学习助手</h2>
            </div>
            <CourseLessonNav :active="learningWorkspace" @change="switchWorkspace" />
          </header>
          <Teleport v-if="!followLayout" :to="mobileNavTarget || 'body'" :disabled="classicLayout || !narrowScreen || !mobileNavTarget">
            <div class="learning-modes" :class="{ 'learning-modes--desktop': !classicLayout && !narrowScreen }">
              <h2 v-if="!classicLayout && !narrowScreen">学习工作台</h2>
              <CourseWorkspaceNav :active="!classicLayout && !narrowScreen ? learningWorkspace : activeWorkspace" :compact="!classicLayout" :materials="!classicLayout && narrowScreen" :resume-workspace="lastLearningWorkspace" @change="switchWorkspace" @resume="switchWorkspace(lastLearningWorkspace)" />
            </div>
          </Teleport>
          <div v-if="evidenceNavigationError" ref="evidenceErrorRef" class="evidence-navigation-error"><el-alert :closable="false" :title="evidenceNavigationError" type="warning" show-icon /></div>
          <el-alert v-if="!followLayout && taskResultStore.errorMessage" :closable="false" :title="taskResultStore.errorMessage" type="error" show-icon />
          <el-skeleton v-if="!followLayout && taskResultStore.loading && !result" :rows="6" animated />
          <!-- Move one reader between layouts; do not duplicate or remount its local state. -->
          <Teleport :to="readingTarget || 'body'" :disabled="classicLayout || !readingTarget">
            <div v-show="readerVisible && (!followLayout || reviewingEvidence)" ref="evidenceRef" class="evidence-reading">
              <Teleport :to="reviewTarget || 'body'" :disabled="classicLayout || narrowScreen || !reviewTarget">
                <div v-if="reviewingEvidence" v-show="readerVisible" class="evidence-reading__return">
                  <span class="evidence-reading__label"><small v-if="isDemoMode && narrowScreen" class="review-mode">本地演示 · 无外部 AI</small>
                    {{ learningTask && lastLearningWorkspace === 'agent' ? `复习第 ${learningTask.questionIndex + 1} 题：${learningTask.question}` : '回看课程原文，当前提问与草稿保留。' }}
                  </span>
                  <div class="evidence-reading__actions">
                    <button type="button" @click="returnToLearning">返回当前学习任务</button>
                    <button v-if="videoCitation" type="button" class="evidence-reading__jump" :aria-disabled="verifyingEvidence || undefined" @click="jumpFromCitation">跳到视频</button>
                    <button v-if="activeCitation && notesAccountId !== undefined" type="button" @click="openCitationNote">在 {{ formatMillisToClock(activeCitation.milliseconds) }} 写笔记</button>
                  </div>
                </div>
              </Teleport>
              <CourseContentPanel :reference-ms="reviewingEvidence ? referenceMs : undefined" :reference-jump-in-header="!!videoCitation" :compact="!classicLayout" ref="readerRef" :key="taskId" :task-id="taskId" :status="status" :result="result" :position-ms="positionMs" :view="readingView ?? (classicLayout ? undefined : 'timeline')" :visible="readerVisible" :locate-sequence="locateSequence" @update:view="changeReadingView" @seek="seekTo" />
            </div>
          </Teleport>
          <CourseScopePicker v-if="!followLayout || (!demo && (learningWorkspace === 'agent' || learningWorkspace === 'qa'))" :key="taskId" :compact="!classicLayout" v-show="learningWorkspace === 'agent' || learningWorkspace === 'qa'" @access-failure="loadTaskDetail(taskId)" v-model="learningScope" :task-id="taskId" :refresh-key="scopeRefresh" :frozen-scope="learningWorkspace === 'agent' ? agentScope : qaScope" @seek="seekTo" />
          <CourseNotesPanel
            v-if="notesAccountId !== undefined"
            v-show="learningWorkspace === 'notes'"
            :key="`${notesAccountId}:${taskId}`"
            ref="notesRef"
            :user-id="notesAccountId"
            :task-id="taskId"
            :playback-ms="playbackPosition"
            :citation="noteCitation"
            :jump-error="noteJumpError"
            @clear-citation="noteCitation = undefined"
            @jump="jumpFromNote"
          />
          <template v-else-if="learningWorkspace === 'notes'">
            <p v-if="taskDetailError" role="alert">
              {{ taskDetailError }} <el-button @click="loadTaskDetail(taskId)">重新读取课程</el-button>
            </p>
            <p v-else role="status">正在确认当前账户和课程权限…</p>
          </template>
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
            <CourseTutorPanel v-else-if="learningWorkspace === 'tutor'" ref="tutorRef" :task-id="taskId"
              :lesson="followLayout" :suggestions-visible="!narrowScreen" :course-title="lessonName"
               :demo-course="demo" :can-note="notesAccountId !== undefined"
              @note="(milliseconds, context) => seekTo(milliseconds, context, 'note')"
              @seek="seekTo" @replay="reviewLessonSource" @practice="switchWorkspace('agent')"
              @lesson-note="lessonNote" @course-qa="switchWorkspace('qa')" @access-failure="loadTaskDetail(taskId)" />
            <CourseFlashcardsPanel v-else-if="learningWorkspace === 'flashcards'" :task-id="taskId" @seek="seekTo" @access-failure="loadTaskDetail(taskId)" />
            <CourseStudyPanel v-else-if="learningWorkspace === 'study'" :task-id="taskId" :status="status" :result="result" @seek="seekTo" />
            <CourseAgentPanel :lesson="followLayout" :demo-practice="Boolean(demo)" :example-position="demo?.positionMs" :compact="!classicLayout" @position="learningTask = $event" @access-failure="loadTaskDetail(taskId)" :learning-scope="learningScope" @frozen-scope="agentScope = $event" v-else-if="learningWorkspace === 'agent'" :task-id="taskId" :status="status" :learning-ready="learningReady" @seek="(ms, context) => followLayout ? reviewLessonSource(ms, context) : seekTo(ms, context)" @navigate="changeWorkspace" />
            <CourseQaPanel @access-failure="loadTaskDetail(taskId)" :learning-scope="learningScope" @frozen-scope="qaScope = $event" v-else-if="learningWorkspace === 'qa'" :task-id="taskId" @seek="seekTo" />
            <CourseFilesPanel v-else-if="learningWorkspace === 'files'" :task-id="taskId" :status="task?.status" :artifacts="result?.artifacts ?? []" :artifacts-status="result?.artifactsStatus" />
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
      <details v-if="workspaceOpened && followLayout" class="lesson-more">
        <summary>更多课程工具</summary>
        <CourseWorkspaceNav :active="learningWorkspace" @change="switchWorkspace" />
        <button type="button" class="layout-switch" @click="reconnect">重新加载课程</button>
        <button type="button" class="layout-switch" @click="changeLayout">经典布局</button>
      </details>
      <details v-if="workspaceOpened && !followLayout" v-show="!(reviewingEvidence && narrowScreen && !classicLayout)" class="workspace-recovery">
        <summary>保存、恢复与课程记录</summary>
        <p>服务端保存学习会话、执行、作答版本、反馈与核对意见。刷新后读取最近的已保存学习记录。</p>
        <p>同一浏览器可从「我的课程」恢复上次的视图和暂停位置。退出登录会清除这些位置。网址还可恢复课程布局。</p>
        <p>未提交的问题、目标、作答和核对文字仅留在当前页面。个人笔记保存在此浏览器和当前账户。</p>
        <CourseModelUsagePanel v-if="task" :key="taskId" :task-id="taskId" />
      </details>
    </div>
  </main>
</template>

<style scoped>
.course-workspace-page { min-height: calc(100vh - var(--header-height)); }
.course-workspace-page__inner { width: min(var(--content-width), calc(100% - 64px)); margin-inline: auto; padding-block: 24px 64px; }
.course-layout { display: grid; grid-template-columns: minmax(330px, 420px) minmax(0, 1fr); align-items: start; gap: 24px; margin-top: 20px; scroll-margin-top: calc(var(--header-height) + 16px); }
.course-layout__media, .course-layout__content, .evidence-reading { min-width: 0; }
.course-layout__media { position: sticky; top: calc(var(--header-height) + 16px); }
.course-layout__content { display: grid; gap: 16px; scroll-margin-top: calc(var(--header-height) + 62px); }
.course-layout__media:focus-visible { outline: 2px solid var(--color-brand); outline-offset: 3px; }

.course-layout--continuous { grid-template-columns: minmax(0, 14fr) minmax(0, 11fr); gap: 16px; }
.course-layout--continuous .course-layout__media, .course-layout--continuous .course-layout__content {
  padding: 16px; border: 1px solid var(--color-border-strong); border-radius: var(--radius-lg); background: var(--color-surface);
}
.course-layout--continuous .course-layout__media { display: grid; gap: 10px; background: var(--color-surface-subtle); }
.materials-heading { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 4px 16px; }
.materials-heading h2, .learning-modes h2 { margin: 0; color: var(--color-ink); font-size: 17px; font-weight: 740; }
.materials-heading span { color: var(--color-ink-soft); font-size: 13px; }
.materials-heading time { margin-inline-start: 4px; color: var(--color-ink); font-variant-numeric: tabular-nums; }
.materials-video-target { min-width: 0; scroll-margin-top: calc(var(--header-height) + 8px); }
.materials-reading-target { min-width: 0; padding: 12px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); }
.course-layout--continuous .course-layout__content { gap: 16px; }
.learning-modes--desktop { display: grid; gap: 8px; margin: -16px -16px 0; padding: 14px 16px 10px; border-bottom: 1px solid var(--color-border-strong); border-radius: var(--radius-lg) var(--radius-lg) 0 0; background: var(--color-brand-soft); }
.course-layout--continuous :deep(.course-video-player) { max-height: 31dvh; object-fit: contain; }
.course-layout--continuous :deep(.video-card) { gap: 6px; }
.course-layout--continuous :deep(.content-panel) { padding: 0; border: 0; box-shadow: none; gap: 12px; }
.course-layout--continuous :deep(.content-panel > header) { position: absolute; clip-path: inset(50%); height: 1px; overflow: hidden; }
.course-layout--continuous .course-layout__media { --reader-height: clamp(124px, calc(60dvh - 270px), 360px); }
.course-layout--continuous .course-layout__media:has(.materials-review-target:not(:empty)) { --reader-height: clamp(124px, calc(60dvh - 345px), 300px); }
.course-layout--continuous :deep(.timeline-list), .course-layout--continuous :deep(.reading-copy), .course-layout--continuous :deep(.course-chapters-panel) { max-height: var(--reader-height, 35dvh); overflow-y: auto; overscroll-behavior: contain; }
.course-layout--continuous :deep(.agent-panel), .course-layout--continuous :deep(.qa-panel), .course-layout--continuous :deep(.tutor), .course-layout--continuous :deep(.flashcards) { padding: 0; border: 0; box-shadow: none; }
.course-layout--continuous :deep(.scope-picker) { margin: 0; padding: 0 0 10px; background: transparent; border: 0; border-bottom: 1px solid var(--color-border); border-radius: 0; }
.course-layout--continuous :deep(.agent-panel > header h2), .course-layout--continuous :deep(.qa-panel h2) { font-size: 22px; }
.course-layout--continuous :deep(.question-text) { font-size: 17px; line-height: 1.7; }
.course-layout--continuous :deep(.practice-question.is-current) { border-color: var(--color-border-strong); }
.course-layout--continuous :deep(.el-textarea__inner) { font-size: 16px; line-height: 1.65; }
.course-layout--continuous :deep(.study-artifact) { margin-top: 12px; gap: 12px; }

.materials-reading-target:empty, .materials-review-target:empty, .mobile-workspace-nav-target { display: none; }
.evidence-reading, .evidence-navigation-error, .course-layout__media { scroll-margin-top: calc(var(--header-height) + 62px); }
.evidence-reading__return { display: grid; gap: 6px; padding: 10px; border: 1px solid var(--color-border-strong); border-radius: var(--radius-md); background: var(--color-evidence-surface); color: var(--color-ink); font-size: 14px; }
.evidence-reading > .evidence-reading__return { margin-bottom: 10px; }
.evidence-reading__label { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; overflow-wrap: anywhere; }
.evidence-reading__actions, .workspace-wayfinding, .workspace-wayfinding__actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.evidence-reading__return button, .workspace-wayfinding button, .layout-switch {
  border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 8px 12px; background: var(--color-surface); color: var(--color-brand-strong); cursor: pointer;
}
.evidence-reading__actions .evidence-reading__jump { color: white; border-color: var(--color-brand); background: var(--color-brand); }
.review-mode { display: inline-block; padding: 1px 5px; margin-inline-end: 4px; border-radius: var(--radius-sm); background: var(--color-brand-soft); color: var(--color-brand-strong); }
.workspace-wayfinding { position: sticky; top: var(--header-height); z-index: 5; justify-content: space-between; padding-block: 8px; background: var(--color-canvas); border-bottom: 1px solid var(--color-border); }
.workspace-wayfinding [aria-pressed=true] { background: var(--color-brand-soft); border-color: var(--color-brand); }
.workspace-recovery, .course-unavailable { margin-top: 20px; padding: 16px; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); line-height: 1.65; }
.workspace-recovery summary { cursor: pointer; font-weight: 650; }
.demo-notice { margin-block: 8px; }
.workspace-preparation { margin-top: 12px; }

@media (max-width: 1024px) {
  .course-workspace-page__inner { width: min(760px, calc(100% - 32px)); }
  .course-layout, .course-layout--continuous { grid-template-columns: 1fr; }
  .course-layout__media, .course-layout--continuous .course-layout__media { position: static; max-height: none; overflow: visible; }
  .course-layout--continuous:not(.is-reading) .course-layout__media, .course-layout--continuous.is-reading .course-layout__content { display: none; }
  .course-layout--continuous .course-layout__media, .course-layout--continuous .course-layout__content { padding: 14px; }
  .course-layout--continuous .course-layout__media, .course-layout--continuous .course-layout__content { scroll-margin-top: calc(var(--header-height) + 124px); }
  .course-layout--continuous :deep(.course-video-player) { max-height: 42vh; }
  .course-layout--continuous :deep(.timeline-list) { max-height: 42dvh; }
  .course-layout--continuous :deep(.reading-copy), .course-layout--continuous :deep(.course-chapters-panel) { max-height: none; }
  .materials-reading-target { padding: 0; border: 0; background: transparent; }
  .mobile-workspace-nav-target { display: block; position: sticky; top: var(--header-height); z-index: 10; padding-block: 8px; background: var(--color-canvas); }
  .course-layout--continuous { margin-top: 8px; }
  .course-workspace-page :deep(button) { min-height: 44px; }
  .is-mobile-evidence .course-layout { margin-top: 0; }
  .is-mobile-evidence .course-layout__media { scroll-margin-top: var(--header-height); background: var(--color-surface); }
  .is-mobile-evidence .evidence-reading__return { position: sticky; top: var(--header-height); z-index: 6; }
  .is-mobile-evidence :deep(.timeline-list) { max-height: none; overflow: visible; }
  .is-mobile-evidence :deep(.timeline-row) { scroll-margin-top: calc(var(--header-height) + 152px); }
}
@media (max-width: 520px) {
  .course-workspace-page__inner { padding-top: 12px; }
  .course-layout--continuous .course-layout__media, .course-layout--continuous .course-layout__content { padding: 12px; }
  .is-mobile-evidence .evidence-reading:has(.evidence-reading__jump) :deep(.timeline-row) { scroll-margin-top: calc(var(--header-height) + 204px); }
}

.follow-lesson { width: min(var(--content-width), calc(100% - 96px)); padding-block: 23px 48px; }
.lesson-heading { display: flex; align-items: end; justify-content: space-between; gap: 12px; margin-bottom: 20px; }
.lesson-heading h1 { font-size: clamp(24px, 2.35vw, 36px); font-weight: 800; letter-spacing: -.03em; line-height: 1.25; margin: 0; }
.lesson-progress { display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 650; white-space: nowrap; color: var(--color-ink-soft); }
.lesson-progress progress { width: 80px; height: 5px; appearance: none; border: 0; border-radius: 10px; overflow: hidden; background: var(--color-border); accent-color: var(--color-brand); }
.lesson-progress progress::-webkit-progress-bar { background: var(--color-border); }
.lesson-progress progress::-webkit-progress-value { background: var(--color-brand); }
.lesson-skeleton { display: grid; grid-template-columns: 1.57fr 1fr; gap: 26px; margin-top: 12px; }
.lesson-skeleton > div:first-child { aspect-ratio: 16 / 9; border-radius: 18px; background: var(--color-surface-subtle); }
.course-layout--follow { grid-template-columns: minmax(0, 1.57fr) minmax(0, 1fr); gap: 26px; margin-top: 0; }
.course-layout--follow .course-layout__media { display: block; border: 0; padding: 0; background: transparent; position: static; }
.course-layout--follow .course-layout__content { position: relative; align-content: start; gap: 12px; padding: 18px 22px; min-height: min(708px, 85vh); border-color: var(--color-border); border-radius: 17px; box-shadow: var(--shadow-low); }
.course-layout--follow :deep(.course-video-player) { width: 100%; aspect-ratio: 16 / 9; max-height: none; }
.course-layout--follow :deep(.video-card) { padding: 0; border: 0; background: none; box-shadow: none; }
.course-layout--follow :deep(.video-card__player-shell) { border-radius: 18px; }
.course-layout--follow .materials-reading-target { padding: 0; border: 0; background: transparent; }
.course-layout--follow .materials-reading-target:has(.evidence-reading[style*="display: none"]) { display: none; }
.course-layout--follow :deep(.scope-picker) { margin: 0; }
.lesson-assistant-header { margin: 0 -22px; padding: 0 22px; }
.lesson-assistant-title { display: flex; align-items: center; gap: 11px; min-height: 53px; margin-bottom: 5px; align-items: start; }
.lesson-assistant-title h2 { margin: 0; font-size: 21px; font-weight: 750; }
.lesson-assistant-icon { border-radius: 12px; padding: 6px 9px; font-size: 23px; background: var(--color-brand-soft); color: var(--color-brand); line-height: 1.2; }
.lesson-more { color: var(--color-ink-soft); margin-top: 20px; font-size: 13px; }
.lesson-more summary { cursor: pointer; width: fit-content; }
.lesson-more[open] > :deep(nav) { margin: 8px 0; }
@media (max-width: 1024px) {
  .follow-lesson { width: min(720px, calc(100% - 28px)); padding-top: 14px; }
  .lesson-heading { align-items: center; margin-bottom: 12px; }
  .lesson-heading h1 { font-size: clamp(19px, 5vw, 29px); }
  .lesson-progress { font-size: 12px; }
  .lesson-progress progress { display: none; }
  .lesson-skeleton, .course-layout--follow { display: block; }
  .lesson-video--sticky { position: sticky; top: var(--lesson-mobile-header-height); z-index: 9; background: var(--color-canvas); }
  .course-layout--follow:not(.is-reading) .course-layout__media,
  .course-layout--follow.is-reading .course-layout__content { display: block; }
  .course-layout--follow.show-lesson-content .course-layout__content:not(:has(.evidence-navigation-error)) { display: none; }
  .course-layout--follow .course-layout__content { min-height: 0; border: 0; border-radius: 0; padding: 14px 0 0; background: transparent; box-shadow: none; }
  .course-layout--follow .course-layout__media, .course-layout--follow .course-layout__content { scroll-margin-top: var(--header-height); }
  .course-layout--follow :deep(.video-card__player-shell) { border-radius: 10px; }
  .course-layout--follow .course-layout__media { display: contents !important; }
  .course-layout--follow :deep(.lesson-controls button) { min-height: 27px; }
  .course-layout--follow :deep(.timestamp), .course-layout--follow :deep(.ask), .course-layout--follow :deep(.language button) { min-height: 28px; }
  .lesson-more { margin-top: 34px; }
}
</style>
