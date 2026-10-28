<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { dueCards, studyCommand, studyStatus } from "../../api/study";
import type { DueCards, StudyCommand } from "../../api/study";
import { mayHaveLostCourseAccess } from "../../api/courseAccess";
import { randomUuid } from "../../utils/randomUuid";
import { formatMillisRange } from "../../utils/time";
import type { EvidenceSeekContext } from "./evidenceSeekGuard";

const props = defineProps<{ taskId: string }>();
const emit = defineEmits<{ seek: [milliseconds: number, context: EvidenceSeekContext]; accessFailure: [] }>();
const data = ref<DueCards | null>(null);
const flipped = ref(false);
const loading = ref(false);
const busy = ref(false);
const enabled = ref(false);
const error = ref("");
const notice = ref("");
const current = computed(() => data.value?.cards[0]);
const generating = computed(() => ["queued", "running"].includes(data.value?.generation?.status ?? ""));
let epoch = 0;
let readSequence = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
const pendingReview = ref<StudyCommand>();
let generationKeys: { session: string; request: string } | undefined;

function fail(reason: unknown) {
  if (mayHaveLostCourseAccess(reason)) {
    data.value = null; enabled.value = false; emit("accessFailure");
    error.value = "课程已更新或不可访问，请重新打开课程。";
  } else error.value = "操作未完成。评分冲突时已重新读取进度；网络中断可重试同一次请求。";
}
async function refresh() {
  const version = epoch, id = props.taskId, sequence = ++readSequence;
  clearTimeout(timer);
  try {
    const result = await dueCards(id);
    if (version !== epoch || sequence !== readSequence) return;
    if (result.cards[0]?.card_id !== current.value?.card_id || result.cards[0]?.version !== current.value?.version) flipped.value = false;
    data.value = result;
    if (["queued", "running"].includes(result.generation?.status ?? "")) timer = setTimeout(() => void refresh(), 1000);
  } catch (reason) { if (version === epoch && sequence === readSequence) fail(reason); }
}
async function generate() {
  if (busy.value || generating.value || !enabled.value) return;
  busy.value = true; error.value = ""; notice.value = "";
  const version = epoch, id = props.taskId;
  generationKeys ??= { session: randomUuid(), request: randomUuid() };
  const keys = generationKeys;
  try {
    const session = await studyCommand(id, { operation: "CREATE_SESSION", request_key: keys.session });
    if (version !== epoch) return;
    await studyCommand(id, { operation: "GENERATE_CARDS", session_id: session.session_id, request_key: keys.request });
    if (version !== epoch) return;
    generationKeys = undefined;
    await refresh();
  } catch (reason) { if (version === epoch) fail(reason); }
  finally { if (version === epoch) busy.value = false; }
}
async function cancelGeneration() {
  const run = data.value?.generation;
  if (!run || busy.value) return;
  const version = epoch;
  busy.value = true;
  try {
    await studyCommand(props.taskId, { operation: "CANCEL", session_id: run.session_id, run_id: run.run_id });
    if (version === epoch) await refresh();
  } catch (reason) { if (version === epoch) fail(reason); }
  finally { if (version === epoch) busy.value = false; }
}
async function rate(rating: "Again" | "Hard" | "Good" | "Easy") {
  if (!current.value || !flipped.value || busy.value || pendingReview.value) return;
  pendingReview.value = { operation: "REVIEW_CARD", card_id: current.value.card_id, rating,
    expected_version: current.value.version, request_key: randomUuid() };
  await submitReview();
}
async function submitReview() {
  const command = pendingReview.value;
  if (!command || busy.value) return;
  const version = epoch, id = props.taskId;
  busy.value = true; error.value = "";
  try {
    await studyCommand(id, command);
    if (version !== epoch) return;
    pendingReview.value = undefined; flipped.value = false;
    notice.value = "评分已保存，下次复习时间已安排。";
    await refresh();
  } catch (reason) {
    if (version !== epoch) return;
    // A definite conflict is safe to discard; unknown transport outcomes retain the replay key.
    const status = (reason as { response?: { status?: number } })?.response?.status;
    if (status === 409) pendingReview.value = undefined;
    fail(reason); await refresh();
  } finally { if (version === epoch) busy.value = false; }
}
function resume() { if (enabled.value && !busy.value) void refresh(); }
function onVisibility() { if (document.visibilityState === "visible") resume(); }
window.addEventListener("focus", resume);
document.addEventListener("visibilitychange", onVisibility);
watch(() => props.taskId, async () => {
  const version = ++epoch;
  ++readSequence; clearTimeout(timer);
  data.value = null; flipped.value = false; busy.value = false; enabled.value = false;
  pendingReview.value = undefined; generationKeys = undefined; error.value = ""; notice.value = ""; loading.value = true;
  try {
    const status = await studyStatus(props.taskId);
    if (version !== epoch) return;
    enabled.value = status.enabled;
    if (status.enabled) await refresh();
  } catch (reason) { if (version === epoch) fail(reason); }
  finally { if (version === epoch) loading.value = false; }
}, { immediate: true });
onBeforeUnmount(() => {
  epoch++; readSequence++; clearTimeout(timer);
  window.removeEventListener("focus", resume); document.removeEventListener("visibilitychange", onVisibility);
});
</script>

