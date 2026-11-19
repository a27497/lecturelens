<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  batchDeleteTasks,
  fetchTasks,
  retryTask,
  toReadableBatchDeleteError,
  toReadableTaskError,
} from "../api/task";
import { loadRound3Course, round3Course, round3Enabled } from "../api/round3Demo";
import EmptyState from "../components/ui/EmptyState.vue";
import PageHeading from "../components/ui/PageHeading.vue";
import SectionPanel from "../components/ui/SectionPanel.vue";
import StatusBadge from "../components/ui/StatusBadge.vue";
import type { TaskSummaryResponse } from "../types/task";
import { lastCourseLocationQuery, readLastCourseLocation } from "../components/task-detail/lastCourseLocation";
import type { LastCourseLocation } from "../components/task-detail/lastCourseLocation";
import { courseLearnable, courseStageText, workspaceLabel } from "../components/task-detail/workspace";
import { useAuthStore } from "../stores/auth";
import { toUserFriendlyError } from "../utils/errorMessage";
import { formatApiTimestamp, formatMillisToClock, parseApiTimestamp } from "../utils/time";
import {
  getTaskStatusGroup,
  isRetryableTaskStatus,
  isRunningTaskStatus,
  shortenTaskId,
  type TaskStatusGroup,
} from "../utils/taskStatus";

interface TaskFilterOption {
  label: string;
  value: TaskStatusGroup;
}

const TASK_FILTERS: TaskFilterOption[] = [
  { label: "全部", value: "ALL" },
  { label: "处理中", value: "RUNNING" },
  { label: "材料就绪", value: "SUCCEEDED" },
  { label: "失败", value: "FAILED" },
  { label: "已取消", value: "CANCELED" },
];

const AUTO_REFRESH_INTERVAL_MS = 5000;
const MAX_TASK_PAGE_SIZE = 100;

const router = useRouter();
const authStore = useAuthStore();
const loading = ref(false);
const refreshing = ref(false);
const openingTaskId = ref("");
const failedOpeningTaskId = ref("");
const retryingTaskId = ref("");
const errorMessage = ref("");
const loaded = ref(false);
const tasks = ref<TaskSummaryResponse[]>([]);
const savedLocations = shallowRef(new Map<string, LastCourseLocation>());
const total = ref(0);
const page = ref(1);
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / MAX_TASK_PAGE_SIZE)));
const activeGroup = ref<TaskStatusGroup>("ALL");
const batchMode = ref(false);
const deleting = ref(false);
const deleteConfirmationOpen = ref(false);
const selectedTaskIds = ref<Set<string>>(new Set());
let autoRefreshTimer: number | undefined;
let componentActive = false;
let latestTaskRequestVersion = 0;
let activeLoadingRequestVersion = 0;
let activeRefreshingRequestVersion = 0;

const filteredTasks = computed(() => {
  if (activeGroup.value === "ALL") {
    return tasks.value;
  }
  return tasks.value.filter((task) => getTaskStatusGroup(task.status) === activeGroup.value);
});
const courseCards = computed(() => filteredTasks.value.map(task => ({
  task,
  title: courseTitle(task),
  location: savedLocations.value.get(task.taskId) ?? null,
  demo: round3Course.value?.taskId === task.taskId ? round3Course.value : undefined,
})));

const emptyLibrary = computed(() => loaded.value && !errorMessage.value && total.value === 0);
const featuredCourse = computed(() => {
  if (page.value !== 1 || batchMode.value || activeGroup.value !== "ALL") return undefined;
  const resumed = courseCards.value.reduce<(typeof courseCards.value)[number] | undefined>((latest, card) => {
    if (!card.location) return latest;
    return !latest || (card.location.visitedAt ?? 0) > (latest.location?.visitedAt ?? 0) ? card : latest;
  }, undefined);
  return resumed ?? courseCards.value.find(({ task }) => courseLearnable(task.status, task.learningReady));
});
const displayedCards = computed(() => {
  const featured = featuredCourse.value;
  return featured ? [featured, ...courseCards.value.filter(card => card !== featured)] : courseCards.value;
});

