import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { connectTaskEvents } from "../api/taskEvents";
import { useTaskEventsStore } from "./taskEvents";
import type { AnalysisTaskStatus, TaskEventPayload } from "../types/task";

vi.mock("../api/taskEvents", () => ({
  connectTaskEvents: vi.fn(),
  isTaskEventAuthError: vi.fn(() => false),
  toReadableTaskEventError: vi.fn(() => "任务事件流连接失败，请稍后重试"),
}));

const connectTaskEventsMock = vi.mocked(connectTaskEvents);

describe("task event connection lifecycle", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it("does not let a late running event overwrite a canceled task at 22 percent", () => {
    const store = useTaskEventsStore();
    store.applyMessage({ event: "canceled", data: payload("CANCELED", 22, null) });
    store.applyMessage({ event: "progress", data: payload("RUNNING", 30, "ASR") });

    expect(store.task?.status).toBe("CANCELED");
    expect(store.task?.progressPercent).toBe(22);
    expect(store.connectionStatus).toBe("closed");
  });

  it("automatically reconnects an unexpectedly closed stream without clearing task progress", async () => {
    vi.useFakeTimers();
    connectTaskEventsMock
      .mockImplementationOnce(async ({ onOpen, onMessage }) => {
        onOpen();
        onMessage({ event: "progress", data: payload("RUNNING", 64, "VISION_ANALYSIS") });
      })
      .mockImplementationOnce(({ onOpen }) => {
        onOpen();
        return new Promise<void>(() => undefined);
      });

    const store = useTaskEventsStore();
    store.connect("task_1");
    await Promise.resolve();
    await Promise.resolve();

    expect(store.connectionStatus).toBe("reconnecting");
    expect(store.errorMessage).toContain("正在自动重连");
    expect(store.task?.progressPercent).toBe(64);

    await vi.advanceTimersByTimeAsync(1_000);

    expect(connectTaskEventsMock).toHaveBeenCalledTimes(2);
    expect(store.connectionStatus).toBe("connected");
    expect(store.task?.progressPercent).toBe(64);
  });

  it("cancels a pending automatic reconnect after a terminal event", async () => {
    vi.useFakeTimers();
    connectTaskEventsMock.mockImplementationOnce(async ({ onOpen, onMessage }) => {
      onOpen();
      onMessage({ event: "progress", data: payload("RUNNING", 95, "ARTIFACT_GENERATION") });
    });

    const store = useTaskEventsStore();
    store.connect("task_1");
    await Promise.resolve();
    await Promise.resolve();
    store.applyMessage({ event: "completed", data: payload("SUCCEEDED", 100, "DONE") });

    await vi.advanceTimersByTimeAsync(10_000);

    expect(connectTaskEventsMock).toHaveBeenCalledTimes(1);
    expect(store.connectionStatus).toBe("closed");
    expect(store.task?.status).toBe("SUCCEEDED");
  });

  it("increases the bounded delay when a reconnected stream opens and immediately closes", async () => {
    vi.useFakeTimers();
    connectTaskEventsMock.mockImplementation(async ({ onOpen }) => {
      onOpen();
    });

    const store = useTaskEventsStore();
    store.connect("task_1");
    await Promise.resolve();
    await Promise.resolve();

    await vi.advanceTimersByTimeAsync(1_000);
    expect(connectTaskEventsMock).toHaveBeenCalledTimes(2);

    await vi.advanceTimersByTimeAsync(1_999);
    expect(connectTaskEventsMock).toHaveBeenCalledTimes(2);

    await vi.advanceTimersByTimeAsync(1);
    expect(connectTaskEventsMock).toHaveBeenCalledTimes(3);
    expect(store.reconnectAttempt).toBe(3);
  });
});

function payload(status: AnalysisTaskStatus, progressPercent: number, currentStage: string | null): TaskEventPayload {
  return {
    taskId: "task_1",
    status,
    progressPercent,
    currentStage,
    errorCode: null,
    errorMessage: null,
    updatedAt: "2026-07-31T03:47:20Z",
  };
}