<template>
  <section class="flashcards" aria-labelledby="flashcards-title">
    <header><div><p class="eyebrow">课程证据 · 间隔复习</p><h2 id="flashcards-title">闪卡复习</h2></div>
      <button :disabled="!enabled || busy || generating || loading" @click="generate">生成一组证据闪卡</button></header>
    <p class="boundary">实验性 Mock 演示：固定内容只验证流程，不代表生成质量。评分是你的自评，FSRS 据此安排复习。</p>
    <p v-if="loading" role="status">正在恢复复习进度…</p>
    <p v-else-if="!enabled && !error">学习服务未启用，暂不能读取闪卡。</p>
    <p v-if="error" role="alert">{{ error }} <button :disabled="busy" @click="refresh">重新读取</button></p>
    <p v-if="pendingReview"><button :disabled="busy || !enabled" @click="submitReview">重试上次评分</button> 上次请求结果尚待确认，重试会沿用原评分。</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <div v-if="data" class="summary"><strong>今日待复习 {{ data.due_count }}</strong><span>今日已复习 {{ data.reviewed_today }} 张 · 共 {{ data.total_count }} 张</span><small>按 UTC 日统计，仅复习当前已到期卡片</small></div>
    <p v-if="generating" role="status">正在生成证据闪卡… <button :disabled="busy" @click="cancelGeneration">取消生成</button></p>
    <p v-else-if="data?.generation && data.generation.status !== 'succeeded'">上次生成{{ data.generation.status === 'cancelled' ? '已取消' : '未完成' }}，可重新生成。</p>
    <article v-if="current" class="card" :aria-busy="busy">
      <p class="eyebrow">{{ flipped ? '答案与出处' : '先回想，再翻面' }}</p>
      <h3>{{ current.front }}</h3>
      <template v-if="flipped"><p class="answer">{{ current.back }}</p>
        <details><summary>核对课程原文 · {{ current.citations.length }} 条证据</summary>
          <blockquote v-for="citation in current.citations" :key="citation.evidence_id"><p>{{ citation.text }}</p>
            <button @click="emit('seek', citation.start_ms, { evidenceId: citation.evidence_id, revision: current.revision })">回看视频 {{ formatMillisRange(citation.start_ms, citation.end_ms) }}</button></blockquote>
        </details>
        <div class="ratings" aria-label="回忆难度自评"><button v-for="rating in (['Again', 'Hard', 'Good', 'Easy'] as const)" :key="rating" :disabled="busy || !!pendingReview" @click="rate(rating)">{{ rating }}<small>{{ { Again: '再学一次', Hard: '比较困难', Good: '想起来了', Easy: '很轻松' }[rating] }}</small></button></div>
      </template>
      <button v-else class="flip" :disabled="busy" @click="flipped = true">翻面 · 显示答案</button>
    </article>
    <p v-else-if="data && !generating" class="empty">{{ data.total_count ? '当前复习已完成。' : '还没有闪卡，生成一组开始复习。' }}<span v-if="data.next_due_at">下次到期：{{ new Date(data.next_due_at).toLocaleString() }}</span></p>
  </section>
</template>

<style scoped>
.flashcards { padding: 24px; display: grid; gap: 18px; min-width: 0; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); }
header { display: flex; align-items: center; justify-content: space-between; gap: 16px; } h2,h3,p { margin: 0; } .eyebrow { color: var(--color-brand); font-size: 12px; margin-bottom: 8px; } .boundary,small { color: var(--color-ink-soft); font-size: 12px; line-height: 1.6; }
button { cursor: pointer; border: 1px solid var(--color-border); border-radius: 8px; padding: 10px 14px; background: var(--color-surface); color: var(--color-ink); font: inherit; } button:disabled { cursor: default; opacity: .55; } button:focus-visible { outline: 2px solid var(--color-brand); outline-offset: 3px; }
.summary { display: flex; gap: 8px 18px; flex-wrap: wrap; align-items: baseline; }.summary strong { font-size: 20px; }.summary small { width: 100%; }.card { display: grid; gap: 24px; padding: 30px; border: 1px solid var(--color-border); border-radius: 14px; min-height: 260px; background: var(--color-brand-soft, #edf4f0); }.card h3,.answer,blockquote { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.75; }.flip { justify-self: center; }.ratings { display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; }.ratings small { display: block; }.empty { padding: 30px 0; line-height: 2; }.empty span { display: block; } blockquote { margin: 14px 0; padding-left: 14px; border-left: 3px solid var(--color-brand); } details summary { cursor: pointer; }
</style>