const hasRunningTasks = computed(() => tasks.value.some((task) => isRunningTaskStatus(task.status)));
const selectedCount = computed(() => selectedTaskIds.value.size);
const selectableFilteredTasks = computed(() => filteredTasks.value.filter(isTaskDeletable));
const allSelectableSelected = computed(() =>
  selectableFilteredTasks.value.length > 0
  && selectableFilteredTasks.value.every((task) => selectedTaskIds.value.has(task.taskId)),
);

const filterCounts = computed<Record<TaskStatusGroup, number>>(() => {
  const counts: Record<TaskStatusGroup, number> = {
    ALL: tasks.value.length,
    RUNNING: 0,
    SUCCEEDED: 0,
    FAILED: 0,
    CANCELED: 0,
  };
  for (const task of tasks.value) {
    const group = getTaskStatusGroup(task.status);
    if (group !== "ALL") {
      counts[group] += 1;
    }
  }
  return counts;
});

onMounted(() => {
  componentActive = true;
  window.addEventListener("storage", refreshSavedLocations);
  window.addEventListener("focus", refreshSavedLocations);
  void loadTasks();
  if (round3Enabled) void loadRound3Course().catch(() => {});
});

onBeforeUnmount(() => {
  componentActive = false;
  window.removeEventListener("storage", refreshSavedLocations);
  window.removeEventListener("focus", refreshSavedLocations);
  latestTaskRequestVersion += 1;
  stopAutoRefresh();
});

watch([tasks, () => authStore.user?.userId], refreshSavedLocations);

