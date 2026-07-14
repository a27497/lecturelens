<script setup lang="ts">
import type { AnalysisTaskStatus } from "../../types/task";
import { getTaskStatusLabel, getTaskStatusTagType } from "../../utils/taskStatus";

const props = defineProps<{
  status?: AnalysisTaskStatus;
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
  <header class="workspace-header">
    <div class="workspace-header__copy">
      <RouterLink class="workspace-header__back" to="/tasks">← 返回我的课程</RouterLink>
      <h1>课程详情</h1>
      <p>查看视频、课程内容和学习资料。</p>
    </div>
    <div class="workspace-header__actions" aria-label="课程操作">
      <el-tag :type="getTaskStatusTagType(props.status)" effect="plain">
        {{ props.status ? getTaskStatusLabel(props.status) : "等待处理" }}
      </el-tag>
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
    </div>
  </header>
</template>

<style scoped>
.workspace-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 22px;
  border-bottom: 1px solid var(--color-border);
}
.workspace-header__copy { display: grid; gap: 7px; }
.workspace-header__back { width: fit-content; color: var(--color-brand); font-size: 14px; font-weight: 650; text-decoration: none; }
.workspace-header h1 { margin: 0; color: var(--color-ink); font-size: clamp(28px, 3vw, 38px); letter-spacing: -0.03em; }
.workspace-header p { margin: 0; color: var(--color-ink-soft); }
.workspace-header__actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 10px; }
@media (max-width: 760px) {
  .workspace-header { align-items: stretch; flex-direction: column; }
  .workspace-header__actions { justify-content: flex-start; }
}
</style>
