<script setup lang="ts">
import { computed } from "vue";
import type { TaskEventPayload, TaskDetailResponse } from "../../types/task";
import type { TaskResultResponse } from "../../types/result";
import type { CourseWorkspace } from "./workspace";
import { courseStageText, readableTaskError } from "./workspace";

const props = defineProps<{
  task: TaskEventPayload | null;
  taskDetail: TaskDetailResponse | null;
  result: TaskResultResponse | null;
  canRetry: boolean;
  retryLoading: boolean;
}>();
defineEmits<{ navigate: [workspace: CourseWorkspace]; retry: [] }>();

const status = computed(() => props.task?.status || props.taskDetail?.status);
const failed = computed(() => status.value === "FAILED");
const stage = computed(() => courseStageText(props.task?.currentStage || props.taskDetail?.currentStage || "", status.value));
const errorSummary = computed(() => readableTaskError(props.task?.errorMessage || props.taskDetail?.errorMessage || ""));
const availability = computed(() => [
  { label: "课程内容", value: props.result?.subtitles.length || props.result?.sourceFullText ? "已生成" : "尚未生成" },
  { label: "中文译文", value: props.result?.translatedFullText ? "已生成" : "尚未生成" },
  { label: "学习资料", value: props.result?.learningPackage ? "已生成" : "尚未生成" },
  { label: "课程章节", value: "按需查看" },
  { label: "下载文件", value: `${props.result?.artifacts.length ?? 0} 个` },
]);
</script>

<template>
  <section class="workspace-panel overview-panel" aria-labelledby="overview-title">
    <header>
      <p class="workspace-panel__eyebrow">课程概览</p>
      <h2 id="overview-title">当前内容</h2>
      <p>查看处理进度，以及已经可以使用的课程内容。</p>
    </header>

    <div v-if="failed" class="overview-failure" role="alert">
      <strong>处理失败</strong>
      <span>失败阶段：{{ stage }}</span>
      <p>{{ errorSummary || "课程处理失败，请查看错误信息或重新处理。" }}</p>
      <el-button v-if="canRetry" type="primary" :loading="retryLoading" @click="$emit('retry')">重新处理</el-button>
    </div>

    <dl class="availability-list">
      <div v-for="item in availability" :key="item.label">
        <dt>{{ item.label }}</dt>
        <dd>{{ item.value }}</dd>
      </div>
    </dl>

    <div class="overview-actions" aria-label="课程内容快捷入口">
      <button type="button" @click="$emit('navigate', 'content')">查看课程内容 <span>→</span></button>
      <button type="button" @click="$emit('navigate', 'study')">查看学习资料 <span>→</span></button>
      <button type="button" @click="$emit('navigate', 'qa')">打开课程问答 <span>→</span></button>
    </div>
  </section>
</template>

<style scoped>
.workspace-panel { display: grid; gap: 24px; min-width: 0; padding: clamp(20px, 3vw, 32px); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); box-shadow: var(--shadow-low); }
header { display: grid; gap: 7px; }
header h2, header p { margin: 0; }
header h2 { color: var(--color-ink); font-size: 26px; }
header > p:last-child { color: var(--color-ink-soft); line-height: 1.7; }
.workspace-panel__eyebrow { color: var(--color-brand) !important; font-size: 12px; font-weight: 750; letter-spacing: .12em; }
.overview-failure { display: grid; gap: 8px; padding: 16px; border-left: 3px solid var(--color-danger, #a33a3a); background: #fbf4f3; }
.overview-failure p { margin: 0; color: var(--color-ink-soft); }
.overview-failure :deep(.el-button) { width: fit-content; margin-top: 4px; }
.availability-list { display: grid; margin: 0; border-top: 1px solid var(--color-border); }
.availability-list div { display: flex; justify-content: space-between; gap: 20px; padding: 15px 2px; border-bottom: 1px solid var(--color-border); }
.availability-list dt, .availability-list dd { margin: 0; }
.availability-list dt { color: var(--color-ink); font-weight: 650; }
.availability-list dd { color: var(--color-ink-soft); }
.overview-actions { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.overview-actions button { display: flex; justify-content: space-between; gap: 12px; padding: 15px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-canvas); color: var(--color-ink); font: inherit; font-weight: 650; cursor: pointer; text-align: left; }
.overview-actions button:hover { border-color: var(--color-brand); color: var(--color-brand); }
@media (max-width: 680px) { .overview-actions { grid-template-columns: 1fr; } }
</style>
