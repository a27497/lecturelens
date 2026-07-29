<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import {
  downloadTaskKeyframeImage,
  isTaskResultAuthError,
  toReadableKeyframeImageError,
} from "../../api/result";
import type { ResultKeyframe, ResultVideoSegment } from "../../types/result";
import { formatMillisToClock } from "../../utils/time";

type ImageStatus = "loading" | "loaded" | "failed";

interface KeyframeImageState {
  status: ImageStatus;
  url: string;
  errorMessage: string;
  retryable: boolean;
}

const PAGE_SIZE = 8;
const OCR_PREVIEW_LENGTH = 480;

const props = defineProps<{
  taskId: string;
  keyframes: ResultKeyframe[];
  videoSegments: ResultVideoSegment[];
}>();

const emit = defineEmits<{
  seek: [startTimeMillis: number];
}>();

const page = ref(1);
const imageStates = reactive(new Map<number, KeyframeImageState>());
const requestTokens = new Map<number, number>();
const requestControllers = new Map<number, AbortController>();
let nextRequestToken = 0;

const sortedKeyframes = computed(() => [...props.keyframes]
  .sort((left, right) => left.timestampMillis - right.timestampMillis || left.frameId - right.frameId));
const pageCount = computed(() => Math.max(1, Math.ceil(sortedKeyframes.value.length / PAGE_SIZE)));
const pageKeyframes = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE;
  return sortedKeyframes.value.slice(start, start + PAGE_SIZE);
});
const asrBackedFrameIds = computed(() => {
  const result = new Set<number>();
  for (const segment of props.videoSegments) {
    if (!segment.asrText?.trim()) continue;
    for (const frameId of segment.evidence?.keyframeIds ?? []) result.add(frameId);
  }
  return result;
});

watch(() => props.taskId, () => {
  page.value = 1;
  clearAllImages();
  for (const frame of pageKeyframes.value) void loadImage(frame);
});

watch(sortedKeyframes, () => {
  page.value = Math.min(page.value, pageCount.value);
}, { immediate: true });

watch(pageKeyframes, (frames) => {
  const visibleFrameIds = new Set(frames.map((frame) => frame.frameId));
  for (const frameId of [...imageStates.keys()]) {
    if (!visibleFrameIds.has(frameId)) clearImage(frameId);
  }
  for (const frame of frames) {
    if (!imageStates.has(frame.frameId)) void loadImage(frame);
  }
}, { immediate: true });

onBeforeUnmount(clearAllImages);

function stateFor(frameId: number): KeyframeImageState {
  let state = imageStates.get(frameId);
  if (!state) {
    state = { status: "loading", url: "", errorMessage: "", retryable: true };
    imageStates.set(frameId, state);
  }
  return state;
}

async function loadImage(frame: ResultKeyframe) {
  clearImage(frame.frameId);
  const state: KeyframeImageState = {
    status: "loading",
    url: "",
    errorMessage: "",
    retryable: true,
  };
  imageStates.set(frame.frameId, state);
  const requestToken = ++nextRequestToken;
  const controller = new AbortController();
  const taskId = props.taskId;
  requestTokens.set(frame.frameId, requestToken);
  requestControllers.set(frame.frameId, controller);
  try {
    const blob = await downloadTaskKeyframeImage(taskId, frame.frameId, controller.signal);
    if (requestTokens.get(frame.frameId) !== requestToken || props.taskId !== taskId) return;
    imageStates.set(frame.frameId, {
      status: "loaded",
      url: URL.createObjectURL(blob),
      errorMessage: "",
      retryable: false,
    });
  } catch (error) {
    if (controller.signal.aborted) return;
    if (requestTokens.get(frame.frameId) !== requestToken || props.taskId !== taskId) return;
    imageStates.set(frame.frameId, {
      status: "failed",
      url: "",
      errorMessage: toReadableKeyframeImageError(error),
      retryable: !isTaskResultAuthError(error),
    });
  } finally {
    if (requestControllers.get(frame.frameId) === controller) {
      requestControllers.delete(frame.frameId);
    }
  }
}

function clearImage(frameId: number) {
  requestTokens.delete(frameId);
  requestControllers.get(frameId)?.abort();
  requestControllers.delete(frameId);
  const state = imageStates.get(frameId);
  if (state?.url) URL.revokeObjectURL(state.url);
  imageStates.delete(frameId);
}

function clearAllImages() {
  for (const frameId of [...imageStates.keys()]) clearImage(frameId);
}

function sourceLabels(frame: ResultKeyframe): string[] {
  const labels: string[] = [];
  if (frame.ocr?.status === "SUCCEEDED" && frame.ocr.text?.trim()) labels.push("OCR");
  if (frame.visualAnalysis?.status === "SUCCEEDED" && frame.visualAnalysis.summary?.trim()) labels.push("视觉分析");
  if (asrBackedFrameIds.value.has(frame.frameId)) labels.push("ASR+画面");
  return labels.length > 0 ? labels : ["关键帧"];
}

function frameTime(frame: ResultKeyframe): string {
  return frame.timeText?.trim() || formatMillisToClock(frame.timestampMillis);
}

function ocrPreview(text: string): string {
  const normalized = text.trim();
  return normalized.length <= OCR_PREVIEW_LENGTH
    ? normalized
    : `${normalized.slice(0, OCR_PREVIEW_LENGTH)}…`;
}

function previousPage() {
  page.value = Math.max(1, page.value - 1);
}

function nextPage() {
  page.value = Math.min(pageCount.value, page.value + 1);
}
</script>

