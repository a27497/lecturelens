import type { TaskEventMessage, TaskEventName, TaskEventPayload } from "../types/task";
import { authHeader, AccessTokenMissingError } from "./authToken";
import { http } from "./http";
import { AUTH_EXPIRED_MESSAGE } from "../utils/errorMessage";

const EVENT_BOUNDARY_PATTERN = /\n\n/;
const DEFAULT_EVENT_NAME: TaskEventName = "progress";

interface ConnectTaskEventsOptions {
  taskId: string;
  signal: AbortSignal;
  onOpen: () => void;
  onMessage: (message: TaskEventMessage) => void;
}

export class TaskEventConnectionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TaskEventConnectionError";
  }
}

export async function connectTaskEvents({
  taskId,
  signal,
  onOpen,
  onMessage,
}: ConnectTaskEventsOptions): Promise<void> {
  const response = await fetch(taskEventsUrl(taskId), {
    method: "GET",
    headers: {
      Accept: "text/event-stream",
      ...authHeader(),
    },
    signal,
  });

  if (!response.ok) {
    throw new TaskEventConnectionError(toReadableTaskEventStatus(response.status));
  }
  if (!response.body) {
    throw new TaskEventConnectionError("浏览器未返回任务事件流");
  }

  onOpen();

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      const parsed = drainEvents(buffer);
      buffer = parsed.remaining;
      parsed.messages.forEach(onMessage);
    }

    buffer += decoder.decode();
    const trailing = parseSseEvent(buffer.trim());
    if (trailing) {
      onMessage(trailing);
    }
  } finally {
    reader.releaseLock();
  }
}

export function isTaskEventAuthError(error: unknown): boolean {
  return (
    error instanceof AccessTokenMissingError ||
    (error instanceof TaskEventConnectionError && error.message === AUTH_EXPIRED_MESSAGE)
  );
}

export function toReadableTaskEventError(error: unknown): string {
  if (isTaskEventAuthError(error)) {
    return AUTH_EXPIRED_MESSAGE;
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return "";
  }
  if (error instanceof TaskEventConnectionError && error.message) {
    return error.message;
  }
  return "任务事件流连接失败，请稍后重试";
}

function taskEventsUrl(taskId: string): string {
  const rawBaseUrl = http.defaults.baseURL;
  const baseUrl = typeof rawBaseUrl === "string" ? rawBaseUrl.replace(/\/$/, "") : "";
  return `${baseUrl}/api/tasks/${encodeURIComponent(taskId)}/events`;
}

function drainEvents(buffer: string): { messages: TaskEventMessage[]; remaining: string } {
  const chunks = buffer.split(EVENT_BOUNDARY_PATTERN);
  const remaining = chunks.pop() ?? "";
  return {
    messages: chunks.flatMap((chunk) => {
      const message = parseSseEvent(chunk);
      return message ? [message] : [];
    }),
    remaining,
  };
}

function parseSseEvent(rawEvent: string): TaskEventMessage | null {
  if (!rawEvent.trim()) {
    return null;
  }

  let eventName: TaskEventName = DEFAULT_EVENT_NAME;
  const dataLines: string[] = [];

  rawEvent.split("\n").forEach((line) => {
    if (line.startsWith(":")) {
      return;
    }
    if (line.startsWith("event:")) {
      eventName = normalizeEventName(line.slice("event:".length).trim());
      return;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  });

  const dataText = dataLines.join("\n").trim();
  return {
    event: eventName,
    data: dataText ? (JSON.parse(dataText) as TaskEventPayload) : null,
  };
}

function normalizeEventName(value: string): TaskEventName {
  switch (value) {
    case "snapshot":
    case "progress":
    case "heartbeat":
    case "completed":
    case "failed":
    case "canceled":
    case "error":
      return value;
    default:
      return DEFAULT_EVENT_NAME;
  }
}

function toReadableTaskEventStatus(status: number): string {
  if (status === 401) {
    return AUTH_EXPIRED_MESSAGE;
  }
  if (status === 403) {
    return "你没有权限操作这个资源";
  }
  if (status === 404) {
    return "分析任务不存在或已被删除";
  }
  return "任务事件流连接失败，请稍后重试";
}
