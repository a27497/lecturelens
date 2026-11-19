<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { FullScreen, Mute, VideoPause, VideoPlay } from "@element-plus/icons-vue";
import { createTimeIndex } from "../utils/timeIndex";
import type { SeekRequest } from "./task-detail/courseLocation";
import { parseVttCues } from "../utils/vtt";
import { formatApiTimestamp, formatSecondsToClock } from "../utils/time";

type SubtitleStatus = "none" | "loading" | "loaded" | "not_found" | "unsupported" | "failed";

const props = defineProps<{
  compact?: boolean;
  lesson?: boolean;
  inactive?: boolean;
  seekRequest?: SeekRequest;
  title: string;
  description?: string;
  playbackUrl: string;
  loading: boolean;
  errorMessage: string;
  expiresAt?: string;
  subtitleTrackUrl?: string;
  subtitleLabel?: string;
  subtitleText?: string;
  subtitleLanguage?: string;
  subtitleStatus?: SubtitleStatus;
  subtitleMessage?: string;
}>();

const emit = defineEmits<{
  position: [milliseconds: number];
  manualSeek: [];
  refresh: [];
}>();

const currentTime = ref(0);
const videoErrorMessage = ref("");
const videoRef = ref<HTMLVideoElement | null>(null);
const shell = ref<HTMLElement>();
const playing = ref(false);
const muted = ref(false);
const captions = ref(false);
const duration = ref(0);
const clock = (seconds: number) => formatSecondsToClock(seconds).replace(/^00:/, "");
const sliderProgress = computed(() => duration.value ? Math.min(100, currentTime.value * 100 / duration.value) : 0);

function togglePlay() {
  const video = videoRef.value;
  if (!video || props.inactive) return;
  if (video.paused) void video.play().catch(() => { videoErrorMessage.value = "视频暂时无法播放，请重试。"; });
  else video.pause();
}
function updatePlaybackState(event: Event) {
  const video = event.currentTarget as HTMLVideoElement;
  playing.value = !video.paused && !video.ended;
  muted.value = video.muted;
}
function toggleMuted() {
  if (videoRef.value) videoRef.value.muted = !videoRef.value.muted;
}
function updateCaptions() {
  const track = videoRef.value?.textTracks[0];
  if (props.lesson && track) track.mode = captions.value ? "showing" : "hidden";
}
watch(() => props.subtitleTrackUrl, () => { void nextTick(updateCaptions); });
function scrub(event: Event) {
  emit("manualSeek");
  seekTo(Number((event.target as HTMLInputElement).value));
}
async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else if (shell.value?.requestFullscreen) await shell.value.requestFullscreen();
    else (videoRef.value as (HTMLVideoElement & { webkitEnterFullscreen?: () => void }) | null)?.webkitEnterFullscreen?.();
  } catch { /* The player remains available inline if fullscreen is denied. */ }
}
const pendingSeekSeconds = ref<number | null>(null);
const subtitleCues = computed(() => parseVttCues(props.subtitleText || ""));
const subtitleIndex = computed(() => createTimeIndex(subtitleCues.value, cue => cue.start, cue => cue.end));
const activeSubtitleText = computed(() => subtitleIndex.value(currentTime.value)?.text ?? "");
let lastReport = -Infinity;
let resumeAfterReload = false;
let hasPosition = false;
let programmedSeekTarget: number | null = null;
const resolvedSubtitleLabel = computed(() => props.subtitleLabel || "原视频自带字幕");
const resolvedSubtitleStatus = computed<SubtitleStatus>(() => props.subtitleStatus || "none");
const subtitleStatusText = computed(() => {
  if (props.subtitleMessage) {
    return props.subtitleMessage;
  }
  switch (resolvedSubtitleStatus.value) {
    case "loading":
      return `${resolvedSubtitleLabel.value}：检测中`;
    case "loaded":
      return `${resolvedSubtitleLabel.value}：已加载`;
    case "not_found":
      return `${resolvedSubtitleLabel.value}：未检测到`;
    case "unsupported":
      return `${resolvedSubtitleLabel.value}：暂不支持该字幕格式`;
    case "failed":
      return `${resolvedSubtitleLabel.value}加载失败`;
    default:
      return `${resolvedSubtitleLabel.value}：未检测到`;
  }
});

