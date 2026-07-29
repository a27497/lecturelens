import { describe, expect, it } from "vitest";
import {
  getTaskStatusGroup,
  getTaskStatusLabel,
  getTaskStatusTagType,
  isRetryableTaskStatus,
  isRunningTaskStatus,
  shortenTaskId,
} from "./taskStatus";

describe("task status helpers", () => {
  it("groups running and terminal task statuses", () => {
    expect(getTaskStatusGroup("CREATED")).toBe("RUNNING");
    expect(getTaskStatusGroup("QUEUED")).toBe("RUNNING");
    expect(getTaskStatusGroup("RUNNING")).toBe("RUNNING");
    expect(getTaskStatusGroup("RETRYING")).toBe("RUNNING");
    expect(getTaskStatusGroup("SUCCEEDED")).toBe("SUCCEEDED");
    expect(getTaskStatusGroup("FAILED")).toBe("FAILED");
    expect(getTaskStatusGroup("CANCELED")).toBe("CANCELED");
  });

  it("identifies refreshable and retryable statuses", () => {
    expect(isRunningTaskStatus("RUNNING")).toBe(true);
    expect(isRunningTaskStatus("QUEUED")).toBe(true);
    expect(isRunningTaskStatus("SUCCEEDED")).toBe(false);
    expect(isRetryableTaskStatus("FAILED")).toBe(true);
    expect(isRetryableTaskStatus("CANCELED")).toBe(true);
    expect(isRetryableTaskStatus("RUNNING")).toBe(false);
  });

  it("returns readable labels and task identifiers", () => {
    expect(getTaskStatusLabel("QUEUED")).toBe("排队中");
    expect(getTaskStatusLabel("RUNNING")).toBe("处理中");
    expect(getTaskStatusLabel("FAILED")).toBe("处理失败");
    expect(getTaskStatusTagType("FAILED")).toBe("danger");
    expect(getTaskStatusTagType("SUCCEEDED")).toBe("success");
    expect(shortenTaskId("task_3367abcdef9a54")).toBe("task_3367...9a54");
    expect(shortenTaskId("task_short")).toBe("task_short");
  });
});
