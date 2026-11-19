<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from "vue";
import { cancelTutorTurn, createTutorSession, getTutorSession, listTutorSessions, submitTutorTurn } from "../../api/tutor";
import type { TutorProviderMode, TutorSession, TutorView } from "../../api/tutor";
import type { Citation } from "../../api/study";
import { mayHaveLostCourseAccess } from "../../api/courseAccess";
import { randomUuid } from "../../utils/randomUuid";
import { formatMillisRange } from "../../utils/time";
import type { EvidenceSeekContext } from "./evidenceSeekGuard";

const props = defineProps<{ taskId: string; canNote?: boolean }>();
const emit = defineEmits<{ seek: [milliseconds: number, context: EvidenceSeekContext]; note: [milliseconds: number, context: EvidenceSeekContext]; accessFailure: [] }>();
const view = ref<TutorView | null>(null);
const sessions = ref<TutorSession[]>([]);
const providerMode = ref<TutorProviderMode>();
const draft = ref("");
const socratic = ref(false);
const busy = ref(false);
const loading = ref(true);
const error = ref("");
const blocked = ref(false);
const pending = ref<{ client_turn_id: string; text: string; socratic: boolean }>();
const activeTurn = computed(() => view.value?.turns.find(t => t.status === "queued" || t.status === "running"));
const exhausted = computed(() => !!view.value && (view.value.session.model_calls >= view.value.session.max_calls || view.value.turns.length >= (view.value.session.max_turns ?? 40)));
let epoch = 0;
let readSequence = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
let createKey = randomUuid();
let visible = true;

function fail(reason: unknown) {
  const response = (reason as { response?: { status?: number; data?: { message?: string } } })?.response;
  const definiteConflict = response?.status === 409;
  const sessionConflict = ["SESSION_BUSY", "REQUEST_KEY_CONFLICT", "TUTOR_SESSION_BUDGET"].includes(response?.data?.message ?? "");
  if (definiteConflict && sessionConflict) pending.value = undefined;
  if (mayHaveLostCourseAccess(reason) || (definiteConflict && !sessionConflict)) {
    ++readSequence; clearTimeout(timer);
    view.value = null; sessions.value = []; blocked.value = true; emit("accessFailure");
    error.value = "课程已更新或不可访问，请重新打开课程并开启新对话。";
  } else error.value = sessionConflict ? "本轮状态发生冲突或预算已用完，请重新读取对话后再发送。" : "Tutor 暂不可用。可重新读取；发送结果未知时请重试同一条消息。";
}
function apply(result: TutorView) {
  ++readSequence;
  view.value = result;
  providerMode.value = result.provider_mode;
  clearTimeout(timer);
  if (activeTurn.value && visible) timer = setTimeout(() => void refresh(), 700);
}
async function refresh() {
  const version = epoch, id = props.taskId, sid = view.value?.session.session_id;
  if (!sid || blocked.value) return;
  const sequence = ++readSequence;
  try {
    const result = await getTutorSession(id, sid);
    if (version === epoch && sequence === readSequence) apply(result);
  } catch (reason) { if (version === epoch && sequence === readSequence) fail(reason); }
}
async function restore() {
  const version = ++epoch;
  clearTimeout(timer); loading.value = true; error.value = "";
  try {
    const result = await listTutorSessions(props.taskId);
    if (version !== epoch) return;
    providerMode.value = result.provider_mode;
    sessions.value = result.sessions.filter(s => s.status === "active" && s.revision === result.revision);
    if (sessions.value[0]) {
      const data = await getTutorSession(props.taskId, sessions.value[0].session_id);
      if (version === epoch) apply(data);
    }
  } catch (reason) { if (version === epoch) fail(reason); }
  finally { if (version === epoch) loading.value = false; }
}
async function openSession(sid: string) {
  if (loading.value || busy.value || pending.value) return;
  const version = ++epoch; clearTimeout(timer); view.value = null; loading.value = true;
  try { const result = await getTutorSession(props.taskId, sid); if (version === epoch) apply(result); }
  catch (reason) { if (version === epoch) fail(reason); }
  finally { if (version === epoch) loading.value = false; }
}
function newConversation() {
  if (loading.value || busy.value || activeTurn.value || pending.value) return;
  epoch++; clearTimeout(timer); view.value = null; draft.value = ""; error.value = ""; createKey = randomUuid();
}
async function send() {
  if (loading.value || busy.value || activeTurn.value || blocked.value || exhausted.value) return;
  if (!pending.value) {
    if (!draft.value.trim()) return;
    pending.value = { client_turn_id: randomUuid(), text: draft.value.trim(), socratic: socratic.value };
  }
  const version = epoch, id = props.taskId, turn = pending.value;
  ++readSequence;
  busy.value = true; error.value = "";
  try {
    if (!view.value) {
      const created = await createTutorSession(id, createKey);
      if (version !== epoch) return;
      view.value = { session: created.session, turns: [] };
      sessions.value = [created.session, ...sessions.value.filter(s => s.session_id !== created.session.session_id)];
    }
    const result = await submitTutorTurn(id, view.value.session.session_id, turn);
    if (version !== epoch) return;
    pending.value = undefined; draft.value = ""; apply(result);
  } catch (reason) { if (version === epoch) fail(reason); }
  finally { if (version === epoch) busy.value = false; }
}
async function cancel() {
  if (!view.value || !activeTurn.value) return;
  const version = epoch;
  ++readSequence;
  try {
    const result = await cancelTutorTurn(props.taskId, view.value.session.session_id, activeTurn.value.client_turn_id);
    if (version === epoch) { pending.value = undefined; apply(result); }
  } catch (reason) { if (version === epoch) fail(reason); }
}
function parts(text: string, citations: Citation[]) {
  return text.split(/(\[[^\[\]\n]+\])/g).map(part => {
    const citation = citations.find(c => `[${c.evidence_id}]` === part);
    return { text: citation ? formatMillisRange(citation.start_ms, citation.end_ms) : part, citation };
  });
}
function seek(c: Citation, action: "seek" | "note" = "seek") {
  if (!view.value) return;
  const context = { evidenceId: c.evidence_id, revision: view.value.session.revision };
  if (action === "note") emit("note", c.start_ms, context);
  else emit("seek", c.start_ms, context);
}
watch(() => props.taskId, () => {
  view.value = null; sessions.value = []; providerMode.value = undefined; pending.value = undefined; draft.value = ""; busy.value = false;
  blocked.value = false; createKey = randomUuid(); void restore();
}, { immediate: true });
onActivated(() => { visible = true; void refresh(); });
onDeactivated(() => { visible = false; clearTimeout(timer); });
onBeforeUnmount(() => { epoch++; clearTimeout(timer); });
</script>