watch(() => props.playbackUrl, () => {
  // A refreshed token creates a new media element. Keep its coordinate and explicit play intent.
  if (videoRef.value) resumeAfterReload = !props.inactive && !videoRef.value.paused && !videoRef.value.ended;
  if (pendingSeekSeconds.value === null && hasPosition) pendingSeekSeconds.value = currentTime.value;
  videoErrorMessage.value = "";
});
watch(() => props.seekRequest, request => {
  if (!request) return;
  if (request.pause) pausePlayback();
  seekTo(request.milliseconds / 1000);
}, { immediate: true });
// v-show/CSS keep the media instance alive. Hidden controls must never leave audio running.
watch(() => props.inactive, inactive => { if (inactive) pausePlayback(); }, { flush: "sync" });
onBeforeUnmount(pausePlayback);

function pausePlayback() {
  resumeAfterReload = false;
  videoRef.value?.pause();
}
function guardPlayback() {
  // A pending play() or refreshed source can finish after the workspace became hidden.
  if (props.inactive) pausePlayback();
}

function reportPosition(force = false) {
  const now = performance.now();
  if (!force && now - lastReport < 250) return;
  lastReport = now;
  emit("position", Math.round(currentTime.value * 1000));
}

function updateCurrentTime(event: Event) {
  // Ignore pre-seek events from newly loaded metadata and detached media elements.
  if (event.currentTarget !== videoRef.value || pendingSeekSeconds.value !== null) return;
  const seconds = (event.currentTarget as HTMLVideoElement).currentTime;
  if (!Number.isFinite(seconds) || seconds < 0) return;
  currentTime.value = seconds;
  hasPosition = true;
  reportPosition(event.type !== "timeupdate");
}

function seekTo(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return;
  pendingSeekSeconds.value = seconds;
  if (props.playbackUrl && videoRef.value && videoRef.value.readyState > 0) applyPendingSeek();
}

function handleLoadedMetadata(event: Event) {
  const length = (event.currentTarget as HTMLVideoElement).duration;
  duration.value = Number.isFinite(length) ? length : 0;
  updateCaptions();
  videoErrorMessage.value = "";
  if (pendingSeekSeconds.value !== null) applyPendingSeek();
  else updateCurrentTime(event);
  if (resumeAfterReload && !props.inactive && videoRef.value) {
    resumeAfterReload = false;
    void videoRef.value.play().catch(() => undefined);
  }
}

function handleSeeking(event: Event) {
  if (!videoRef.value || event.currentTarget !== videoRef.value || pendingSeekSeconds.value !== null) return;
  const seconds = videoRef.value.currentTime;
  // Native controls can swallow input events. Distinguish their seeks from our own restoration/navigation.
  if (programmedSeekTarget !== null && Math.abs(seconds - programmedSeekTarget) < 0.001) return;
  programmedSeekTarget = null;
  emit("manualSeek");
}

function handleSeeked(event: Event) {
  if (event.currentTarget !== videoRef.value) return;
  programmedSeekTarget = null;
  updateCurrentTime(event);
}

function clearVideoError() {
  videoErrorMessage.value = "";
}

function handleVideoError(event: Event) {
  const error = (event.currentTarget as HTMLVideoElement).error;
  if (!error || error.code === 1) {
    videoErrorMessage.value = "";
    return;
  }
  if (error.code === 2) {
    videoErrorMessage.value = "视频网络或播放链接异常，请刷新后重试。";
  } else if (error.code === 3) {
    videoErrorMessage.value = "浏览器无法解码该视频。";
  } else if (error.code === 4) {
    videoErrorMessage.value = "浏览器不支持该视频编码或格式。";
  } else {
    videoErrorMessage.value = "视频播放失败，请刷新后重试。";
  }
}

function applyPendingSeek() {
  if (!videoRef.value || pendingSeekSeconds.value === null) return;
  const duration = videoRef.value.duration;
  const target = Number.isFinite(duration) ? Math.min(pendingSeekSeconds.value, Math.max(0, duration)) : pendingSeekSeconds.value;
  programmedSeekTarget = target;
  try { videoRef.value.currentTime = target; }
  catch { programmedSeekTarget = null; return; } // Metadata can precede a seekable resource; canplay retries the same request.
  pendingSeekSeconds.value = null;
  currentTime.value = target;
  hasPosition = true;
  reportPosition(true);
}

defineExpose({
  seekTo,
});
</script>

