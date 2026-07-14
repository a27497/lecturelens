import type { AnalysisTaskStatus } from "../types/task";

export type TaskStatusGroup = "ALL" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELED";
export type TaskStatusTagType = "primary" | "success" | "warning" | "danger" | "info";

const RUNNING_STATUSES = new Set<string>([
  "CREATED",
  "PENDING",
  "QUEUED",
  "RUNNING",
  "PROCESSING",
  "RETRYING",
  "CANCEL_REQUESTED",
]);

const CANCELED_STATUSES = new Set<string>(["CANCELED", "CANCELLED"]);

export function isRunningTaskStatus(status: AnalysisTaskStatus | string | null | undefined): boolean {
  return RUNNING_STATUSES.has(normalizeStatus(status));
}

export function isTerminalTaskStatus(status: AnalysisTaskStatus | string | null | undefined): boolean {
  const normalized = normalizeStatus(status);
  return normalized === "SUCCEEDED" || normalized === "FAILED" || CANCELED_STATUSES.has(normalized);
}

export function isRetryableTaskStatus(status: AnalysisTaskStatus | string | null | undefined): boolean {
  const normalized = normalizeStatus(status);
  return normalized === "FAILED" || CANCELED_STATUSES.has(normalized);
}

export function getTaskStatusGroup(status: AnalysisTaskStatus | string | null | undefined): TaskStatusGroup {
  const normalized = normalizeStatus(status);
  if (RUNNING_STATUSES.has(normalized)) {
    return "RUNNING";
  }
  if (normalized === "SUCCEEDED") {
    return "SUCCEEDED";
  }
  if (normalized === "FAILED") {
    return "FAILED";
  }
  if (CANCELED_STATUSES.has(normalized)) {
    return "CANCELED";
  }
  return "ALL";
}

export function getTaskStatusLabel(status: AnalysisTaskStatus | string | null | undefined): string {
  switch (normalizeStatus(status)) {
    case "CREATED":
    case "PENDING":
    case "QUEUED":
      return "排队中";
    case "RUNNING":
    case "PROCESSING":
      return "处理中";
    case "RETRYING":
      return "重试中";
    case "CANCEL_REQUESTED":
      return "正在取消";
    case "SUCCEEDED":
      return "已完成";
    case "FAILED":
      return "处理失败";
    case "CANCELED":
    case "CANCELLED":
      return "已取消";
    default:
      return "等待中";
  }
}

export function getTaskStatusTagType(status: AnalysisTaskStatus | string | null | undefined): TaskStatusTagType {
  switch (normalizeStatus(status)) {
    case "RUNNING":
    case "PROCESSING":
      return "primary";
    case "RETRYING":
    case "CANCEL_REQUESTED":
      return "warning";
    case "SUCCEEDED":
      return "success";
    case "FAILED":
      return "danger";
    case "CREATED":
    case "PENDING":
    case "QUEUED":
    case "CANCELED":
    case "CANCELLED":
    default:
      return "info";
  }
}

export function shortenTaskId(taskId: string): string {
  if (taskId.length <= 16) {
    return taskId;
  }
  return `${taskId.slice(0, 9)}...${taskId.slice(-4)}`;
}

function normalizeStatus(status: AnalysisTaskStatus | string | null | undefined): string {
  return (status || "").trim().toUpperCase();
}
