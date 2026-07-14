<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  batchDeleteTasks,
  fetchTasks,
  retryTask,
  toReadableBatchDeleteError,
  toReadableTaskError,
} from "../api/task";
import EmptyState from "../components/ui/EmptyState.vue";
import PageHeading from "../components/ui/PageHeading.vue";
import SectionPanel from "../components/ui/SectionPanel.vue";
import StatusBadge from "../components/ui/StatusBadge.vue";
import type { TaskSummaryResponse } from "../types/task";
import { toUserFriendlyError } from "../utils/errorMessage";
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
  { label: "已完成", value: "SUCCEEDED" },
  { label: "失败", value: "FAILED" },
  { label: "已取消", value: "CANCELED" },
];

const AUTO_REFRESH_INTERVAL_MS = 5000;
const MAX_TASK_PAGE_SIZE = 100;

const router = useRouter();
const loading = ref(false);
const refreshing = ref(false);
const retryingTaskId = ref("");
const errorMessage = ref("");
const tasks = ref<TaskSummaryResponse[]>([]);
const total = ref(0);
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

const emptyText = computed(() => {
  switch (activeGroup.value) {
    case "FAILED":
      return "还没有处理失败的课程。";
    case "SUCCEEDED":
      return "还没有处理完成的课程。";
    case "RUNNING":
      return "还没有正在处理的课程。";
    case "CANCELED":
      return "还没有已取消的课程。";
    case "ALL":
    default:
      return "还没有上传课程视频。";
  }
});

onMounted(() => {
  componentActive = true;
  void loadTasks();
});

onBeforeUnmount(() => {
  componentActive = false;
  latestTaskRequestVersion += 1;
  stopAutoRefresh();
});

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
    const result = await fetchTasks(1, MAX_TASK_PAGE_SIZE, "ALL");
    if (!componentActive || requestVersion !== latestTaskRequestVersion) {
      return;
    }
    tasks.value = result.items;
    total.value = result.total;
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