<template>
  <section class="video-card" aria-label="视频播放">
    <div v-if="!compact || !playbackUrl" class="video-card__header">
      <div>
        <h2>{{ title }}</h2>
        <p v-if="!compact">{{ description }}</p>
      </div>
      <el-button :loading="loading" @click="$emit('refresh')">刷新播放链接</el-button>
    </div>

    <div v-if="lesson && loading && !playbackUrl" class="lesson-video-skeleton" aria-label="正在加载视频" role="status" />
    <el-skeleton v-else-if="loading && !playbackUrl" :rows="3" animated />

    <el-alert
      v-if="errorMessage"
      :closable="false"
      :title="errorMessage"
      show-icon
      type="warning"
    />

    <el-alert
      v-if="videoErrorMessage"
      :closable="false"
      :title="videoErrorMessage"
      show-icon
      type="warning"
    />

    <div v-if="playbackUrl" ref="shell" class="video-card__player-shell" :class="{ 'video-card__player-shell--lesson': lesson }">
      <video
      :aria-label="title"
      ref="videoRef"
      class="course-video-player"
      :src="playbackUrl"
      :controls="!lesson"
      playsinline
      :preload="lesson ? 'auto' : 'metadata'"
      @loadedmetadata="handleLoadedMetadata"
      @play="guardPlayback(); updatePlaybackState($event)"
      @playing="updatePlaybackState"
      @volumechange="updatePlaybackState"
      @click="lesson && togglePlay()"
      @canplay="clearVideoError(); applyPendingSeek()"
      @error="handleVideoError"
      @seeking="handleSeeking"
      @seeked="handleSeeked"
      @timeupdate="updateCurrentTime"
      @pause="updateCurrentTime($event); updatePlaybackState($event)"
      @ended="updateCurrentTime($event); updatePlaybackState($event)"
    >
        <track
          v-if="subtitleTrackUrl"
          kind="subtitles"
          :src="subtitleTrackUrl"
          :srclang="subtitleLanguage || 'und'"
          :label="resolvedSubtitleLabel"
          :default="!lesson"
        />
      </video>
      <div v-if="activeSubtitleText && !subtitleTrackUrl && (!lesson || captions)" class="video-card__subtitle-overlay">
        {{ activeSubtitleText }}
      </div>
      <div v-if="lesson" class="lesson-controls">
        <input class="lesson-scrubber" type="range" min="0" :max="duration || 1" step="0.1" :value="currentTime"
          :disabled="!duration" aria-label="播放位置" :aria-valuetext="`${clock(currentTime)} / ${clock(duration)}`"
          :style="{ '--elapsed': `${sliderProgress}%` }" @input="scrub" />
        <div class="lesson-controls__row">
          <button type="button" :aria-label="playing ? '暂停' : '播放'" :disabled="!duration" @click="togglePlay">
            <component :is="playing ? VideoPause : VideoPlay" aria-hidden="true" />
          </button>
          <time>{{ clock(currentTime) }} / <span>{{ clock(duration) }}</span></time>
          <div class="lesson-controls__extra">
            <button type="button" :aria-label="muted ? '取消静音' : '静音'" :aria-pressed="muted" @click="toggleMuted">
              <Mute v-if="muted" aria-hidden="true" />
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M3 9h4l5-4v14l-5-4H3zM16 8c2 2 2 6 0 8m3-11c4 4 4 10 0 14"/></svg>
            </button>
            <button type="button" aria-label="视频字幕" :aria-pressed="captions"
              :disabled="!subtitleTrackUrl && !subtitleText" @click="captions = !captions; updateCaptions()">CC</button>
            <button type="button" aria-label="切换全屏" @click="toggleFullscreen"><FullScreen aria-hidden="true" /></button>
          </div>
        </div>
      </div>
    </div>

    <component v-if="!lesson || errorMessage || videoErrorMessage" :is="compact ? 'details' : 'div'" class="video-card__metadata">
      <summary v-if="compact">播放与字幕信息</summary>
      <el-button v-if="compact && playbackUrl" :loading="loading" @click="$emit('refresh')">刷新播放链接</el-button>
    <p
      class="video-card__subtitle"
      :class="`video-card__subtitle--${resolvedSubtitleStatus}`"
    >
      {{ subtitleStatusText }}
    </p>

    <p v-if="expiresAt" class="video-card__expiry">
      播放链接有效期至 {{ formatApiTimestamp(expiresAt) }}
    </p>
    </component>
  </section>
</template>

