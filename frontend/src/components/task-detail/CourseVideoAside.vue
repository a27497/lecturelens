<script setup lang="ts">
import { ref } from "vue";
import type { SeekRequest } from "./courseLocation";
import VideoPlaybackCard from "../VideoPlaybackCard.vue";
import type { TaskEventPayload, TaskConnectionStatus, TaskDetailResponse } from "../../types/task";
import CoursePreparationStatus from "./CoursePreparationStatus.vue";
import { formatWorkspaceTime } from "./workspace";

type SubtitleStatus = "none" | "loading" | "loaded" | "not_found" | "unsupported" | "failed";
type VideoPlaybackExpose = { seekTo: (seconds: number) => void };

const props = defineProps<{
  compact?: boolean;
  lesson?: boolean;
  inactive?: boolean;
  seekRequest?: SeekRequest;
  task: TaskEventPayload | null;
  taskDetail: TaskDetailResponse | null;
  connectionStatus: TaskConnectionStatus;
  connectionError: string;
  lastHeartbeatAt: string;
  playbackUrl: string;
  playbackLoading: boolean;
  playbackError: string;
  playbackExpiresAt: string;
  subtitleTrackUrl: string;
  subtitleText: string;
  subtitleLanguage: string;
  subtitleStatus: SubtitleStatus;
  subtitleMessage: string;
}>();

defineEmits<{ refreshVideo: []; position: [milliseconds: number]; manualSeek: [] }>();

const playbackRef = ref<VideoPlaybackExpose | null>(null);

function seekTo(seconds: number) {
  playbackRef.value?.seekTo(seconds);
}

defineExpose({ seekTo });
</script>

<template>
  <aside class="course-video-aside" aria-label="课程视频和处理状态">
    <VideoPlaybackCard
      ref="playbackRef"
      :compact="compact"
      :lesson="lesson"
      :inactive="inactive"
      :seek-request="seekRequest"
      @position="$emit('position', $event)"
      @manual-seek="$emit('manualSeek')"
      title="课程视频"
      description="播放上传的原始视频。"
      :playback-url="playbackUrl"
      :loading="playbackLoading"
      :error-message="playbackError"
      :expires-at="playbackExpiresAt"
      subtitle-label="原视频字幕"
      :subtitle-track-url="subtitleTrackUrl"
      :subtitle-text="subtitleText"
      :subtitle-language="subtitleLanguage"
      :subtitle-status="subtitleStatus"
      :subtitle-message="subtitleMessage"
      @refresh="$emit('refreshVideo')"
    />

    <CoursePreparationStatus v-if="!compact" classic :task="task" :task-detail="taskDetail" :connection-status="connectionStatus" :connection-error="connectionError" />

    <details v-if="!compact" class="course-details">
      <summary>课程信息</summary>
      <dl>
        <div><dt>任务 ID</dt><dd>{{ taskDetail?.taskId || task?.taskId || "暂无" }}</dd></div>
        <div><dt>原始状态</dt><dd>{{ task?.status || taskDetail?.status || "暂无" }}</dd></div>
        <div><dt>原始阶段</dt><dd>{{ task?.currentStage || taskDetail?.currentStage || "暂无" }}</dd></div>
        <div><dt>目标语言</dt><dd>{{ taskDetail?.targetLanguage || "暂无" }}</dd></div>
        <div><dt>最近心跳</dt><dd>{{ formatWorkspaceTime(lastHeartbeatAt) }}</dd></div>
        <div><dt>开始时间</dt><dd>{{ formatWorkspaceTime(taskDetail?.startedAt) }}</dd></div>
        <div><dt>结束时间</dt><dd>{{ formatWorkspaceTime(taskDetail?.finishedAt) }}</dd></div>
      </dl>
    </details>
  </aside>
</template>

<style scoped>
.course-video-aside { display: grid; gap: 16px; min-width: 0; }
.course-details { border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); }
dl { display: grid; gap: 10px; margin: 0; }
dl div { display: flex; justify-content: space-between; gap: 12px; }
dt, dd { margin: 0; }
dt { color: var(--color-ink-soft); font-size: 13px; }
dd { color: var(--color-ink); text-align: right; overflow-wrap: anywhere; }
.course-details { padding: 0 18px; }
.course-details summary { padding: 16px 0; color: var(--color-ink); font-weight: 700; cursor: pointer; }
.course-details dl { padding: 0 0 18px; }
</style>
