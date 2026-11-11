<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { getCourseModelUsage, featureLabels, invocationLabel, selectionSource } from "../../api/modelUsage";
import type { CourseModelUsage } from "../../api/modelUsage";
import ModelEvidence from "./ModelEvidence.vue";
const props = defineProps<{ taskId: string; refreshKey?: string }>();
const opened = ref(false), loading = ref(false), error = ref("");
const usage = ref<CourseModelUsage | null>(null);
let generation = 0;
let controller: AbortController | undefined;
watch(() => props.taskId, () => { generation++; controller?.abort(); opened.value = false; usage.value = null; error.value = ""; loading.value = false; });
watch(() => props.refreshKey, () => { if (opened.value) void load(); });
onBeforeUnmount(() => { generation++; controller?.abort(); });
async function load() {
  const version = ++generation, task = props.taskId;
  controller?.abort(); controller = new AbortController();
  opened.value = true; loading.value = true; usage.value = null; error.value = "";
  try {
    const result = await getCourseModelUsage(task, controller.signal);
    if (version === generation && props.taskId === task) {
      if (result.taskId !== task) throw Error("identity");
      usage.value = result;
    }
  } catch { if (version === generation) error.value = "模型记录不可用或权限已变化，请重新打开课程。"; }
  finally { if (version === generation) loading.value = false; }
}
</script>
<template>
  <section class="model-usage" aria-label="课程模型使用记录">
    <el-button :loading="loading" @click="load">{{ opened ? '刷新模型使用记录' : '模型使用记录' }}</el-button>
    <div v-if="opened">
      <h3>课程模型使用记录</h3>
      <p v-if="error" role="alert">{{ error }}</p>
      <template v-if="usage">
        <details><summary>当前下次配置（不是历史执行记录）</summary>
          <p v-if="!usage.current">未记录或系统模型管理未启用。</p>
          <template v-else><p>当前系统版本 v{{ usage.current.configVersion }}</p><p v-for="r in usage.current.routes" :key="r.feature">{{ featureLabels[r.feature] ?? r.feature }}：{{ r.model || '未配置' }} · {{ selectionSource(r.source) }}</p></template>
        </details>
        <h4>课程处理 · 冻结选择</h4>
        <p v-if="!usage.pipeline.length">未记录</p>
        <article v-for="s in usage.pipeline" :key="s.snapshotId ?? ''">
          <p>快照 {{ s.snapshotId }} · v{{ s.configVersion }} · {{ s.origin === 'ADOPTED' ? '接管时冻结（非创建时）' : s.origin === 'CREATED' ? '创建时冻结' : '冻结时机未记录' }} · {{ s.recordedAt }}</p>
          <p v-for="r in s.routes.filter(r => r.feature !== 'COURSE_QA')" :key="r.feature">{{ featureLabels[r.feature] ?? r.feature }}：{{ r.model || '未配置' }} · {{ selectionSource(r.source) }} · 已选择，是否调用请核对记录</p>
        </article>
        <h4>普通 QA · 最近 50 条已保存记录</h4>
        <p v-if="!usage.qa.length">未记录</p>
        <article v-for="q in usage.qa" :key="q.recordId">
          <p>QA #{{ q.recordId }} · {{ q.recordedAt }} · {{ q.status }} · {{ invocationLabel(q.invocationState) }}</p>
          <p v-if="q.selection">快照 {{ q.selection.snapshotId }} · 系统版本 v{{ q.selection.configVersion }} · {{ q.selection.routes[0]?.model || '未记录' }} · {{ selectionSource(q.selection.routes[0]?.source ?? '') }}</p><p v-else>冻结配置：未记录</p>
          <p>响应记录：{{ q.provider || '未记录' }} / {{ q.model || '未记录' }} · Token：{{ q.totalTokens ?? '未知' }} · 调用记录 ID：{{ q.callRecordId || '未记录' }}</p>
        </article>
        <h4>课程调用台账 · 最近 100 条逻辑调用</h4>
        <p>STARTED 表示本地登记；不证明供应商已收到请求。本地 Mock 是确定性输出，不代表真实模型调用。台账未保存快照关联时，不按时间推断。物理重试次数和未记录的跳过原因未知。</p>
        <p v-if="!usage.calls.length">未记录</p>
        <p v-for="c in usage.calls" :key="c.recordId">#{{ c.recordId }} · {{ featureLabels[c.stage] ?? c.stage }} · {{ c.provider }} / {{ c.model || '未记录' }} · {{ c.status }} · {{ c.startedAt }} · Token：{{ c.totalTokens ?? '未知' }}</p>
        <ModelEvidence />
        <p>Agent decision / review 的冻结配置与逐次调用见该次 Run 的 Trace。打开此卡不发起模型发现或兼容探测。</p>
      </template>
    </div>
  </section>
</template>
<style scoped>
.model-usage { padding: 16px; margin-top: 16px; border: 1px solid var(--color-border); border-radius: var(--radius-md); overflow-wrap: anywhere; background: var(--color-surface); }.model-usage p { line-height: 1.7; }.model-usage article { border-bottom: 1px solid var(--color-border); padding: 8px 0; }.model-usage summary { cursor: pointer; }
</style>
