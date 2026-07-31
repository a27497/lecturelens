import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useTaskEventsStore } from "./taskEvents";
import type { AnalysisTaskStatus, TaskEventPayload } from "../types/task";

describe("task event terminal precedence", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("does not let a late running event overwrite a canceled task at 22 percent", () => {
    const store = useTaskEventsStore();
    store.applyMessage({ event: "canceled", data: payload("CANCELED", 22, null) });
    store.applyMessage({ event: "progress", data: payload("RUNNING", 30, "ASR") });

    expect(store.task?.status).toBe("CANCELED");
    expect(store.task?.progressPercent).toBe(22);
    expect(store.connectionStatus).toBe("closed");
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