<template>
  <section class="tutor" aria-labelledby="tutor-title">
    <header><h2 id="tutor-title">Tutor</h2>
      <button :disabled="loading || busy || !!activeTurn || !!pending || blocked" @click="newConversation">新对话</button></header>
    <p v-if="providerMode === 'deepseek-flash'" class="boundary">DeepSeek 试学：提问、对话上下文和检索到的课程片段将发送给 DeepSeek。此试学共可生成最多 3 次，教学质量待评审。</p>
    <p v-else class="boundary">实验性 Mock 演示，仅验证对话流程；教学质量尚未经过真实模型验收。</p>
    <p v-if="view?.session.engine === 'light'" class="boundary">轻量 Tutor：每轮最多一次生成，最多六轮；完整保留本对话前提，超限或失败不自动重试。复杂问题请拆分提问。</p>
    <p v-if="loading" role="status">正在恢复对话…</p>
    <label v-if="sessions.length">已保存对话 <select :value="view?.session.session_id ?? ''" :disabled="loading || busy || !!pending" @change="openSession(($event.target as HTMLSelectElement).value)"><option disabled value="">选择对话</option><option v-for="(s, i) in sessions" :key="s.session_id" :value="s.session_id">对话 {{ sessions.length - i }}</option></select></label>
    <p v-if="error" role="alert">{{ error }} <button v-if="!blocked" @click="view ? refresh() : restore()">重新读取</button></p>
    <p v-if="!loading && !error && !view?.turns.length" class="tutor-empty">可以从课程中的概念、步骤或例子问起。</p>
    <ol v-if="view?.turns.length" class="messages" aria-live="polite">
      <li v-for="turn in view?.turns ?? []" :key="turn.turn_id">
        <p class="learner"><strong>你</strong> {{ turn.learner_text }}</p>
        <div v-if="turn.status === 'completed'" class="answer" :class="{ insufficient: turn.outcome === 'insufficient_evidence' }">
          <strong>{{ turn.outcome === 'socratic_prompt' ? 'Tutor · 引导思考' : 'Tutor' }}</strong>
          <p v-if="turn.outcome === 'insufficient_evidence'">我不知道：当前课程没有足够证据回答这个问题。可换一个课程已讲授的问题。</p>
          <p v-else><template v-for="(part, i) in parts(turn.answer ?? '', turn.citations)" :key="i"><button v-if="part.citation" class="citation" :title="`Evidence ${part.citation.evidence_id}`" :aria-label="`定位出处 ${part.text}`" @click="seek(part.citation)">{{ part.text }}</button><span v-else>{{ part.text }}</span></template></p>
          <p v-if="turn.evaluation"><strong>对你的回复：</strong><template v-for="(part, i) in parts(turn.evaluation, turn.citations)" :key="i"><button v-if="part.citation" class="citation" :title="`Evidence ${part.citation.evidence_id}`" :aria-label="`定位出处 ${part.text}`" @click="seek(part.citation)">{{ part.text }}</button><span v-else>{{ part.text }}</span></template></p>
          <details v-if="turn.citations.length"><summary>核对课程原文</summary><blockquote v-for="c in turn.citations" :key="c.evidence_id"><p>{{ c.text }}</p><div class="citation-actions"><button class="citation" @click="seek(c)">定位出处 {{ formatMillisRange(c.start_ms, c.end_ms) }}</button><button v-if="canNote" type="button" @click="seek(c, 'note')">记下这一段</button></div></blockquote></details>
        </div>
        <p v-else-if="turn.status === 'failed' || turn.status === 'cancelled'" role="status">{{ turn.status === 'cancelled' ? '已取消。' : '本轮未完成，未发布回答。可开启下一轮或新对话。' }} <code v-if="turn.status === 'failed' && turn.error_code">{{ turn.error_code }}</code></p>
        <p v-else role="status">Tutor 正在查找课程证据… <button @click="cancel">取消</button></p>
      </li>
    </ol>
    <p v-if="exhausted">本对话预算已用完，请开启新对话。</p>
    <form class="tutor-compose" @submit.prevent="send">
      <label><input v-model="socratic" type="checkbox" :disabled="busy || !!pending" /> Socratic · 用问题引导我</label>
      <label for="tutor-message">向课程 Tutor 提问</label>
      <textarea id="tutor-message" v-model="draft" maxlength="2000" rows="3" :disabled="busy || !!pending || blocked" placeholder="可以继续追问：为什么？能举个例子吗？" />
      <button type="submit" :disabled="busy || !!activeTurn || loading || blocked || exhausted || (!pending && !draft.trim())">{{ pending ? '重试同一条消息' : '发送' }}</button>
    </form>
  </section>