<style scoped>
.lesson-video-skeleton { aspect-ratio: 16 / 9; border-radius: 16px; background: var(--color-surface-subtle); }
.video-card__metadata { font-size: 13px; color: var(--color-ink-soft); }
.video-card__metadata summary { cursor: pointer; padding-block: 4px; }
.video-card {
  display: grid;
  gap: 14px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.video-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.video-card h2 {
  margin: 0;
  color: var(--color-ink);
  font-size: 18px;
  line-height: 1.25;
}

.video-card p {
  margin: 8px 0 0;
  color: var(--color-ink-soft);
  line-height: 1.6;
}

.video-card__player-shell {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-lg);
  background: var(--color-video);
}

.course-video-player {
  display: block;
  width: 100%;
  max-height: 62vh;
  background: var(--color-video);
}

.video-card__subtitle-overlay {
  position: absolute;
  right: 18px;
  bottom: 54px;
  left: 18px;
  max-width: calc(100% - 36px);
  margin: 0 auto;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgb(17 24 39 / 78%);
  color: #ffffff;
  font-size: 16px;
  font-weight: 650;
  line-height: 1.5;
  text-align: center;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  pointer-events: none;
}

.video-card__subtitle {
  margin: 0;
  color: var(--color-ink-soft);
  font-size: 13px;
  line-height: 1.5;
}

.video-card__subtitle--loaded {
  color: var(--color-brand);
}

.video-card__subtitle--loading {
  color: var(--color-brand);
}

.video-card__subtitle--not_found,
.video-card__subtitle--none {
  color: var(--color-ink-muted);
}

.video-card__subtitle--unsupported,
.video-card__subtitle--failed {
  color: #b45309;
}

.video-card__expiry {
  margin: 0;
  color: var(--color-ink-muted);
  font-size: 12px;
}

@media (max-width: 720px) {
  .video-card__header {
    flex-direction: column;
  }

  .video-card__header :deep(.el-button) {
    width: 100%;
    margin-left: 0;
  }

  .video-card__subtitle-overlay {
    right: 10px;
    bottom: 48px;
    left: 10px;
    max-width: calc(100% - 20px);
    font-size: 14px;
  }
}

.video-card__player-shell--lesson { position: relative; overflow: hidden; }
.video-card__player-shell--lesson video { display: block; cursor: pointer; }
.video-card__player-shell--lesson:fullscreen { display: grid; place-items: center; background: #100d1b; }
.video-card__player-shell--lesson:fullscreen video { width: 100%; height: 100%; max-height: 100vh; object-fit: contain; }
.video-card__player-shell--lesson video::cue { background: rgb(13 9 26 / 84%); color: white; }
.lesson-controls { position: absolute; inset: auto 0 0; display: grid; gap: 2px; padding: 8px 14px; background: linear-gradient(transparent, rgb(10 7 23 / 84%) 62%); color: white; }
.lesson-scrubber { appearance: none; width: 100%; height: 16px; padding: 0; margin: 0; background: transparent; cursor: pointer; accent-color: #dcc8ff; }
.lesson-scrubber::-webkit-slider-runnable-track { height: 4px; border-radius: 8px; background: linear-gradient(to right, #dac4ff var(--elapsed), rgb(255 255 255 / 30%) var(--elapsed)); }
.lesson-scrubber::-webkit-slider-thumb { appearance: none; width: 11px; height: 11px; margin-top: -3.5px; border-radius: 50%; background: #dcc8ff; }
.lesson-scrubber::-moz-range-track { height: 4px; border-radius: 8px; background: rgb(255 255 255 / 30%); }
.lesson-scrubber::-moz-range-progress { height: 4px; border-radius: 8px; background: #dac4ff; }
.lesson-scrubber::-moz-range-thumb { width: 11px; height: 11px; border: 0; border-radius: 50%; background: #dcc8ff; }
.lesson-controls__row, .lesson-controls__extra { display: flex; align-items: center; gap: 9px; }
.lesson-controls__extra { margin-inline-start: auto; gap: 7px; }
.lesson-controls button { display: grid; width: 30px; min-height: 27px; place-items: center; padding: 2px; background: transparent; border: 0; border-radius: 4px; color: white; font: inherit; font-size: 12px; font-weight: 750; cursor: pointer; }
.lesson-controls button[aria-pressed="true"] { color: #dcc8ff; }
.lesson-controls button:disabled { opacity: .5; cursor: default; }
.lesson-controls button svg { width: 17px; height: 17px; }
.lesson-controls time { font-size: 12px; color: white; font-weight: 750; font-variant-numeric: tabular-nums; }
.lesson-controls time span { color: #d1c7e2; }
@media (max-width: 520px) {
  .lesson-controls { padding: 6px 10px 4px; }
  .lesson-controls__row { gap: 4px; }
}
</style>