function openTask(task: TaskSummaryResponse) {
  void router.push(`/tasks/${encodeURIComponent(task.taskId)}`);
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

function primaryActionText(task: TaskSummaryResponse): string {
  if (task.status === "SUCCEEDED") {
    return "查看结果";
  }
  if (isRunningTaskStatus(task.status)) {
    return "查看进度";
  }
  return "查看详情";
}

function courseStatusLabel(task: TaskSummaryResponse): string {
  const status = String(task.status || "").toUpperCase();
  if (status === "SUCCEEDED") {
    return "已完成";
  }
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

function readableStage(stage: string | null): string {
  switch (stage) {
    case "VALIDATE_TASK":
    case "RESOLVE_UPLOADED_SOURCE":
      return "正在读取视频";
    case "EXTRACT_AUDIO":
      return "正在提取音频";
    case "TRANSCRIBE":
    case "TRANSCRIBING":
    case "ASR":
    case "PERSIST_SUBTITLES":
      return "正在生成字幕";
    case "TRANSLATE":
    case "TRANSLATE_SUBTITLES":
    case "TRANSLATING":
      return "正在生成翻译";
    case "GENERATE_LEARNING_PACKAGE":
      return "正在生成学习资料";
    case "GENERATE_ARTIFACTS":
      return "正在生成下载文件";
    case "WRITE_AI_CALL_RECORD":
      return "正在保存处理结果";
    case "DONE":
      return "已完成";
    case "FAILED":
      return "处理失败";
    default:
      return stage ? "处理中" : "等待处理";
  }
}

function courseSecondaryStatus(task: TaskSummaryResponse): string {
  if (isRunningTaskStatus(task.status)) {
    return readableStage(task.currentStage);
  }
  return courseStatusLabel(task);
}

function courseTitle(task: TaskSummaryResponse): string {
  if (!task.createdAt) {
    return "课程视频";
  }
  const date = new Date(task.createdAt);
  if (Number.isNaN(date.getTime())) {
    return "课程视频";
  }
  return `课程视频 · ${date.toLocaleDateString(undefined, { month: "long", day: "numeric" })}`;
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
  if (!value) {
    return "暂无";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}
</script>

<template>
  <main class="task-list-page page-container">
    <PageHeading
      title="我的课程"
      description="查看课程视频的处理进度和结果。"
    >
      <template #actions>
        <RouterLink to="/upload">
          <el-button type="primary" size="large">上传视频</el-button>
        </RouterLink>
      </template>
    </PageHeading>

    <SectionPanel class="course-library">
      <div class="task-list-toolbar">
        <el-radio-group v-model="activeGroup" :disabled="deleting" class="task-list-toolbar__filters">
          <el-radio-button v-for="filter in TASK_FILTERS" :key="filter.value" :label="filter.value">
            {{ filter.label }} {{ filterCounts[filter.value] }}
          </el-radio-button>
        </el-radio-group>
        <div class="task-list-toolbar__actions">
          <el-button text :loading="loading || refreshing" :disabled="deleting" @click="loadTasks()">刷新</el-button>
          <el-button v-if="batchMode" :disabled="deleting" @click="exitBatchMode">退出批量管理</el-button>
          <el-button v-else @click="enterBatchMode">批量管理</el-button>
        </div>
      </div>

      <div v-if="batchMode" class="batch-management" aria-label="课程批量管理工具栏">
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

      <p v-if="hasRunningTasks" class="auto-refresh-note">课程正在处理中，列表会自动更新。</p>

      <el-alert
        v-if="errorMessage"
        :closable="false"
        :title="errorMessage"
        show-icon
        type="error"
      />

      <el-skeleton v-if="loading && tasks.length === 0" :rows="5" animated />
      <EmptyState
        v-else-if="filteredTasks.length === 0"
        title="还没有课程视频"
        :description="emptyText"
      >
        <RouterLink to="/upload">
          <el-button type="primary">上传第一门课程</el-button>
        </RouterLink>
      </EmptyState>

      <div v-else class="task-list">
        <article v-for="task in filteredTasks" :key="task.taskId" class="course-item" :class="{ 'is-batch-mode': batchMode }">
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
                  :aria-label="`选择${courseTitle(task)}，状态${courseStatusLabel(task)}`"
                  @change="toggleTaskSelection(task, Boolean($event))"
                />
              </span>
            </el-tooltip>
            <small v-if="!isTaskDeletable(task)">处理中课程请先取消处理</small>
          </div>
          <div class="course-item__summary">
            <div class="course-item__title-row">
              <div>
                <h2>{{ courseTitle(task) }}</h2>
                <p>{{ courseSecondaryStatus(task) }}</p>
              </div>
              <StatusBadge :label="courseStatusLabel(task)" :tone="courseStatusTone(task)" />
            </div>

            <div class="course-progress">
              <el-progress
                :percentage="task.progressPercent ?? 0"
                :show-text="false"
                :stroke-width="7"
                :status="task.status === 'FAILED' ? 'exception' : task.status === 'SUCCEEDED' ? 'success' : undefined"
              />
              <span>{{ task.progressPercent ?? 0 }}%</span>
            </div>

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

            <p v-if="task.status === 'FAILED'" class="course-item__failure">
              {{ readableFailure(task) }}
            </p>

            <details class="course-item__technical">
              <summary>课程编号</summary>
              <div>
                <code :title="task.taskId">{{ shortenTaskId(task.taskId) }}</code>
                <button type="button" @click="copyTaskId(task.taskId)">复制编号</button>
              </div>
            </details>
          </div>

          <div class="course-item__actions">
            <el-button type="primary" @click="openTask(task)">{{ primaryActionText(task) }}</el-button>
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

      <p v-if="total > 0" class="task-list-page__total">
        当前显示 {{ filteredTasks.length }} 门课程，共 {{ total }} 门
      </p>
    </SectionPanel>
  </main>
</template>

<style scoped>
.task-list-page {
  display: grid;
  gap: 28px;
  padding-block: 46px 72px;
}

.course-library {
  display: grid;
  gap: 20px;
}

.task-list-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.task-list-toolbar__filters {
  max-width: 100%;
  overflow-x: auto;
}

.task-list-toolbar__actions,
.batch-management__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.task-list-toolbar__actions :deep(.el-button),
.batch-management__actions :deep(.el-button) {
  margin-left: 0;
}

.batch-management {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-canvas);
}

.batch-management strong {
  color: var(--color-ink);
  font-size: 14px;
}

.auto-refresh-note,
.task-list-page__total {
  margin: 0;
  color: var(--color-ink-muted);
  font-size: 13px;
}

.task-list {
  border-top: 1px solid var(--color-border);
}

.course-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 32px;
  padding: 26px 2px;
  border-bottom: 1px solid var(--color-border);
}

.course-item.is-batch-mode {
  grid-template-columns: auto minmax(0, 1fr) auto;
}

.course-item__selection {
  display: grid;
  align-content: start;
  gap: 6px;
  max-width: 170px;
  padding-top: 2px;
}

.course-item__checkbox-target {
  display: inline-flex;
  align-items: center;
  min-width: 44px;
  min-height: 44px;
}

.course-item__selection small {
  color: var(--color-ink-muted);
  font-size: 12px;
  line-height: 1.5;
}

.course-item__summary {
  display: grid;
  gap: 16px;
  min-width: 0;
}

.course-item__title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.course-item h2 {
  margin: 0;
  color: var(--color-ink);
  font-size: 18px;
  letter-spacing: -0.015em;
}

.course-item__title-row p {
  margin: 6px 0 0;
  color: var(--color-ink-soft);
  font-size: 14px;
}

.course-progress {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 42px;
  align-items: center;
  gap: 14px;
  max-width: 720px;
}

.course-progress span {
  color: var(--color-brand-strong);
  font-size: 13px;
  font-weight: 700;
  text-align: right;
}

.course-item__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 18px 34px;
  margin: 0;
}

