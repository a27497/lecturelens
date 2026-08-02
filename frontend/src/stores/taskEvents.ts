import { defineStore } from "pinia";
import {
  connectTaskEvents,
  isTaskEventAuthError,
  toReadableTaskEventError,
} from "../api/taskEvents";
import type {
  AnalysisTaskStatus,
  TaskConnectionStatus,
  TaskEventMessage,
  TaskEventPayload,
} from "../types/task";

const TERMINAL_STATUSES = new Set<AnalysisTaskStatus>(["SUCCEEDED", "FAILED", "CANCELED"]);
const INITIAL_RECONNECT_DELAY_MS = 1_000;
const MAX_RECONNECT_DELAY_MS = 10_000;
const STABLE_CONNECTION_RESET_MS = 30_000;

interface TaskEventsState {
  taskId: string;
  task: TaskEventPayload | null;
  connectionStatus: TaskConnectionStatus;
  errorMessage: string;
  lastHeartbeatAt: string;
  controller: AbortController | null;
  reconnectTimer: ReturnType<typeof setTimeout> | null;
  reconnectStabilityTimer: ReturnType<typeof setTimeout> | null;
  reconnectAttempt: number;
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
    reconnectTimer: null,
    reconnectStabilityTimer: null,
    reconnectAttempt: 0,
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
      this.openConnection(normalizedTaskId, false);
    },

    openConnection(normalizedTaskId: string, reconnecting: boolean) {
      this.closeCurrentConnection();
      this.clearReconnectTimer();
      this.requestVersion += 1;
      const currentVersion = this.requestVersion;
      this.taskId = normalizedTaskId;
      if (!reconnecting) {
        this.task = null;
        this.lastHeartbeatAt = "";
        this.errorMessage = "";
        this.reconnectAttempt = 0;
      }

      if (!normalizedTaskId) {
        this.connectionStatus = "idle";
        this.errorMessage = "请提供任务 ID";
        return;
      }

      const controller = new AbortController();
      this.controller = controller;
      this.connectionStatus = reconnecting ? "reconnecting" : "connecting";

      void connectTaskEvents({
        taskId: normalizedTaskId,
        signal: controller.signal,
        onOpen: () => {
          if (this.isStale(currentVersion)) {
            return;
          }
          this.connectionStatus = "connected";
          this.errorMessage = "";
          if (reconnecting && this.reconnectAttempt > 0) {
            this.scheduleReconnectAttemptReset(currentVersion, controller);
          }
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
          if (this.isTerminal) {
            this.connectionStatus = "closed";
            return;
          }
          this.scheduleReconnect(currentVersion, "任务事件流已断开");
        })
        .catch((error: unknown) => {
          if (this.isStale(currentVersion) || controller.signal.aborted) {
            return;
          }
          if (isTaskEventAuthError(error)) {
            this.connectionStatus = "error";
            this.errorMessage = toReadableTaskEventError(error);
            return;
          }
          this.scheduleReconnect(currentVersion, toReadableTaskEventError(error));
        });
    },

    reconnect() {
      if (!this.taskId || (this.isConnecting && !this.reconnectTimer)) {
        return;
      }
      const taskId = this.taskId;
      this.openConnection(taskId, true);
    },

    disconnect() {
      this.clearReconnectTimer();
      this.closeCurrentConnection();
      this.requestVersion += 1;
      this.connectionStatus = this.isTerminal ? "closed" : "idle";
    },

    scheduleReconnect(version: number, message: string) {
      if (this.isStale(version) || this.isTerminal || !this.taskId) {
        return;
      }
      this.closeCurrentConnection();
      this.clearReconnectTimer();
      this.connectionStatus = "reconnecting";
      const readableMessage = message.trim() || "任务事件流连接失败";
      this.errorMessage = `${readableMessage}，正在自动重连`;
      this.reconnectAttempt += 1;
      const delay = Math.min(
        INITIAL_RECONNECT_DELAY_MS * (2 ** Math.max(0, this.reconnectAttempt - 1)),
        MAX_RECONNECT_DELAY_MS,
      );
      const taskId = this.taskId;
      this.reconnectTimer = setTimeout(() => {
        this.reconnectTimer = null;
        if (this.isStale(version) || this.isTerminal || this.taskId !== taskId) {
          return;
        }
        this.openConnection(taskId, true);
      }, delay);
    },

    applyMessage(message: TaskEventMessage) {
      if (message.event === "heartbeat") {
        this.lastHeartbeatAt = new Date().toISOString();
        return;
      }

      if (message.data && !this.shouldKeepTerminalTask(message.data)) {
        this.task = message.data;
      }

      if (message.event === "completed" || message.event === "failed" || message.event === "canceled") {
        this.connectionStatus = "closed";
        this.clearReconnectTimer();
        this.closeCurrentConnection();
      }
    },

    shouldKeepTerminalTask(next: TaskEventPayload): boolean {
      return Boolean(
        this.task
        && TERMINAL_STATUSES.has(this.task.status)
        && !TERMINAL_STATUSES.has(next.status),
      );
    },

    closeCurrentConnection() {
      this.clearReconnectStabilityTimer();
      if (this.controller) {
        this.controller.abort();
        this.controller = null;
      }
    },

    clearReconnectTimer() {
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
    },

    scheduleReconnectAttemptReset(version: number, controller: AbortController) {
      this.clearReconnectStabilityTimer();
      this.reconnectStabilityTimer = setTimeout(() => {
        this.reconnectStabilityTimer = null;
        if (!this.isStale(version) && this.controller === controller && this.connectionStatus === "connected") {
          this.reconnectAttempt = 0;
        }
      }, STABLE_CONNECTION_RESET_MS);
    },

    clearReconnectStabilityTimer() {
      if (this.reconnectStabilityTimer) {
        clearTimeout(this.reconnectStabilityTimer);
        this.reconnectStabilityTimer = null;
      }
    },

    isStale(version: number): boolean {
      return version !== this.requestVersion;
    },
  },
});
