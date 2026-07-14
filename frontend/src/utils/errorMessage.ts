import type { AxiosError } from "axios";
import { AccessTokenMissingError } from "../api/authToken";

export const AUTH_EXPIRED_MESSAGE = "登录已过期，请重新登录";
export const INVALID_CREDENTIALS_MESSAGE = "邮箱或密码不正确";
export const DEFAULT_ERROR_MESSAGE = "操作失败，请稍后重试";

const ERROR_CODE_MESSAGES: Record<string, string> = {
  AUTH_INVALID_CREDENTIALS: INVALID_CREDENTIALS_MESSAGE,
  AUTH_TOKEN_EXPIRED: AUTH_EXPIRED_MESSAGE,
  AUTH_TOKEN_INVALID: AUTH_EXPIRED_MESSAGE,
  COMMON_UNAUTHORIZED: AUTH_EXPIRED_MESSAGE,
  UNAUTHORIZED: AUTH_EXPIRED_MESSAGE,
  COMMON_FORBIDDEN: "你没有权限操作这个资源",
  FORBIDDEN: "你没有权限操作这个资源",
  UPLOAD_SESSION_FORBIDDEN: "你没有权限操作这个资源",
  TASK_NOT_OWNER: "你没有权限操作这个资源",
  MEDIA_PLAYBACK_FORBIDDEN: "你没有权限操作这个资源",
  UPLOAD_SESSION_NOT_FOUND: "上传任务不存在，请重新选择视频",
  UPLOAD_SESSION_NOT_COMPLETED: "视频还没有上传完成",
  TASK_NOT_FOUND: "分析任务不存在或已被删除",
  TASK_RETRY_NOT_ALLOWED: "当前任务不能重新分析",
  TASK_INVALID_STATUS: "当前任务状态不允许这个操作",
  MQ_SEND_FAILED: "消息队列配置异常，请联系管理员",
  AI_PROVIDER_TIMEOUT: "AI 服务响应较慢，请稍后重试",
  AI_PROVIDER_FAILED: "AI 服务临时异常，请稍后重试",
  MEDIA_PLAYBACK_TOKEN_EXPIRED: "播放链接已过期，请刷新播放链接",
  MEDIA_SOURCE_NOT_FOUND: "未找到原视频文件",
};

interface ErrorResponseData {
  code?: unknown;
  message?: unknown;
}

interface ErrorResponse {
  status?: number;
  data?: ErrorResponseData;
}

function asResponse(error: unknown): ErrorResponse | undefined {
  if (typeof error === "object" && error !== null && "response" in error) {
    return (error as { response?: ErrorResponse }).response;
  }
  return undefined;
}

export function apiErrorCode(error: unknown): string {
  const code = asResponse(error)?.data?.code;
  return typeof code === "string" ? code : "";
}

export function isTimeoutError(error: unknown): boolean {
  const response = asResponse(error);
  if (response?.status === 408) {
    return true;
  }
  const axiosError = error as Partial<AxiosError> | null;
  if (axiosError?.code === "ECONNABORTED" || axiosError?.code === "ETIMEDOUT") {
    return true;
  }
  return error instanceof Error && /timeout|timed out/i.test(error.message);
}

export function isNetworkError(error: unknown): boolean {
  if (typeof error === "object" && error !== null && "request" in error && !asResponse(error)) {
    return true;
  }
  return error instanceof Error && /network error|econnreset|socket hang up/i.test(error.message);
}

export function isAuthExpiredMessage(message: string): boolean {
  return message === AUTH_EXPIRED_MESSAGE || message === "登录已失效，请重新登录";
}

function statusMessage(status: number | undefined): string | undefined {
  if (status === 401) {
    return AUTH_EXPIRED_MESSAGE;
  }
  if (status === 403) {
    return "你没有权限操作这个资源";
  }
  return undefined;
}

function safeBackendMessage(error: unknown): string | undefined {
  const message = asResponse(error)?.data?.message;
  if (typeof message !== "string") {
    return undefined;
  }
  const trimmed = message.trim();
  if (!trimmed) {
    return undefined;
  }
  if (/exception|stack|trace|error:|at\s+\S+\(/i.test(trimmed)) {
    return undefined;
  }
  return /[\u4e00-\u9fff]/.test(trimmed) ? trimmed : undefined;
}

export function toUserFriendlyError(error: unknown, fallback = DEFAULT_ERROR_MESSAGE): string {
  if (error instanceof AccessTokenMissingError) {
    return AUTH_EXPIRED_MESSAGE;
  }

  const code = apiErrorCode(error);
  if (code && ERROR_CODE_MESSAGES[code]) {
    return ERROR_CODE_MESSAGES[code];
  }

  if (isTimeoutError(error)) {
    return "服务器响应较慢，请稍后重试";
  }

  if (isNetworkError(error)) {
    return "网络连接失败，请检查服务器是否可访问";
  }

  const status = asResponse(error)?.status;
  const mappedStatus = statusMessage(status);
  if (mappedStatus) {
    return mappedStatus;
  }

  return safeBackendMessage(error) || fallback;
}

export function toAuthEntryError(error: unknown): string {
  if (apiErrorCode(error) === "AUTH_INVALID_CREDENTIALS") {
    return INVALID_CREDENTIALS_MESSAGE;
  }
  if (isTimeoutError(error)) {
    return "服务器响应较慢，请稍后重试";
  }
  if (isNetworkError(error)) {
    return "网络连接失败，请检查服务器是否启动";
  }
  return toUserFriendlyError(error, "认证请求失败，请稍后重试");
}
