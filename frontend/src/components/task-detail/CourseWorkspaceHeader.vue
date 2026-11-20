<script setup lang="ts">
import type { AnalysisTaskStatus } from "../../types/task";
import { getTaskStatusLabel, getTaskStatusTagType } from "../../utils/taskStatus";
import StatusBadge from "../ui/StatusBadge.vue";
import { courseLearnable } from "./workspace";

const props = defineProps<{
  compact?: boolean;
  demoMode?: boolean;
  courseName?: string | null;
  status?: AnalysisTaskStatus;
  learningReady?: boolean | null;
  canCancel: boolean;
  canRetry: boolean;
  refreshing: boolean;
  cancelLoading: boolean;
  retryLoading: boolean;
}>();

defineEmits<{
  refresh: [];
  cancel: [];
  retry: [];
}>();
</script>

<template>
  <header class="workspace-header" :class="{ 'workspace-header--compact': compact, 'workspace-header--attention': canCancel || canRetry }">
    <div class="workspace-header__copy">
      <RouterLink class="workspace-header__back" to="/tasks">← 返回我的课程</RouterLink>
      <div class="workspace-header__title-row">
        <h1 class="workspace-header__title" :title="courseName || undefined">{{ courseName || "课程学习" }}</h1>
        <StatusBadge
          v-if="compact && status"
          :tone="status === 'SUCCEEDED' ? 'success' : status === 'FAILED' ? 'danger' : canCancel ? 'progress' : 'neutral'"
          :label="status === 'SUCCEEDED' ? '材料已就绪' : courseLearnable(status, learningReady) ? '字幕可学习 · 资料准备中' : getTaskStatusLabel(status)"
        />
      </div>
      <span v-if="compact && demoMode" class="workspace-mode">本地演示 · 无外部 AI</span>
      <p v-if="!compact">看课、回看来源，继续你的提问与练习。</p>
    </div>
    <div class="workspace-header__actions" :class="{ 'is-ready': courseLearnable(props.status, props.learningReady) }" aria-label="课程操作">
      <el-tag v-if="!compact" :type="getTaskStatusTagType(props.status)" effect="plain">
        {{ props.status === "SUCCEEDED" ? "材料已就绪" : courseLearnable(props.status, props.learningReady) ? "可以开始学习 · 资料后台生成中" : props.status ? getTaskStatusLabel(props.status) : "等待处理" }}
      </el-tag>
      <component :is="compact ? 'details' : 'div'" class="course-controls" :open="compact && (canCancel || canRetry)">
        <summary v-if="compact">课程操作</summary>
      <el-button :loading="props.refreshing" @click="$emit('refresh')">刷新</el-button>
      <el-button
        v-if="props.canCancel"
        :loading="props.cancelLoading"
        type="danger"
        plain
        @click="$emit('cancel')"
      >
        取消处理
      </el-button>
      <el-button
        v-if="props.canRetry"
        :loading="props.retryLoading"
        type="primary"
        @click="$emit('retry')"
      >
        重新处理
      </el-button>
        <slot name="workspace-actions" />
      </component>
    </div>
  </header>
</template>

<style scoped>
.workspace-header { display: flex; align-items: end; justify-content: space-between; flex-wrap: wrap; gap: 12px 24px; padding-bottom: 12px; border-bottom: 1px solid var(--color-border); }
.workspace-header--compact { align-items: center; border-block-end: 0; padding-bottom: 0; }
.workspace-header__copy { display: grid; gap: 6px; min-width: 0; }
.workspace-header__title-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 16px; }
.workspace-header__back { width: fit-content; color: var(--color-brand-strong); font-size: 14px; font-weight: 650; text-decoration: none; }
.workspace-header h1 { margin: 0; color: var(--color-ink); font-size: clamp(25px, 3vw, 38px); line-height: 1.18; letter-spacing: -0.03em; overflow-wrap: anywhere; }
.workspace-header p, .workspace-mode { margin: 0; color: var(--color-ink-soft); }
.workspace-mode { font-size: 13px; }
.workspace-header__actions, .course-controls[open] { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.course-controls summary { width: fit-content; cursor: pointer; padding: 8px 12px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-ink); font-size: 14px; }
.course-controls[open] { padding: 8px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); }
.course-controls .el-button + .el-button { margin-inline-start: 0; }
@media (max-width: 640px) {
  .workspace-header { align-items: flex-start; gap: 8px 12px; }
  .workspace-header__copy { flex: 1 1 min(210px, 100%); }
  .workspace-header--attention .workspace-header__actions { flex-basis: 100%; }
  .course-controls summary, .course-controls :deep(button) { min-height: 44px; }
  .course-controls summary { padding-block: 12px; }
}
</style>
