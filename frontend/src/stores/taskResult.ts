import { defineStore } from "pinia";
import { fetchTaskResult, toReadableTaskResultError } from "../api/result";
import type { TaskResultResponse } from "../types/result";

interface TaskResultState {
  taskId: string;
  result: TaskResultResponse | null;
  loading: boolean;
  errorMessage: string;
  requestVersion: number;
}

export const useTaskResultStore = defineStore("taskResult", {
  state: (): TaskResultState => ({
    taskId: "",
    result: null,
    loading: false,
    errorMessage: "",
    requestVersion: 0,
  }),

  getters: {
    hasAnyResult: (state) => {
      const result = state.result;
      return Boolean(
        result &&
          (result.subtitles.length > 0 ||
            result.translations.length > 0 ||
            result.learningPackage ||
            result.artifacts.length > 0 ||
            result.keyframes.length > 0 ||
            result.aiCallRecords.length > 0),
      );
    },
  },

  actions: {
    async load(taskId: string) {
      const normalizedTaskId = taskId.trim();
      this.requestVersion += 1;
      const currentVersion = this.requestVersion;
      this.taskId = normalizedTaskId;
      this.result = null;
      this.errorMessage = "";

      if (!normalizedTaskId) {
        this.loading = false;
        return;
      }

      this.loading = true;
      try {
        const result = await fetchTaskResult(normalizedTaskId);
        if (this.isStale(currentVersion)) {
          return;
        }
        this.result = result;
      } catch (error) {
        if (this.isStale(currentVersion)) {
          return;
        }
        this.errorMessage = toReadableTaskResultError(error);
      } finally {
        if (!this.isStale(currentVersion)) {
          this.loading = false;
        }
      }
    },

    clear() {
      this.requestVersion += 1;
      this.taskId = "";
      this.result = null;
      this.loading = false;
      this.errorMessage = "";
    },

    isStale(version: number): boolean {
      return version !== this.requestVersion;
    },
  },
});