<template>
  <section class="visual-evidence" aria-label="画面证据">
    <div class="visual-evidence__intro">
      <div>
        <h3>画面证据</h3>
        <p>查看课程中的关键画面、识别文字和视觉摘要。点击图片或时间可跳到原视频。</p>
      </div>
      <span>{{ sortedKeyframes.length }} 张</span>
    </div>

    <div class="visual-evidence__grid">
      <article v-for="frame in pageKeyframes" :key="`${taskId}-${frame.frameId}`" class="evidence-card">
        <div class="evidence-card__media">
          <div v-if="stateFor(frame.frameId).status === 'loading'" class="evidence-card__loading" aria-live="polite">
            <span class="evidence-card__spinner" aria-hidden="true" />
            <span>画面加载中</span>
          </div>
          <div v-else-if="stateFor(frame.frameId).status === 'failed'" class="evidence-card__error" role="status">
            <span>{{ stateFor(frame.frameId).errorMessage }}</span>
            <button
              v-if="stateFor(frame.frameId).retryable"
              type="button"
              :data-testid="`retry-frame-${frame.frameId}`"
              @click="loadImage(frame)"
            >重试</button>
          </div>
          <button
            v-else
            type="button"
            class="evidence-card__image-button"
            :aria-label="`跳到视频 ${frameTime(frame)}`"
            :data-testid="`image-frame-${frame.frameId}`"
            @click="emit('seek', frame.timestampMillis)"
          >
            <img
              :src="stateFor(frame.frameId).url"
              :alt="`${frameTime(frame)} 的课程关键画面`"
              loading="lazy"
            />
          </button>
        </div>

        <div class="evidence-card__body">
          <div class="evidence-card__heading">
            <button
              type="button"
              class="evidence-card__time"
              :data-testid="`seek-frame-${frame.frameId}`"
              @click="emit('seek', frame.timestampMillis)"
            >
              {{ frameTime(frame) }}
            </button>
            <div class="evidence-card__tags" aria-label="证据来源">
              <span v-for="label in sourceLabels(frame)" :key="label">{{ label }}</span>
            </div>
          </div>

          <div v-if="frame.ocr?.status === 'SUCCEEDED' && frame.ocr.text" class="evidence-card__copy">
            <strong>画面文字</strong>
            <p>{{ ocrPreview(frame.ocr.text) }}</p>
          </div>
          <div v-if="frame.visualAnalysis?.status === 'SUCCEEDED' && frame.visualAnalysis.summary" class="evidence-card__copy">
            <strong>{{ frame.visualAnalysis.screenType || "画面" }} 摘要</strong>
            <p>{{ frame.visualAnalysis.summary }}</p>
          </div>
        </div>
      </article>
    </div>

    <nav v-if="pageCount > 1" class="visual-evidence__pagination" aria-label="画面证据分页">
      <button type="button" :disabled="page === 1" @click="previousPage">上一页</button>
      <span>第 {{ page }} / {{ pageCount }} 页</span>
      <button type="button" :disabled="page === pageCount" @click="nextPage">下一页</button>
    </nav>
  </section>
</template>

<style scoped>
.visual-evidence { display: grid; gap: 18px; min-width: 0; }
.visual-evidence__intro { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.visual-evidence__intro h3, .visual-evidence__intro p { margin: 0; }
.visual-evidence__intro p { margin-top: 6px; color: var(--color-ink-soft); line-height: 1.6; }
.visual-evidence__intro > span { flex: 0 0 auto; color: var(--color-ink-muted); font-size: 13px; }
.visual-evidence__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.evidence-card { overflow: hidden; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); }
.evidence-card__media { aspect-ratio: 16 / 9; background: #111827; }
.evidence-card__loading, .evidence-card__error { display: flex; width: 100%; height: 100%; align-items: center; justify-content: center; flex-direction: column; gap: 10px; padding: 16px; color: #e5e7eb; text-align: center; }
.evidence-card__spinner { width: 24px; height: 24px; border: 3px solid rgb(255 255 255 / 32%); border-top-color: #ffffff; border-radius: 50%; animation: evidence-spin .8s linear infinite; }
.evidence-card__error button, .visual-evidence__pagination button { padding: 7px 12px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); color: var(--color-ink); font: inherit; cursor: pointer; }
.evidence-card__image-button { display: block; width: 100%; height: 100%; padding: 0; border: 0; background: transparent; cursor: pointer; }
.evidence-card__image-button img { display: block; width: 100%; height: 100%; object-fit: contain; }
.evidence-card__body { display: grid; gap: 12px; padding: 14px; }
.evidence-card__heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
.evidence-card__time { padding: 0; border: 0; background: transparent; color: var(--color-brand); font: 700 13px/1.4 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; cursor: pointer; }
.evidence-card__tags { display: flex; flex-wrap: wrap; gap: 6px; }
.evidence-card__tags span { padding: 3px 7px; border-radius: 999px; background: var(--color-brand-soft, #edf4f0); color: var(--color-brand); font-size: 11px; font-weight: 700; }
.evidence-card__copy { display: grid; gap: 4px; min-width: 0; }
.evidence-card__copy strong { color: var(--color-ink); font-size: 13px; }
.evidence-card__copy p { display: -webkit-box; margin: 0; overflow: hidden; color: var(--color-ink-soft); line-height: 1.6; overflow-wrap: anywhere; -webkit-box-orient: vertical; -webkit-line-clamp: 4; }
.visual-evidence__pagination { display: flex; align-items: center; justify-content: center; gap: 14px; color: var(--color-ink-soft); font-size: 13px; }
.visual-evidence__pagination button:disabled { cursor: not-allowed; opacity: .45; }
@keyframes evidence-spin { to { transform: rotate(360deg); } }
@media (max-width: 680px) { .visual-evidence__grid { grid-template-columns: 1fr; }.visual-evidence__intro { flex-direction: column; gap: 8px; } }
</style>
