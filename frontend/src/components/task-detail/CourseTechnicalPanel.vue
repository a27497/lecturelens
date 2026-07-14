<script setup lang="ts">
import { ref, watch } from "vue";
import type { TaskConnectionStatus, TaskDetailResponse, TaskEventPayload } from "../../types/task";
import type { TaskResultResponse } from "../../types/result";
import { connectionText, formatWorkspaceTime } from "./workspace";

type TechnicalView = "status" | "calls";
const props = defineProps<{
  taskId: string;
  task: TaskEventPayload | null;
  taskDetail: TaskDetailResponse | null;
  result: TaskResultResponse | null;
  connectionStatus: TaskConnectionStatus;
  lastHeartbeatAt: string;
}>();

const activeView = ref<TechnicalView>("status");
const views: Array<{ value: TechnicalView; label: string }> = [
  { value: "status", label: "处理状态" },
  { value: "calls", label: "模型调用" },
];

watch(() => props.taskId, () => {
  activeView.value = "status";
});
</script>

<template>
  <section class="workspace-panel technical-panel" aria-labelledby="technical-title">
    <header><h2 id="technical-title">处理详情</h2><p>查看处理状态和模型调用记录。</p></header>
    <nav class="subnav" aria-label="处理详情视图">
      <button v-for="item in views" :key="item.value" type="button" :aria-pressed="activeView === item.value" :class="{ 'is-active': activeView === item.value }" @click="activeView = item.value">{{ item.label }}</button>
    </nav>

    <section v-if="activeView === 'status'" class="technical-status" aria-label="处理状态">
      <dl>
        <div><dt>任务 ID</dt><dd>{{ taskId }}</dd></div>
        <div><dt>原始状态</dt><dd>{{ task?.status || taskDetail?.status || '暂无' }}</dd></div>
        <div><dt>原始阶段</dt><dd>{{ task?.currentStage || taskDetail?.currentStage || '暂无' }}</dd></div>
        <div><dt>错误码</dt><dd>{{ task?.errorCode || taskDetail?.errorCode || '无' }}</dd></div>
        <div><dt>连接状态</dt><dd>{{ connectionText(connectionStatus) }}</dd></div>
        <div><dt>更新时间</dt><dd>{{ formatWorkspaceTime(task?.updatedAt || taskDetail?.updatedAt) }}</dd></div>
        <div><dt>心跳时间</dt><dd>{{ formatWorkspaceTime(lastHeartbeatAt) }}</dd></div>
      </dl>
      <div v-if="task?.errorMessage || taskDetail?.errorMessage" class="raw-error" role="alert"><strong>原始错误摘要</strong><p>{{ task?.errorMessage || taskDetail?.errorMessage }}</p></div>
    </section>

    <section v-else class="model-calls" aria-labelledby="calls-title">
      <h3 id="calls-title">模型调用记录</h3>
      <el-empty v-if="!result?.aiCallRecords.length" description="暂无模型调用记录" />
      <div v-else class="call-list">
        <article v-for="record in result.aiCallRecords" :key="record.id">
          <div><strong>{{ record.stage }}</strong><el-tag size="small" effect="plain">{{ record.status }}</el-tag></div>
          <span>{{ record.callType }}</span><span>{{ record.provider }}<template v-if="record.model"> / {{ record.model }}</template></span>
          <small>{{ record.durationMillis === null ? '暂无耗时' : `${record.durationMillis} ms` }} · {{ record.totalTokens === null ? '暂无 token' : `${record.totalTokens} tokens` }}</small>
        </article>
      </div>
    </section>
  </section>
</template>

<style scoped>
.workspace-panel { display: grid; gap: 22px; min-width: 0; padding: clamp(20px, 3vw, 30px); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); box-shadow: var(--shadow-low); }
header { display: grid; gap: 6px; } header h2, header p, h3 { margin: 0; } header p { color: var(--color-ink-soft); }
.subnav { display: flex; gap: 6px; padding-bottom: 12px; border-bottom: 1px solid var(--color-border); overflow-x: auto; }.subnav button { flex: 0 0 auto; padding: 8px 13px; border: 1px solid transparent; border-radius: var(--radius-sm); background: transparent; color: var(--color-ink-soft); font: inherit; cursor: pointer; }.subnav button.is-active { border-color: var(--color-border); background: var(--color-brand-soft, #edf4f0); color: var(--color-brand); font-weight: 700; }
.technical-status dl { display: grid; margin: 0; border-top: 1px solid var(--color-border); }.technical-status dl div { display: grid; grid-template-columns: 150px minmax(0,1fr); gap: 16px; padding: 13px 0; border-bottom: 1px solid var(--color-border); }.technical-status dt { color: var(--color-ink-soft); }.technical-status dd { margin: 0; overflow-wrap: anywhere; }.raw-error { margin-top: 18px; padding: 15px; border-left: 3px solid var(--color-danger, #a33a3a); background: #fbf4f3; }.raw-error p { margin-bottom: 0; overflow-wrap: anywhere; }
.model-calls, .call-list { display: grid; gap: 18px; min-width: 0; }.call-list article { display: grid; gap: 10px; padding: 16px 0; border-bottom: 1px solid var(--color-border); }.call-list article > div { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; }.call-list article > span, .call-list article small { color: var(--color-ink-soft); }
@media (max-width: 700px) { .technical-status dl div { grid-template-columns: 1fr; gap: 5px; } }
</style>