</template>

<style scoped>
.tutor { display: grid; gap: 14px; min-width: 0; padding: 20px; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); }
header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
h2, p { margin: 0; }
.boundary { color: var(--color-ink-soft); font-size: 13px; line-height: 1.6; }
.tutor-empty { padding: 16px; border-radius: var(--radius-md); background: var(--color-canvas); color: var(--color-ink-soft); }
button, select, textarea { font: inherit; color: var(--color-ink); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 8px 12px; }
button { cursor: pointer; }
button:disabled { opacity: .55; cursor: default; }
.tutor-compose { display: grid; gap: 10px; padding-top: 16px; border-top: 1px solid var(--color-border); }
.tutor-compose label[for] { font-weight: 650; }
textarea { min-width: 0; resize: vertical; line-height: 1.65; font-size: 16px; }
.tutor-compose button[type="submit"] { justify-self: end; color: white; background: var(--color-brand); border-color: var(--color-brand); }
.messages { list-style: none; padding: 0; margin: 0; display: grid; gap: 20px; }
.messages li { display: grid; gap: 12px; }
.learner, .answer { line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
.learner { justify-self: end; max-width: min(94%, 40ch); padding: 12px 16px; border-radius: var(--radius-lg); background: var(--color-brand-soft); }
.answer { display: grid; gap: 8px; }
.insufficient { padding-inline-start: 12px; border-inline-start: 3px solid var(--color-ink-soft); }
.citation { padding: 3px 7px; margin-inline: 2px; color: var(--color-warning); background: var(--color-evidence-surface); font-size: 13px; font-variant-numeric: tabular-nums; }
.citation-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
blockquote { margin: 10px 0; padding: 10px 12px; border-inline-start: 2px solid var(--color-warning); }
summary { width: fit-content; cursor: pointer; color: var(--color-brand-strong); }
@media (max-width: 1024px) { button { min-height: 44px; } }
</style>
