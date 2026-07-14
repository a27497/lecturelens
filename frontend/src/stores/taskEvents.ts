import { defineStore } from "pinia";
import {
  connectTaskEvents,
  toReadableTaskEventError,
} from "../api/taskEvents";
import type {
  AnalysisTaskStatus,
  TaskConnectionStatus,
  TaskEventMessage,
  TaskEventPayload,
} from "../types/task";

const TERMINAL_STATUSES = new Set<AnalysisTaskStatus>(["SUCCEEDED", "FAILED", "CANCELED"]);

interface TaskEventsState {
  taskId: string;
  task: TaskEventPayload | null;
  connectionStatus: TaskConnectionStatus;
  errorMessage: string;
  lastHeartbeatAt: string;
  controller: AbortController | null;
  requestVersion: number;
}

export const useTaskEventsStore = defineStore("taskEvents", {
  state: (): TaskEventsState => ({
    taskId: "",
    task: null,
    connectionStatus: "idle",
    errorMessage: "",
    lastHeartbeatAt: "",
    controller: null,
    requestVersion: 0,
  }),

  getters: {
    isConnecting: (state) =>
      state.connectionStatus === "connecting" || state.connectionStatus === "reconnecting",
    isTerminal: (state) => (state.task ? TERMINAL_STATUSES.has(state.task.status) : false),
  },

  actions: {
    connect(taskId: string) {
      const normalizedTaskId = taskId.trim();
      this.closeCurrentConnection();
      this.requestVersion += 1;
      const currentVersion = this.requestVersion;
      this.taskId = normalizedTaskId;
      this.task = null;
      this.lastHeartbeatAt = "";
      this.errorMessage = "";

      if (!normalizedTaskId) {
        this.connectionStatus = "idle";
        this.errorMessage = "请提供任务 ID";
        return;
      }

      const controller = new AbortController();
      this.controller = controller;
      this.connectionStatus = "connecting";

      void connectTaskEvents({
        taskId: normalizedTaskId,
        signal: controller.signal,
        onOpen: () => {
          if (this.isStale(currentVersion)) {
            return;
          }
          this.connectionStatus = "connected";
          this.errorMessage = "";
        },
        onMessage: (message) => {
          if (this.isStale(currentVersion)) {
            return;
          }
          this.applyMessage(message);
        },
      })
        .then(() => {
          if (this.isStale(currentVersion) || controller.signal.aborted) {
            return;
          }
          this.connectionStatus = this.isTerminal ? "closed" : "error";
          if (!this.isTerminal) {
            this.errorMessage = "任务事件流已断开，可重新连接";
          }
        })
        .catch((error: unknown) => {
          if (this.isStale(currentVersion) || controller.signal.aborted) {
            return;
          }
          this.connectionStatus = "error";
          this.errorMessage = toReadableTaskEventError(error);
        });
    },

    reconnect() {
      if (!this.taskId || this.isConnecting) {
        return;
      }
      const taskId = this.taskId;
      this.connectionStatus = "reconnecting";
      this.connect(taskId);
    },

    disconnect() {
      this.closeCurrentConnection();
      this.connectionStatus = this.isTerminal ? "closed" : "idle";
    },

    applyMessage(message: TaskEventMessage) {
      if (message.event === "heartbeat") {
        this.lastHeartbeatAt = new Date().toISOString();
        return;
      }

      if (message.data) {
        this.task = message.data;
      }

      if (message.event === "completed" || message.event === "failed" || message.event === "canceled") {
        this.connectionStatus = "closed";
        this.closeCurrentConnection();
      }
    },

    closeCurrentConnection() {
      if (this.controller) {
        this.controller.abort();
        this.controller = null;
      }
    },

    isStale(version: number): boolean {
      return version !== this.requestVersion;
    },
  },
});