.course-item__meta div {
  display: grid;
  gap: 4px;
}

.course-item__meta dt,
.course-item__meta dd {
  margin: 0;
  font-size: 12px;
}

.course-item__meta dt {
  color: var(--color-ink-muted);
}

.course-item__meta dd {
  color: var(--color-ink-soft);
  font-weight: 620;
}

.course-item__failure {
  margin: 0;
  padding: 10px 12px;
  border-left: 2px solid var(--color-danger);
  background: #fbf2f1;
  color: var(--color-danger);
  font-size: 13px;
  line-height: 1.6;
}

.course-item__technical {
  color: var(--color-ink-muted);
  font-size: 12px;
}

.course-item__technical summary {
  cursor: pointer;
}

.course-item__technical div {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
}

.course-item__technical code {
  color: var(--color-ink-soft);
}

.course-item__technical button {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-brand-strong);
  cursor: pointer;
  font-size: 12px;
  font-weight: 650;
}

.course-item__actions {
  display: flex;
  align-items: flex-end;
  flex-direction: column;
  gap: 10px;
  justify-content: center;
}

.course-item__actions :deep(.el-button) {
  min-width: 138px;
  margin-left: 0;
}

@media (max-width: 760px) {
  .task-list-page {
    padding-block: 34px 52px;
  }

  .task-list-toolbar,
  .course-item {
    align-items: stretch;
    grid-template-columns: 1fr;
  }

  .task-list-toolbar {
    flex-direction: column;
  }

  .task-list-toolbar__actions,
  .batch-management,
  .batch-management__actions {
    width: 100%;
  }

  .batch-management {
    align-items: stretch;
    flex-direction: column;
  }

  .batch-management__actions :deep(.el-button) {
    flex: 1 1 140px;
  }

  .task-list-toolbar__filters {
    width: 100%;
  }

  .course-item {
    gap: 20px;
  }

  .course-item.is-batch-mode {
    grid-template-columns: 1fr;
  }

  .course-item__selection {
    max-width: none;
  }

  .course-item__title-row {
    align-items: flex-start;
    flex-direction: column-reverse;
  }

  .course-item__actions,
  .course-item__actions :deep(.el-button) {
    width: 100%;
  }
}
</style>