watch(hasRunningTasks, (nextValue) => {
  if (nextValue) {
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
});

watch(activeGroup, () => {
  selectedTaskIds.value = new Set();
});

async function loadTasks(options: { silent?: boolean } = {}) {
  const requestVersion = ++latestTaskRequestVersion;
  if (options.silent) {
    activeRefreshingRequestVersion = requestVersion;
    refreshing.value = true;
  } else {
    activeLoadingRequestVersion = requestVersion;
    loading.value = true;
  }
  errorMessage.value = "";
  try {
    const result = await fetchTasks(page.value, MAX_TASK_PAGE_SIZE, "ALL");
    if (!componentActive || requestVersion !== latestTaskRequestVersion) {
      return;
    }
    total.value = result.total;
    if (page.value > pageCount.value) {
      page.value = pageCount.value;
      await loadTasks(options);
      return;
    }
    tasks.value = result.items;
    loaded.value = true;
    reconcileSelection();
  } catch (error) {
    if (componentActive && requestVersion === latestTaskRequestVersion) {
      errorMessage.value = toReadableTaskError(error);
    }
  } finally {
    if (options.silent && activeRefreshingRequestVersion === requestVersion) {
      refreshing.value = false;
    } else if (!options.silent && activeLoadingRequestVersion === requestVersion) {
      loading.value = false;
    }
  }
}

function changePage(next: number) {
  if (next < 1 || next > pageCount.value || deleting.value || loading.value) return;
  page.value = next;
  selectedTaskIds.value = new Set();
  tasks.value = [];
  void loadTasks();
}

function isTaskDeletable(task: TaskSummaryResponse): boolean {
  return ["SUCCEEDED", "FAILED", "CANCELED"].includes(task.status);
}

function reconcileSelection() {
  if (!batchMode.value || selectedTaskIds.value.size === 0) {
    return;
  }
  const selectableVisibleIds = new Set(selectableFilteredTasks.value.map((task) => task.taskId));
  selectedTaskIds.value = new Set(
    [...selectedTaskIds.value].filter((taskId) => selectableVisibleIds.has(taskId)),
  );
}

function enterBatchMode() {
  batchMode.value = true;
}

function exitBatchMode() {
  if (deleting.value) {
    return;
  }
  batchMode.value = false;
  selectedTaskIds.value = new Set();
}

function toggleTaskSelection(task: TaskSummaryResponse, selected: boolean) {
  if (deleting.value || !isTaskDeletable(task)) {
    return;
  }
  const next = new Set(selectedTaskIds.value);
  if (selected) {
    if (next.size >= MAX_TASK_PAGE_SIZE) {
      return;
    }
    next.add(task.taskId);
  } else {
    next.delete(task.taskId);
  }
  selectedTaskIds.value = next;
}

function selectAllCurrent() {
  if (deleting.value) {
    return;
  }
  const next = new Set(selectedTaskIds.value);
  if (allSelectableSelected.value) {
    for (const task of selectableFilteredTasks.value) {
      next.delete(task.taskId);
    }
    selectedTaskIds.value = next;
    return;
  }
  for (const task of selectableFilteredTasks.value) {
    if (next.size >= MAX_TASK_PAGE_SIZE) {
      break;
    }
    next.add(task.taskId);
  }
  selectedTaskIds.value = next;
}

async function confirmBatchDelete() {
  if (deleting.value || deleteConfirmationOpen.value || selectedTaskIds.value.size === 0) {
    return;
  }
  const taskIds = [...selectedTaskIds.value];
  deleteConfirmationOpen.value = true;
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${taskIds.length} 门课程吗？删除后将不再显示在“我的课程”中。`,
      "删除课程",
      {
        confirmButtonText: "确认删除",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
  } catch {
    return;
  } finally {
    deleteConfirmationOpen.value = false;
  }

  if (deleting.value || !componentActive) {
    return;
  }
  deleting.value = true;
  try {
    const response = await batchDeleteTasks([...new Set(taskIds)]);
    if (!componentActive) {
      return;
    }
    ElMessage.success(
      response.deletedCount === 0
        ? "所选课程已从列表中删除"
        : `已删除 ${response.deletedCount} 门课程`,
    );
    selectedTaskIds.value = new Set();
    batchMode.value = false;
    await loadTasks();
  } catch (error) {
    if (componentActive) {
      ElMessage.error(toReadableBatchDeleteError(error));
    }
  } finally {
    deleting.value = false;
  }
}

function startAutoRefresh() {
  if (autoRefreshTimer !== undefined) {
    return;
  }
  autoRefreshTimer = window.setInterval(() => {
    if (!deleting.value && !loading.value && !refreshing.value) {
      void loadTasks({ silent: true });
    }
  }, AUTO_REFRESH_INTERVAL_MS);
}

function stopAutoRefresh() {
  if (autoRefreshTimer === undefined) {
    return;
  }
  window.clearInterval(autoRefreshTimer);
  autoRefreshTimer = undefined;
}

const lessonClock = (time: number) => formatMillisToClock(time).replace(/^00:/, "");

function lastLocationText(location: LastCourseLocation): string {
  return `上次停在：${workspaceLabel(location.view)} · 视频 ${formatMillisToClock(location.at)}`;
}

function refreshSavedLocations() {
  const userId = authStore.user?.userId;
  const locations = new Map<string, LastCourseLocation>();
  for (const task of tasks.value) {
    if (!courseLearnable(task.status, task.learningReady)) continue;
    const location = readLastCourseLocation(userId, task.taskId);
    if (location) locations.set(task.taskId, location);
  }
  savedLocations.value = locations;
}

async function openTask(task: TaskSummaryResponse) {
  if (openingTaskId.value) return;
  openingTaskId.value = task.taskId;
  failedOpeningTaskId.value = "";
  try {
    const learnable = courseLearnable(task.status, task.learningReady);
    const user = learnable ? await authStore.loadCurrentUser().catch(() => null) : null;
    if (!componentActive) return;
    if (learnable && !user) {
      // Entering with default coordinates could overwrite a saved location when identity arrives.
      failedOpeningTaskId.value = task.taskId;
      return;
    }
    // Other tabs can save a new location after this card has rendered.
    const location = readLastCourseLocation(user?.userId, task.taskId);
    const course = round3Course.value;
    const query = location ? lastCourseLocationQuery(location)
      : course?.taskId === task.taskId ? { at: String(course.positionMs) } : undefined;
    await router.push({ path: `/tasks/${encodeURIComponent(task.taskId)}`, query });
  } finally {
    openingTaskId.value = "";
  }
}

async function confirmRetryTask(task: TaskSummaryResponse) {
  if (!isRetryableTaskStatus(task.status) || retryingTaskId.value) {
    return;
  }
  try {
    await ElMessageBox.confirm(
      "确定要重新处理这个课程吗？系统会基于原视频创建新的处理任务，原失败记录会保留。",
      "重新处理课程",
      {
        confirmButtonText: "重新处理",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
  } catch {
    return;
  }

  retryingTaskId.value = task.taskId;
  try {
    const response = await retryTask(task.taskId);
    ElMessage.success("已创建新的处理任务，正在打开详情。");
    await router.push(`/tasks/${encodeURIComponent(response.newTaskId)}`);
  } catch (error) {
    ElMessage.error(toReadableTaskError(error));
  } finally {
    retryingTaskId.value = "";
  }
}

async function copyTaskId(taskId: string) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(taskId);
    } else {
      fallbackCopyText(taskId);
    }
    ElMessage.success("任务 ID 已复制");
  } catch {
    try {
      fallbackCopyText(taskId);
      ElMessage.success("任务 ID 已复制");
    } catch {
      ElMessage.error("复制失败，请手动选择任务 ID 复制");
    }
  }
}

function fallbackCopyText(text: string) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

function primaryActionText(task: TaskSummaryResponse, location: LastCourseLocation | null): string {
  if (courseLearnable(task.status, task.learningReady)) {
    return location ? "继续学习" : "进入学习";
  }
  if (isRunningTaskStatus(task.status)) {
    return "查看进度";
  }
  return "查看详情";
}

function courseStatusLabel(task: TaskSummaryResponse): string {
  const status = String(task.status || "").toUpperCase();
  if (status === "SUCCEEDED") {
    return "材料已就绪";
  }
  if (courseLearnable(task.status, task.learningReady)) return "字幕可学习";
  if (status === "FAILED") {
    return "处理失败";
  }
  if (status === "CANCELED" || status === "CANCELLED") {
    return "已取消";
  }
  if (status === "CREATED" || status === "PENDING" || status === "QUEUED") {
    return "等待处理";
  }
  return "处理中";
}

function courseStatusTone(task: TaskSummaryResponse): "neutral" | "progress" | "success" | "warning" | "danger" {
  const status = String(task.status || "").toUpperCase();
  if (status === "SUCCEEDED") {
    return "success";
  }
  if (status === "FAILED") {
    return "danger";
  }
  if (status === "RETRYING" || status === "CANCEL_REQUESTED") {
    return "warning";
  }
  return isRunningTaskStatus(status) ? "progress" : "neutral";
}

function courseTitle(task: TaskSummaryResponse): string {
  if (task.courseName?.trim()) {
    return task.courseName.trim();
  }
  if (!task.createdAt) {
    return "课程视频";
  }
  const date = parseApiTimestamp(task.createdAt);
  if (!date) {
    return "课程视频";
  }
  return `课程视频 · ${date.toLocaleDateString("zh-CN", { month: "long", day: "numeric" })}`;
}

function readableFailure(task: TaskSummaryResponse): string {
  if (task.status !== "FAILED") {
    return "";
  }
  const fallback = "课程处理失败，请查看错误信息或重新处理。";
  const mapped = toUserFriendlyError(
    {
      response: {
        data: {
          code: task.errorCode,
          message: task.errorMessage,
        },
      },
    },
    fallback,
  );
  if (mapped !== fallback) {
    return mapped;
  }
  const message = task.errorMessage || "";
  if (/ASR|transcrib|SiliconFlow|audio/i.test(message)) {
    return "语音转文字服务临时异常，请稍后重试。";
  }
  if (/401|auth|provider|LLM|OpenAI|translation/i.test(message)) {
    return "翻译服务认证失败，请检查服务器模型配置。";
  }
  if (/RocketMQ|message queue|MQ|消息队列/i.test(message)) {
    return "消息队列配置异常，请联系管理员。";
  }
  return fallback;
}

function formatTime(value: string | null): string {
  return formatApiTimestamp(value);
}
</script>

<template>
  <main class="task-list-page page-container">
    <PageHeading
      title="我的课程"
      description="看课时遇到疑问，就从那一段问起。"
    >
      <template v-if="!emptyLibrary" #actions>
        <RouterLink class="upload-link" to="/upload"><span aria-hidden="true">＋</span> 上传视频</RouterLink>
      </template>
    </PageHeading>

    <SectionPanel class="course-library">
      <div v-if="!emptyLibrary && (loaded || errorMessage)" class="task-list-toolbar">
        <el-radio-group v-model="activeGroup" :disabled="deleting" class="task-list-toolbar__filters" aria-label="按课程状态筛选">
          <el-radio-button v-for="filter in TASK_FILTERS" :key="filter.value" :value="filter.value">
            {{ filter.label }} {{ filterCounts[filter.value] }}
          </el-radio-button>
        </el-radio-group>
        <div class="task-list-toolbar__actions">
          <el-button text :loading="loading || refreshing" :disabled="deleting" @click="loadTasks()">刷新</el-button>
          <el-button v-if="batchMode" :disabled="deleting" @click="exitBatchMode">退出批量管理</el-button>
          <el-button v-else @click="enterBatchMode">批量管理</el-button>
        </div>
      </div>

      <div v-if="batchMode && !emptyLibrary" class="batch-management" aria-label="课程批量管理工具栏">
        <strong>已选择 {{ selectedCount }} 项</strong>
        <div class="batch-management__actions">
          <el-button :disabled="deleting || selectableFilteredTasks.length === 0" @click="selectAllCurrent">
            {{ allSelectableSelected ? "取消全选" : "全选当前列表" }}
          </el-button>
          <el-button type="danger" :loading="deleting" :disabled="deleting || deleteConfirmationOpen || selectedCount === 0" @click="confirmBatchDelete">
            删除所选
          </el-button>
        </div>
      </div>

      <p v-if="hasRunningTasks" class="auto-refresh-note">课程准备中 · 自动更新</p>

      <el-alert
        v-if="errorMessage"
        :closable="false"
        :title="errorMessage"
        show-icon
        type="error"
      />

      <div v-if="loading && tasks.length === 0" role="status">
        <span>正在加载课程…</span>
        <el-skeleton :rows="4" animated aria-hidden="true" />
      </div>
      <EmptyState
        v-else-if="loaded && !errorMessage && filteredTasks.length === 0"
        :class="{ 'library-empty': emptyLibrary }"
        :title="emptyLibrary ? '还没有课程视频' : '当前列表没有符合条件的课程'"
        :description="emptyLibrary ? '上传第一段课程视频，开始学习。' : '试试查看全部课程。'"
      >
        <RouterLink v-if="emptyLibrary" class="upload-link" to="/upload"><span aria-hidden="true">＋</span> 上传视频</RouterLink>
        <el-button v-else @click="activeGroup = 'ALL'">查看全部课程</el-button>
      </EmptyState>

      <div v-else-if="filteredTasks.length" class="task-list">
        <article
          v-for="{ task, title, location, demo } in displayedCards"
          :key="task.taskId"
          class="course-item"
          :class="{ 'is-batch-mode': batchMode, 'is-featured': featuredCourse?.task.taskId === task.taskId, 'is-resumed': featuredCourse?.task.taskId === task.taskId && location, 'is-demo-course': demo }"
        >
          <div v-if="batchMode" class="course-item__selection" @click.stop>
            <el-tooltip
              :disabled="isTaskDeletable(task)"
              content="处理中课程请先取消处理"
              placement="top"
            >
              <span class="course-item__checkbox-target">
                <el-checkbox
                  :model-value="selectedTaskIds.has(task.taskId)"
                  :disabled="deleting || !isTaskDeletable(task)"
                  :aria-label="`选择${title}，状态${courseStatusLabel(task)}`"
                  @change="toggleTaskSelection(task, Boolean($event))"
                />
              </span>
            </el-tooltip>
            <small v-if="!isTaskDeletable(task)">处理中课程请先取消处理</small>
          </div>
          <img v-if="demo" class="course-cover" :src="demo.cover" alt="" width="320" height="180" />
          <div class="course-item__summary">
            <div class="course-item__title-row">
              <div>
                <p v-if="!demo && featuredCourse?.task.taskId === task.taskId" class="course-item__last">{{ location ? '上次学习' : '可以开始学习' }}</p>
                <p v-if="demo" class="demo-course-series">{{ demo.series }}</p>
                <h2 class="course-item__name" :title="demo?.title || title">{{ demo?.title || title }}</h2>
                <p v-if="demo">{{ demo.description }}</p>
                <p v-if="isRunningTaskStatus(task.status)">{{ courseStageText(task.currentStage ?? "", task.status) }}</p>
                <p v-if="location && !demo" class="course-item__resume">{{ lastLocationText(location) }}</p>
              </div>
              <StatusBadge v-if="!demo" :label="courseStatusLabel(task)" :tone="courseStatusTone(task)" />
            </div>

            <div v-if="demo" class="demo-course-progress">
              <span>已学 {{ Math.floor(Math.min(1, (location?.at ?? demo.positionMs) / demo.durationMs) * 100) }}%</span>
              <progress :value="Math.min(1, (location?.at ?? demo.positionMs) / demo.durationMs)" aria-label="学习进度" />
            </div>
            <div v-if="isRunningTaskStatus(task.status) && task.progressPercent != null" class="course-progress" aria-label="材料准备进度">
              <small>材料准备</small>
              <el-progress
                :percentage="task.progressPercent"
                :show-text="false"
                :stroke-width="7"
              />
              <span>{{ task.progressPercent }}%</span>
            </div>


            <p v-if="task.status === 'FAILED'" class="course-item__failure">
              {{ readableFailure(task) }}
            </p>
            <p v-if="failedOpeningTaskId === task.taskId" class="course-item__failure" role="alert">
              暂时无法确认登录账号，请重试打开课程。
            </p>

            <details v-if="!demo" class="course-item__technical">
              <summary>材料信息与编号</summary>
            <dl class="course-item__meta">
              <div>
                <dt>课程语言</dt>
                <dd>{{ task.targetLanguage }}</dd>
              </div>
              <div>
                <dt>创建时间</dt>
                <dd>{{ formatTime(task.createdAt) }}</dd>
              </div>
              <div>
                <dt>最近更新</dt>
                <dd>{{ formatTime(task.updatedAt) }}</dd>
              </div>
            </dl>

              <div>
                <code :title="task.taskId">{{ shortenTaskId(task.taskId) }}</code>
                <button type="button" @click="copyTaskId(task.taskId)">复制编号</button>
              </div>
            </details>
          </div>

          <div class="course-item__actions">
            <el-button type="primary" :loading="openingTaskId === task.taskId" @click="openTask(task)">
              {{ failedOpeningTaskId === task.taskId ? "重试打开课程" : demo ? `继续学习 ${lessonClock(location?.at ?? demo.positionMs)}` : primaryActionText(task, location) }}
              <span v-if="featuredCourse?.task.taskId === task.taskId" class="course-item__arrow" aria-hidden="true">→</span>
            </el-button>
            <el-button
              v-if="isRetryableTaskStatus(task.status)"
              :loading="retryingTaskId === task.taskId"
              plain
              @click="confirmRetryTask(task)"
            >
              重新处理
            </el-button>
          </div>
        </article>
      </div>

      <nav v-if="pageCount > 1" class="task-list-pagination" aria-label="课程列表分页">
        <p>第 {{ page }} / {{ pageCount }} 页 · 筛选当前页的课程</p>
        <el-button :disabled="page === 1 || loading || deleting" @click="changePage(page - 1)">上一页</el-button>
        <el-button :disabled="page === pageCount || loading || deleting" @click="changePage(page + 1)">下一页</el-button>
      </nav>
    </SectionPanel>
  </main>
</template>

<style scoped>
.task-list-page { display: grid; gap: 20px; padding-block: 36px 64px; }
.task-list-page .course-library { display: grid; gap: 16px; border: 0; padding: 0; background: transparent; box-shadow: none; }
.upload-link { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 44px; padding-inline: 16px; border-radius: var(--radius-md); background: var(--color-brand); color: white; text-decoration: none; font-weight: 650; }
.upload-link:hover { background: var(--color-brand-strong); }
.library-empty { border-radius: var(--radius-lg); border-style: solid; background: var(--color-surface); }
.task-list-toolbar, .batch-management, .task-list-pagination { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.task-list-toolbar { padding-block: 8px; border-block: 1px solid var(--color-border); }
.task-list-toolbar__filters { display: flex; flex-wrap: wrap; gap: 4px; }
.task-list-toolbar__filters :deep(.el-radio-button__inner) { border: 1px solid transparent; border-radius: var(--radius-md); padding: 10px 12px; background: transparent; }
.task-list-toolbar__filters :deep(.is-active .el-radio-button__inner) { border-color: var(--color-border); color: var(--color-brand-strong); background: var(--color-brand-soft); box-shadow: none; }
.task-list-toolbar__filters :deep(input:focus-visible + span) { outline: 2px solid var(--color-brand); outline-offset: 2px; }
.task-list-toolbar__actions, .batch-management__actions, .course-item__actions { display: flex; flex-wrap: wrap; gap: 8px; }
.task-list-page :deep(.el-button + .el-button) { margin-inline-start: 0; }
.batch-management { padding: 12px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); }
.auto-refresh-note, .task-list-pagination p, .course-item__selection small { margin: 0; color: var(--color-ink-soft); font-size: 13px; }
.task-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(290px, 100%), 1fr)); gap: 16px; }
.course-item { display: flex; flex-direction: column; min-width: 0; gap: 16px; padding: 20px; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); }
.course-item.is-featured { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; grid-column: 1 / -1; gap: 20px 36px; min-height: 178px; padding: clamp(18px, 3vw, 32px); border-color: var(--color-border-strong); border-inline-start: 5px solid var(--color-brand); background: var(--color-brand-soft); }
.is-featured .course-item__name { font-size: clamp(22px, 3.2vw, 32px); letter-spacing: -.025em; }
.is-featured .course-item__title-row { justify-content: flex-start; }
.is-featured .course-item__title-row > div { flex: 0 1 auto; }
.is-featured .course-item__actions { margin-top: 0; }
.is-featured .course-item__actions .el-button { min-height: 44px; }
.course-item__arrow { margin-inline-start: 8px; }
.course-item__summary { display: grid; gap: 12px; min-width: 0; }
.course-item__title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px 16px; flex-wrap: wrap; }
.course-item__title-row > div { flex: 1 1 150px; min-width: 0; }
.course-item__name { margin: 0; color: var(--color-ink); font-size: 19px; line-height: 1.35; overflow-wrap: anywhere; }
.course-item__title-row p { margin: 6px 0 0; color: var(--color-ink-soft); font-size: 14px; }
.course-item__title-row .course-item__last { margin: 0 0 6px; color: var(--color-brand-strong); font-size: 13px; font-weight: 650; }
.course-item__resume, .course-progress span { font-variant-numeric: tabular-nums; }
.course-item__selection { display: flex; gap: 8px; align-items: center; }
.course-progress { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 8px; align-items: center; color: var(--color-ink-soft); font-size: 13px; }
.course-item__failure { margin: 0; padding: 8px 12px; border-radius: var(--radius-md); background: var(--color-danger-surface); color: var(--color-danger); font-size: 14px; line-height: 1.6; }
.course-item__technical { color: var(--color-ink-soft); font-size: 13px; }
.course-item__technical summary { cursor: pointer; width: fit-content; }
.course-item__technical dl { display: grid; gap: 4px; }
.course-item__technical div { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.course-item__technical dd { margin: 0; }
.course-item__technical button { border: 0; padding: 4px; background: transparent; color: var(--color-brand-strong); cursor: pointer; }
.course-item__actions { margin-top: auto; }
.task-list-pagination { justify-content: flex-start; }

@media (max-width: 640px) {
  .task-list-page { padding-top: 24px; gap: 16px; }
  .task-list { grid-template-columns: 1fr; }
  .course-item { padding: 16px; }
  .course-item.is-featured { grid-template-columns: 1fr; gap: 10px; }
  .task-list-page :deep(.el-button), .task-list-toolbar__filters :deep(.el-radio-button__inner) { min-height: 44px; }
  .course-item__technical summary { display: list-item; padding-block: 12px; }
}

.course-item.is-demo-course { display: grid; grid-template-columns: minmax(240px, 38%) minmax(0, 1fr); align-items: center; gap: 20px; }
.course-cover { width: 100%; height: auto; display: block; border-radius: 12px; grid-row: span 2; }
.demo-course-series { color: var(--color-brand); font-size: 13px; font-weight: 650; }
.demo-course-progress { display: flex; align-items: center; gap: 10px; color: var(--color-ink-soft); font-size: 13px; }
.demo-course-progress progress { accent-color: var(--color-brand); height: 8px; width: 85px; }
@media (max-width: 680px) {
  .course-item.is-demo-course { grid-template-columns: 1fr; }
  .course-cover { grid-row: auto; }
}
</style>
