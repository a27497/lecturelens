import { defineStore } from "pinia";
import {
  completeUpload,
  createUploadSession,
  getMissingChunks,
  isRetryableUploadError,
  toReadableUploadError,
  toUploadRetryingMessage,
  UPLOAD_CHUNK_RETRY_DELAYS_MS,
  uploadChunk,
} from "../api/upload";
import type { CompleteUploadResponse, SelectedUploadFile, UploadPhase } from "../types/upload";
import { calculateFileMd5 } from "../utils/fileMd5";
import { getFileExtension } from "../utils/fileSize";

const DEFAULT_CHUNK_SIZE_BYTES = 10 * 1024 * 1024;
const MAX_CONCURRENT_CHUNKS = 3;
const SPEED_SAMPLE_WINDOW_MS = 6000;
const SPEED_SAMPLE_MIN_INTERVAL_MS = 500;
const SUPPORTED_EXTENSIONS = new Set(["mp4", "mov", "mkv", "webm"]);
const activeChunkControllers = new Map<number, AbortController>();

class UploadPausedError extends Error {
  constructor() {
    super("UPLOAD_PAUSED");
    this.name = "UploadPausedError";
  }
}

function isUploadPausedError(error: unknown): boolean {
  return error instanceof UploadPausedError;
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function withJitter(ms: number): number {
  return ms + Math.floor(Math.random() * 250);
}

interface SpeedSample {
  timeMs: number;
  bytes: number;
}

interface UploadState {
  selected: SelectedUploadFile | null;
  phase: UploadPhase;
  statusText: string;
  errorMessage: string;
  uploadId: string;
  fileMd5: string;
  chunkSizeBytes: number;
  totalChunks: number;
  uploadedChunks: number[];
  missingChunks: number[];
  activeChunks: number[];
  failedChunks: number[];
  chunkProgressBytes: Record<number, number>;
  uploadedBytes: number;
  totalBytes: number;
  speedBytesPerSecond: number | null;
  etaSeconds: number | null;
  uploadStartedAtMs: number;
  speedSamples: SpeedSample[];
  retryCount: number;
  retryMessage: string;
  pauseRequested: boolean;
  progressPercent: number;
  completed: CompleteUploadResponse | null;
}

export const useUploadStore = defineStore("upload", {
  state: (): UploadState => ({
    selected: null,
    phase: "empty",
    statusText: "请选择一个课程视频文件",
    errorMessage: "",
    uploadId: "",
    fileMd5: "",
    chunkSizeBytes: DEFAULT_CHUNK_SIZE_BYTES,
    totalChunks: 0,
    uploadedChunks: [],
    missingChunks: [],
    activeChunks: [],
    failedChunks: [],
    chunkProgressBytes: {},
    uploadedBytes: 0,
    totalBytes: 0,
    speedBytesPerSecond: null,
    etaSeconds: null,
    uploadStartedAtMs: 0,
    speedSamples: [],
    retryCount: 0,
    retryMessage: "",
    pauseRequested: false,
    progressPercent: 0,
    completed: null,
  }),

  getters: {
    isBusy: (state) =>
      ["hashing", "creating", "checking", "uploading", "completing"].includes(state.phase),
    canStart: (state) =>
      state.selected !== null &&
      state.uploadId.length === 0 &&
      state.selected.isSupportedExtension &&
      !["hashing", "creating", "checking", "uploading", "paused", "completing", "success"].includes(
        state.phase,
      ),
    canResume: (state) =>
      state.selected !== null &&
      state.uploadId.length > 0 &&
      !["hashing", "creating", "checking", "uploading", "completing", "success"].includes(
        state.phase,
      ),
    isPaused: (state) => state.phase === "paused",
    uploadedCount: (state) => state.uploadedChunks.length,
    uploadingCount: (state) => state.activeChunks.length,
    failedCount: (state) => state.failedChunks.length,
  },

  actions: {
    selectFile(file: File | null) {
      this.reset();
      if (!file) {
        return;
      }
      const extension = getFileExtension(file.name);
      const isSupportedExtension = SUPPORTED_EXTENSIONS.has(extension);
      this.selected = { file, extension, isSupportedExtension };
      this.totalBytes = file.size;
      this.totalChunks = Math.ceil(file.size / this.chunkSizeBytes);
      this.phase = isSupportedExtension ? "ready" : "error";
      this.statusText = isSupportedExtension
        ? "文件已选择，可以开始上传"
        : "当前文件类型暂不支持";
      this.errorMessage = isSupportedExtension ? "" : "仅支持 mp4、mov、mkv、webm 文件";
    },

    reset() {
      this.abortActiveChunks();
      this.selected = null;
      this.phase = "empty";
      this.statusText = "请选择一个课程视频文件";
      this.errorMessage = "";
      this.uploadId = "";
      this.fileMd5 = "";
      this.totalChunks = 0;
      this.uploadedChunks = [];
      this.missingChunks = [];
      this.activeChunks = [];
      this.failedChunks = [];
      this.chunkProgressBytes = {};
      this.uploadedBytes = 0;
      this.totalBytes = 0;
      this.speedBytesPerSecond = null;
      this.etaSeconds = null;
      this.uploadStartedAtMs = 0;
      this.speedSamples = [];
      this.retryCount = 0;
      this.retryMessage = "";
      this.pauseRequested = false;
      this.progressPercent = 0;
      this.completed = null;
    },

    async startUpload() {
      if (!this.selected || !this.selected.isSupportedExtension || this.isBusy) {
        return;
      }
      try {
        this.pauseRequested = false;
        await this.prepareSession();
        await this.resumeUpload();
      } catch (error) {
        if (isUploadPausedError(error)) {
          this.enterPaused();
          return;
        }
        this.fail(error);
      }
    },

    async resumeUpload() {
      if (!this.selected || !this.uploadId || this.isBusy) {
        return;
      }
      try {
        this.pauseRequested = false;
        this.phase = "checking";
        this.statusText = "正在查询缺失分片";
        this.clearTransientProgress();
        const missing = await getMissingChunks(this.uploadId);
        if (this.pauseRequested) {
          throw new UploadPausedError();
        }
        this.missingChunks = missing.missingChunks;
        this.uploadedChunks = [...missing.uploadedChunks].sort((left, right) => left - right);
        this.totalChunks = missing.totalChunks;
        this.totalBytes = this.selected.file.size;
        this.updateProgress();

        if (this.missingChunks.length > 0) {
          this.phase = "uploading";
          this.statusText = "正在上传课程视频分片";
          this.uploadStartedAtMs = Date.now();
          this.speedSamples = [{ timeMs: this.uploadStartedAtMs, bytes: this.uploadedBytes }];
          await this.uploadMissingChunksConcurrently();
        }
        if (this.pauseRequested) {
          throw new UploadPausedError();
        }

        this.phase = "completing";
        this.statusText = "分片已上传，正在完成后端合并";
        this.clearTransientProgress();
        this.completed = await completeUpload(this.uploadId);
        if (this.pauseRequested) {
          throw new UploadPausedError();
        }
        this.phase = "success";
        this.uploadedBytes = this.totalBytes;
        this.speedBytesPerSecond = null;
        this.etaSeconds = 0;
        this.progressPercent = 100;
        this.statusText = "上传完成，可以创建 AI 分析任务";
        this.errorMessage = "";
      } catch (error) {
        if (isUploadPausedError(error)) {
          this.enterPaused();
          return;
        }
        this.fail(error);
      }
    },

    async prepareSession() {
      if (!this.selected) {
        return;
      }
      const { file } = this.selected;
      this.totalBytes = file.size;
      this.totalChunks = Math.ceil(file.size / this.chunkSizeBytes);
      this.phase = "hashing";
      this.statusText = "正在计算文件 MD5，请稍候";
      this.fileMd5 = await calculateFileMd5(file, (progress) => {
        this.progressPercent = progress;
      });

      this.phase = "creating";
      this.statusText = "正在创建上传会话";
      const session = await createUploadSession({
        filename: file.name,
        sizeBytes: file.size,
        chunkSizeBytes: this.chunkSizeBytes,
        totalChunks: this.totalChunks,
        fileMd5: this.fileMd5,
      });
      this.uploadId = session.uploadId;
      this.progressPercent = 0;
      this.phase = "ready";
    },

    async uploadMissingChunksConcurrently() {
      const queue = [...this.missingChunks];
      const workerCount = Math.min(MAX_CONCURRENT_CHUNKS, queue.length);
      const workers = Array.from({ length: workerCount }, async () => {
        while (queue.length > 0 && !this.pauseRequested) {
          const chunkIndex = queue.shift();
          if (chunkIndex === undefined) {
            return;
          }
          await this.uploadOneChunk(chunkIndex);
        }
      });
      await Promise.all(workers);
      if (this.pauseRequested) {
        throw new UploadPausedError();
      }
    },

    async uploadOneChunk(chunkIndex: number) {
      if (!this.selected) {
        return;
      }
      const start = chunkIndex * this.chunkSizeBytes;
      const end = Math.min(start + this.chunkSizeBytes, this.selected.file.size);
      const chunkSize = end - start;
      this.markChunkActive(chunkIndex);
      try {
        for (let attempt = 0; attempt <= UPLOAD_CHUNK_RETRY_DELAYS_MS.length; attempt += 1) {
          if (this.pauseRequested) {
            throw new UploadPausedError();
          }
          this.clearChunkProgress(chunkIndex);
          const controller = new AbortController();
          activeChunkControllers.set(chunkIndex, controller);
          try {
            await uploadChunk(
              this.uploadId,
              chunkIndex,
              this.selected.file.slice(start, end),
              {
                signal: controller.signal,
                onUploadProgress: (event) => {
                  const loaded = Math.min(event.loaded || 0, chunkSize);
                  this.chunkProgressBytes = {
                    ...this.chunkProgressBytes,
                    [chunkIndex]: loaded,
                  };
                  this.updateProgress();
                },
              },
            );
            if (!this.uploadedChunks.includes(chunkIndex)) {
              this.uploadedChunks.push(chunkIndex);
              this.uploadedChunks.sort((left, right) => left - right);
            }
            this.removeFailedChunk(chunkIndex);
            this.statusText = `已上传 ${this.uploadedChunks.length}/${this.totalChunks} 个分片`;
            return;
          } catch (error) {
            if (this.pauseRequested || controller.signal.aborted) {
              throw new UploadPausedError();
            }
            this.clearChunkProgress(chunkIndex);
            const canRetry =
              isRetryableUploadError(error) && attempt < UPLOAD_CHUNK_RETRY_DELAYS_MS.length;
            if (!canRetry) {
              this.markChunkFailed(chunkIndex);
              throw error;
            }
            const retryNumber = attempt + 1;
            this.retryCount += 1;
            this.retryMessage = `正在重试第 ${chunkIndex + 1} 个分片，第 ${retryNumber} 次`;
            this.statusText = `${toUploadRetryingMessage(error)} 正在重试第 ${retryNumber} 次。`;
            this.statusText = `${toUploadRetryingMessage(error)} ${this.retryMessage}`;
            await wait(withJitter(UPLOAD_CHUNK_RETRY_DELAYS_MS[attempt]));
          } finally {
            activeChunkControllers.delete(chunkIndex);
          }
        }
      } finally {
        this.markChunkInactive(chunkIndex);
        this.clearChunkProgress(chunkIndex);
      }
    },

    pauseUpload() {
      if (!["checking", "uploading"].includes(this.phase)) {
        return;
      }
      this.pauseRequested = true;
      this.abortActiveChunks();
      this.enterPaused();
    },

    enterPaused() {
      this.phase = "paused";
      this.statusText = "上传已暂停";
      this.activeChunks = [];
      this.chunkProgressBytes = {};
      this.speedBytesPerSecond = null;
      this.etaSeconds = null;
    },

    abortActiveChunks() {
      activeChunkControllers.forEach((controller) => {
        controller.abort();
      });
      activeChunkControllers.clear();
    },

    clearChunkProgress(chunkIndex: number) {
      if (!(chunkIndex in this.chunkProgressBytes)) {
        return;
      }
      const remainingProgress = { ...this.chunkProgressBytes };
      delete remainingProgress[chunkIndex];
      this.chunkProgressBytes = remainingProgress;
      this.updateProgress();
    },

    markChunkActive(chunkIndex: number) {
      if (!this.activeChunks.includes(chunkIndex)) {
        this.activeChunks = [...this.activeChunks, chunkIndex].sort((left, right) => left - right);
      }
    },

    markChunkInactive(chunkIndex: number) {
      this.activeChunks = this.activeChunks.filter((current) => current !== chunkIndex);
    },

    markChunkFailed(chunkIndex: number) {
      if (!this.failedChunks.includes(chunkIndex)) {
        this.failedChunks = [...this.failedChunks, chunkIndex].sort((left, right) => left - right);
      }
    },

    removeFailedChunk(chunkIndex: number) {
      this.failedChunks = this.failedChunks.filter((current) => current !== chunkIndex);
    },

    clearTransientProgress() {
      this.activeChunks = [];
      this.failedChunks = [];
      this.chunkProgressBytes = {};
      this.speedBytesPerSecond = null;
      this.etaSeconds = null;
      this.uploadStartedAtMs = 0;
      this.speedSamples = [];
      this.retryCount = 0;
      this.retryMessage = "";
    },

    getChunkSize(chunkIndex: number): number {
      if (!this.selected) {
        return this.chunkSizeBytes;
      }
      const start = chunkIndex * this.chunkSizeBytes;
      const end = Math.min(start + this.chunkSizeBytes, this.selected.file.size);
      return Math.max(end - start, 0);
    },

    updateProgress() {
      if (!this.selected || this.totalBytes <= 0) {
        this.uploadedBytes = 0;
        this.progressPercent = 0;
        this.speedBytesPerSecond = null;
        this.etaSeconds = null;
        return;
      }

      const completedBytes = this.uploadedChunks.reduce(
        (sum, chunkIndex) => sum + this.getChunkSize(chunkIndex),
        0,
      );
      const activeBytes = Object.entries(this.chunkProgressBytes).reduce((sum, [index, loaded]) => {
        const chunkIndex = Number(index);
        if (this.uploadedChunks.includes(chunkIndex)) {
          return sum;
        }
        return sum + Math.min(loaded, this.getChunkSize(chunkIndex));
      }, 0);
      this.uploadedBytes = Math.min(completedBytes + activeBytes, this.totalBytes);
      this.progressPercent = Math.min(
        100,
        Math.round((this.uploadedBytes / this.totalBytes) * 100),
      );

      if (this.phase === "uploading") {
        this.updateRollingSpeed();
        const remainingBytes = Math.max(this.totalBytes - this.uploadedBytes, 0);
        const speed = this.speedBytesPerSecond;
        this.etaSeconds = speed !== null && speed > 0 ? Math.ceil(remainingBytes / speed) : null;
      }
    },

    updateRollingSpeed() {
      const now = Date.now();
      const lastSample = this.speedSamples[this.speedSamples.length - 1];
      if (
        !lastSample ||
        now - lastSample.timeMs >= SPEED_SAMPLE_MIN_INTERVAL_MS ||
        this.uploadedBytes !== lastSample.bytes
      ) {
        this.speedSamples = [
          ...this.speedSamples.filter((sample) => now - sample.timeMs <= SPEED_SAMPLE_WINDOW_MS),
          { timeMs: now, bytes: this.uploadedBytes },
        ];
      }

      const firstSample = this.speedSamples[0];
      const newestSample = this.speedSamples[this.speedSamples.length - 1];
      if (!firstSample || !newestSample || newestSample.timeMs <= firstSample.timeMs) {
        this.speedBytesPerSecond = null;
        return;
      }

      const elapsedSeconds = (newestSample.timeMs - firstSample.timeMs) / 1000;
      const transferredBytes = newestSample.bytes - firstSample.bytes;
      this.speedBytesPerSecond =
        elapsedSeconds >= 1 && transferredBytes > 0 ? transferredBytes / elapsedSeconds : null;
    },

    fail(error: unknown) {
      this.phase = "error";
      this.errorMessage = toReadableUploadError(error);
      this.statusText = "上传中断，可点击“继续上传”重试失败分片";
      this.activeChunks = [];
      this.speedBytesPerSecond = null;
      this.etaSeconds = null;
    },
  },
});
