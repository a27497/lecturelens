<script setup lang="ts">
import type { UploadPhase } from "../../types/upload";
import { formatFileSize } from "../../utils/fileSize";

defineProps<{
  phase: UploadPhase;
  statusText: string;
  progressPercent: number;
  uploadedChunks: number;
  totalChunks: number;
  uploadedBytes: number;
  totalBytes: number;
  speedBytesPerSecond: number | null;
  etaSeconds: number | null;
  uploadingCount: number;
  failedCount: number;
  retryCount: number;
  maxConcurrency: number;
  chunkSizeBytes: number;
  uploadId: string;
}>();

function formatSpeed(bytesPerSecond: number | null): string {
  if (bytesPerSecond === null) {
    return "计算中";
  }
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) {
    return "等待上传";
  }
  return `${formatFileSize(bytesPerSecond)}/s`;
}

function formatEta(seconds: number | null): string {
  if (seconds === 0) {
    return "即将完成";
  }
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) {
    return "计算中";
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes <= 0) {
    return `${remainingSeconds} 秒`;
  }
  return `${minutes} 分 ${remainingSeconds.toString().padStart(2, "0")} 秒`;
}
</script>

<template>
  <section class="upload-progress" aria-label="上传进度">
    <div class="upload-progress__header">
      <strong>{{ statusText }}</strong>
      <span>{{ progressPercent }}%</span>
    </div>
    <el-progress
      :percentage="progressPercent"
      :show-text="false"
      :status="phase === 'success' ? 'success' : phase === 'error' ? 'exception' : undefined"
      :stroke-width="8"
    />

    <dl class="upload-progress__metrics" aria-label="上传实时指标">
      <div>
        <dt>已上传</dt>
        <dd>{{ formatFileSize(uploadedBytes) }} / {{ formatFileSize(totalBytes) }}</dd>
      </div>
      <div>
        <dt>当前速度</dt>
        <dd>{{ formatSpeed(speedBytesPerSecond) }}</dd>
      </div>
      <div>
        <dt>预计剩余</dt>
        <dd>{{ formatEta(etaSeconds) }}</dd>
      </div>
    </dl>

    <details class="upload-progress__details">
      <summary>上传详情</summary>
      <dl>
        <div>
          <dt>上传标识</dt>
          <dd>{{ uploadId || "尚未创建" }}</dd>
        </div>
        <div>
          <dt>分片大小</dt>
          <dd>{{ formatFileSize(chunkSizeBytes) }}</dd>
        </div>
        <div>
          <dt>已完成分片</dt>
          <dd>{{ uploadedChunks }} / {{ totalChunks }}</dd>
        </div>
        <div>
          <dt>并发分片</dt>
          <dd>{{ uploadingCount }} / {{ maxConcurrency }}</dd>
        </div>
        <div>
          <dt>失败分片</dt>
          <dd>{{ failedCount }}</dd>
        </div>
        <div>
          <dt>重试次数</dt>
          <dd>{{ retryCount }}</dd>
        </div>
      </dl>
    </details>
  </section>
</template>

<style scoped>
.upload-progress {
  display: grid;
  gap: 13px;
  padding-top: 4px;
}

.upload-progress__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--color-ink);
  font-size: 14px;
}

.upload-progress__header strong {
  min-width: 0;
  overflow-wrap: anywhere;
}

.upload-progress__header span {
  color: var(--color-brand-strong);
  font-weight: 700;
}

.upload-progress__metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
  margin: 6px 0 0;
  padding: 16px 0;
  border-block: 1px solid var(--color-border);
}

.upload-progress__metrics div {
  display: grid;
  gap: 5px;
  min-width: 0;
  padding: 0 16px;
  border-right: 1px solid var(--color-border);
}

.upload-progress__metrics div:first-child {
  padding-left: 0;
}

.upload-progress__metrics div:last-child {
  padding-right: 0;
  border-right: 0;
}

.upload-progress dt,
.upload-progress dd {
  margin: 0;
}

.upload-progress dt {
  color: var(--color-ink-muted);
  font-size: 12px;
}

.upload-progress dd {
  color: var(--color-ink);
  font-size: 14px;
  font-weight: 650;
  overflow-wrap: anywhere;
}

.upload-progress__details summary {
  color: var(--color-brand-strong);
  cursor: pointer;
  font-size: 13px;
  font-weight: 650;
}

.upload-progress__details dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px 20px;
  margin: 16px 0 0;
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-subtle);
}

.upload-progress__details dl div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

@media (max-width: 640px) {
  .upload-progress__metrics,
  .upload-progress__details dl {
    grid-template-columns: 1fr;
  }

  .upload-progress__metrics {
    gap: 14px;
  }

  .upload-progress__metrics div,
  .upload-progress__metrics div:first-child,
  .upload-progress__metrics div:last-child {
    padding: 0;
    border-right: 0;
  }
}
</style>
