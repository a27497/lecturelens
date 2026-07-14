import {
  getTaskStatusGroup,
  getTaskStatusLabel,
  getTaskStatusTagType,
  isRetryableTaskStatus,
  isRunningTaskStatus,
  shortenTaskId,
} from "./taskStatus.ts";

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, got ${String(actual)}`);
  }
}

function assertTrue(actual: boolean, message: string) {
  assertEqual(actual, true, message);
}

function assertFalse(actual: boolean, message: string) {
  assertEqual(actual, false, message);
}

assertEqual(getTaskStatusGroup("CREATED"), "RUNNING", "CREATED should be grouped as running");
assertEqual(getTaskStatusGroup("QUEUED"), "RUNNING", "QUEUED should be grouped as running");
assertEqual(getTaskStatusGroup("RUNNING"), "RUNNING", "RUNNING should be grouped as running");
assertEqual(getTaskStatusGroup("RETRYING"), "RUNNING", "RETRYING should be grouped as running");
assertEqual(getTaskStatusGroup("SUCCEEDED"), "SUCCEEDED", "SUCCEEDED should be completed");
assertEqual(getTaskStatusGroup("FAILED"), "FAILED", "FAILED should be failed");
assertEqual(getTaskStatusGroup("CANCELED"), "CANCELED", "CANCELED should be canceled");

assertTrue(isRunningTaskStatus("RUNNING"), "RUNNING should auto-refresh");
assertTrue(isRunningTaskStatus("QUEUED"), "QUEUED should auto-refresh");
assertFalse(isRunningTaskStatus("SUCCEEDED"), "SUCCEEDED should not auto-refresh");
assertTrue(isRetryableTaskStatus("FAILED"), "FAILED should be retryable");
assertTrue(isRetryableTaskStatus("CANCELED"), "CANCELED should be retryable");
assertFalse(isRetryableTaskStatus("RUNNING"), "RUNNING should not be retryable");

assertEqual(getTaskStatusLabel("QUEUED"), "排队中", "QUEUED label");
assertEqual(getTaskStatusLabel("RUNNING"), "处理中", "RUNNING label");
assertEqual(getTaskStatusLabel("FAILED"), "处理失败", "FAILED label");
assertEqual(getTaskStatusTagType("FAILED"), "danger", "FAILED tag");
assertEqual(getTaskStatusTagType("SUCCEEDED"), "success", "SUCCEEDED tag");

assertEqual(shortenTaskId("task_3367abcdef9a54"), "task_3367...9a54", "long task id should be shortened");
assertEqual(shortenTaskId("task_short"), "task_short", "short task id should remain readable");
