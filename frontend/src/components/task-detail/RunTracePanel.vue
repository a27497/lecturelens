<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import ModelEvidence from "./ModelEvidence.vue";
import { studyCommand } from "../../api/study";
import type { StudyArtifact, StudyEvent, StudyRun } from "../../api/study";
const props = defineProps<{ taskId: string; sessionId: string; run: StudyRun; artifact: StudyArtifact | null }>();
const opened = ref(false);
const loading = ref(false);
const error = ref("");
const events = ref<StudyEvent[]>([]);
let generation = 0;
watch(() => [props.taskId, props.sessionId, props.run.run_id], () => {
  generation++; opened.value = false; loading.value = false; error.value = ""; events.value = [];
});
onBeforeUnmount(() => { generation++; });
async function load() {
  if (loading.value) return;
  const current = generation;
  loading.value = true; opened.value = true; error.value = ""; events.value = [];
  const collected: StudyEvent[] = [];
  try {
    let after = 0;
    for (let page = 0; page < 20; page++) {
      const response = await studyCommand(props.taskId, { operation: "EVENTS", session_id: props.sessionId, run_id: props.run.run_id, after });
      if (current !== generation) return;
      const batch = response.events ?? [];
      collected.push(...batch);
      if (batch.length < 100) { events.value = collected; return; }
      const next = batch[batch.length - 1]!.sequence;
      if (next <= after) throw new Error("cursor");
      after = next;
    }
    throw new Error("limit");
  } catch { if (current === generation) { events.value = []; error.value = "Trace 暂不可用或课程状态已变化，请重新打开课程后重试。"; } }
  finally { if (current === generation) loading.value = false; }
}
// Project only the existing public event fields. Private model prompts and
// checkpoint contents remain in the Phase B operator CLI.
function callIdentity(event: StudyEvent) {
  const selection = event.payload.model_selection;
  if (!selection || typeof selection !== "object") return "按次模型身份：未记录";
  const s = selection as Record<string, unknown>;
  return `按次模型：${typeof s.model === 'string' ? s.model : '未记录'} · 连接版本：${typeof s.version === 'number' ? s.version : '未记录'}`;
}
function details(event: StudyEvent) {
  const fields = ["tool", "call_id", "purpose", "attempt", "duration_ms", "prompt_tokens", "completion_tokens", "input_tokens", "output_tokens", "accepted", "status", "error_code", "failure_category", "decision", "actor_id", "edited", "policy"];
  return fields.filter(key => event.payload[key] !== undefined).map(key => `${key}: ${String(event.payload[key])}`).join(" · ");
}
</script>
<template>
  <section class="run-trace" aria-label="Agent Trace">
    <el-button :loading="loading" @click="load">{{ opened ? '刷新 Trace' : 'View Trace · 查看执行链路' }}</el-button>
    <div v-if="opened">
      <h3>Agent Trace</h3>
      <template v-if="!loading && !error">
      <p>Run ID：<code>{{ run.run_id }}</code> · {{ run.status }}</p>
      <p>Question：{{ run.goal }}</p>
      <p>模型调用：{{ run.model_calls }} · 工具调用：{{ run.tool_calls }}<span v-if="artifact"> · Revision：{{ artifact.revision }}</span></p>
      <p>Run 创建时间：{{ run.created_at || '未记录' }} · 模式：{{ run.model_mode }}</p>
      <article v-for="role in (['decision', 'review'] as const)" :key="role">
        <h4>{{ role === 'decision' ? 'Agent decision' : 'Agent review' }} · 冻结选择</h4>
        <template v-if="run.model_selection?.[role]">
          <p>{{ run.model_selection[role]!.model }} · {{ run.model_selection[role]!.connection_id === null ? '服务器默认' : typeof run.model_selection[role]!.connection_id === 'string' ? '个人连接' : '来源未记录' }} · {{ run.model_selection[role]!.name }} · 连接版本标记 {{ run.model_selection[role]!.version }}<span v-if="run.model_selection[role]!.connection_id === null">（环境默认，无独立配置版本号）</span></p>
          <p>来自该 Run 保存的选择；编辑或删除当前连接不会重写此记录。已选择不代表已调用。</p>
          <ModelEvidence :single-turn="run.model_selection[role]!.single_turn_evidence" :model="run.model_selection[role]!.model" :version="run.model_selection[role]!.version" :mock="run.model_mode === 'mock'" />
        </template>
        <p v-else>冻结配置：未记录</p>
      </article>
      <p>此视图读取已持久化的公开执行事件；完整诊断与 Replay 通过 Phase B 运维 CLI 查看。</p>
      </template>
      <p v-if="error" role="alert">{{ error }}</p>
      <ol v-else><li v-for="event in events" :key="event.sequence"><strong>#{{ event.sequence }} {{ event.event_type }}</strong><p>{{ details(event) }}</p><p v-if="['model_started', 'model_finished', 'model_failed', 'model_replayed'].includes(event.event_type)">{{ callIdentity(event) }} · {{ event.event_type === 'model_replayed' ? '重放已保存结果，非新调用' : event.event_type === 'model_started' ? '本地调用开始，不证明供应商接收' : '本地调用结果' }} · 输入 Token：{{ event.payload.prompt_tokens ?? '未知' }} · 输出 Token：{{ event.payload.completion_tokens ?? '未知' }}</p></li></ol>
      <div v-if="artifact && !error"><h4>Evidence → Final Answer</h4><p v-for="id in artifact.evidence_ids" :key="id"><code>{{ id }}</code></p><p>{{ artifact.explanation }}</p></div>
    </div>
  </section>
</template>
<style scoped>
.run-trace { margin-top: 20px; overflow-wrap: anywhere; }.run-trace div { padding: 16px; background: var(--color-canvas); border-radius: var(--radius-md); }.run-trace p { white-space: pre-wrap; line-height: 1.7; }.run-trace ol { padding-left: 22px; }.run-trace li { margin: 12px 0; }.run-trace code { font-size: 12px; }
</style>
