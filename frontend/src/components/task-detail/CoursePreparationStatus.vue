<script setup lang="ts">
import { computed } from "vue";
import type { TaskConnectionStatus, TaskDetailResponse, TaskEventPayload } from "../../types/task";
import { formatDurationBetween } from "../../utils/time";
import { getTaskStatusLabel, getTaskStatusTagType, isRunningTaskStatus } from "../../utils/taskStatus";
import { connectionText, courseStageText, formatWorkspaceTime, readableTaskError } from "./workspace";

const props = defineProps<{
  classic?: boolean;
  task: TaskEventPayload | null;
  taskDetail: TaskDetailResponse | null;
  connectionStatus: TaskConnectionStatus;
  connectionError: string;
}>();

const status = computed(() => props.task?.status ?? props.taskDetail?.status);
const progress = computed(() => props.task?.progressPercent ?? props.taskDetail?.progressPercent);
const stage = computed(() => courseStageText(props.task?.currentStage || props.taskDetail?.currentStage || "", status.value));
const errorSummary = computed(() => readableTaskError(props.task?.errorMessage || props.taskDetail?.errorMessage || ""));
const isRunning = computed(() => isRunningTaskStatus(status.value));
const isSucceeded = computed(() => status.value === "SUCCEEDED");
</script>

<template>
  <section class="course-status" :class="{ 'is-classic': classic }" aria-labelledby="course-status-title">
    <div class="course-status__heading">
      <div>
        <span v-if="classic">处理状态</span>
        <strong id="course-status-title">{{ stage }}</strong>
      </div>
      <el-tag v-if="classic" :type="getTaskStatusTagType(task?.status || taskDetail?.status)" effect="plain">
        {{ getTaskStatusLabel(task?.status || taskDetail?.status) }}
      </el-tag>
    </div>

    <template v-if="isRunning">
      <el-progress v-if="progress != null" :percentage="progress" :show-text="false" :stroke-width="7" />
      <div class="course-status__meta">
        <span v-if="progress != null">{{ progress }}%</span>
        <span v-if="classic">{{ formatWorkspaceTime(task?.updatedAt || taskDetail?.updatedAt) }}</span>
        <span>{{ connectionText(connectionStatus) }}</span>
      </div>
    </template>
    <template v-else-if="isSucceeded">
      <dl>
        <div><dt>处理耗时</dt><dd>{{ formatDurationBetween(taskDetail?.startedAt, taskDetail?.finishedAt) }}</dd></div>
        <div><dt>目标语言</dt><dd>{{ taskDetail?.targetLanguage || "暂无" }}</dd></div>
      </dl>
    </template>
    <template v-else>
      <p v-if="errorSummary" class="course-status__error" role="alert">{{ errorSummary }}</p>
      <p v-else>当前课程处理已结束。</p>
    </template>

    <p v-if="connectionError" class="course-status__error" role="alert">{{ connectionError }}</p>
  </section>
</template>

<style scoped>
.course-status { border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); display: grid; gap: 8px; padding: 12px 16px; }
.course-status__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.course-status__heading > div { display: grid; gap: 4px; }
.course-status__heading span, .course-status__meta, .course-status p, dt { color: var(--color-ink-soft); font-size: 13px; }
.course-status__heading strong { color: var(--color-ink); font-size: 17px; }
.course-status__meta { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; }
.course-status p { margin: 0; }
.course-status .course-status__error { color: var(--color-danger); }
dl { display: grid; gap: 10px; margin: 0; }
dl div { display: flex; justify-content: space-between; gap: 12px; }
dt, dd { margin: 0; }
dd { color: var(--color-ink); text-align: right; overflow-wrap: anywhere; }
.is-classic { padding: 18px; gap: 14px; }
</style>
