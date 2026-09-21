<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
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
  loading.value = true; opened.value = true; error.value = "";
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
function details(event: StudyEvent) {
  const fields = ["tool", "call_id", "purpose", "attempt", "duration_ms", "prompt_tokens", "completion_tokens", "input_tokens", "output_tokens", "accepted", "status", "error_code"];
  return fields.filter(key => event.payload[key] !== undefined).map(key => `${key}: ${String(event.payload[key])}`).join(" · ");
}
</script>
<template>
  <section class="run-trace" aria-label="Agent Trace">
    <el-button :loading="loading" @click="load">{{ opened ? '刷新 Trace' : 'View Trace · 查看执行链路' }}</el-button>
    <div v-if="opened">
      <h3>Agent Trace</h3>
      <p>Run ID：<code>{{ run.run_id }}</code> · {{ run.status }}</p>
      <p>Question：{{ run.goal }}</p>
      <p>模型调用：{{ run.model_calls }} · 工具调用：{{ run.tool_calls }}<span v-if="artifact"> · Revision：{{ artifact.revision }}</span></p>
      <p v-if="run.model_selection?.decision">Model：{{ run.model_selection.decision.model }}</p>
      <p>此视图读取已持久化的公开执行事件；完整诊断与 Replay 通过 Phase B 运维 CLI 查看。</p>
      <p v-if="error" role="alert">{{ error }}</p>
      <ol v-else><li v-for="event in events" :key="event.sequence"><strong>#{{ event.sequence }} {{ event.event_type }}</strong><p>{{ details(event) }}</p></li></ol>
      <div v-if="artifact && !error"><h4>Evidence → Final Answer</h4><p v-for="id in artifact.evidence_ids" :key="id"><code>{{ id }}</code></p><p>{{ artifact.explanation }}</p></div>
    </div>
  </section>
</template>
<style scoped>
.run-trace { margin-top: 20px; overflow-wrap: anywhere; }.run-trace div { padding: 16px; background: var(--color-canvas); border-radius: var(--radius-md); }.run-trace p { white-space: pre-wrap; line-height: 1.7; }.run-trace ol { padding-left: 22px; }.run-trace li { margin: 12px 0; }.run-trace code { font-size: 12px; }
</style>
