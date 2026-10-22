<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { createTimeIndex } from "../utils/timeIndex";
import type { SeekRequest } from "./task-detail/courseLocation";
import { parseVttCues } from "../utils/vtt";
import { formatApiTimestamp } from "../utils/time";

type SubtitleStatus = "none" | "loading" | "loaded" | "not_found" | "unsupported" | "failed";

const props = defineProps<{
  seekRequest?: SeekRequest;
  title: string;
  description: string;
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
  if (videoRef.value) resumeAfterReload = !videoRef.value.paused && !videoRef.value.ended;
  if (pendingSeekSeconds.value === null && hasPosition) pendingSeekSeconds.value = currentTime.value;
  videoErrorMessage.value = "";
});
watch(() => props.seekRequest, request => {
  if (request) seekTo(request.milliseconds / 1000);
}, { immediate: true });

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
  videoErrorMessage.value = "";
  if (pendingSeekSeconds.value !== null) applyPendingSeek();
  else updateCurrentTime(event);
  if (resumeAfterReload && videoRef.value) {
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
    <div class="video-card__header">
      <div>
        <h2>{{ title }}</h2>
        <p>{{ description }}</p>
      </div>
      <el-button :loading="loading" @click="$emit('refresh')">刷新播放链接</el-button>
    </div>

    <el-skeleton v-if="loading && !playbackUrl" :rows="3" animated />

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

    <div v-if="playbackUrl" class="video-card__player-shell">
      <video
      v-if="playbackUrl"
      ref="videoRef"
      class="course-video-player"
      :src="playbackUrl"
      controls
      preload="metadata"
      @loadedmetadata="handleLoadedMetadata"
      @canplay="clearVideoError(); applyPendingSeek()"
      @error="handleVideoError"
      @seeking="handleSeeking"
      @seeked="handleSeeked"
      @timeupdate="updateCurrentTime"
      @pause="updateCurrentTime"
      @ended="updateCurrentTime"
    >
        <track
          v-if="subtitleTrackUrl"
          kind="subtitles"
          :src="subtitleTrackUrl"
          :srclang="subtitleLanguage || 'und'"
          :label="resolvedSubtitleLabel"
          default
        />
      </video>
      <div v-if="activeSubtitleText" class="video-card__subtitle-overlay">
        {{ activeSubtitleText }}
      </div>
    </div>

    <p
      class="video-card__subtitle"
      :class="`video-card__subtitle--${resolvedSubtitleStatus}`"
    >
      {{ subtitleStatusText }}
    </p>

    <p v-if="expiresAt" class="video-card__expiry">
      播放链接有效期至 {{ formatApiTimestamp(expiresAt) }}
    </p>
  </section>
</template>

<style scoped>
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
  border-radius: var(--radius-sm);
  background: var(--color-ink);
}

.course-video-player {
  display: block;
  width: 100%;
  max-height: 62vh;
  background: var(--color-ink);
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
</style>
