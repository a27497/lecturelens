import type {
  ApiResponse,
  CompleteUploadResponse,
  CreateUploadSessionRequest,
  CreateUploadSessionResponse,
  MissingChunksResponse,
  UploadChunkResponse,
} from "../types/upload";
import type { AxiosProgressEvent } from "axios";
import { AccessTokenMissingError, authHeader } from "./authToken";
import { http } from "./http";
import {
  AUTH_EXPIRED_MESSAGE,
  apiErrorCode,
  isNetworkError,
  isTimeoutError,
  toUserFriendlyError,
} from "../utils/errorMessage";

export const UPLOAD_CHUNK_RETRY_DELAYS_MS = [1000, 2000] as const;

const RETRYABLE_UPLOAD_STATUSES = new Set([408, 429, 500, 502, 503, 504]);
const NON_RETRYABLE_UPLOAD_STATUSES = new Set([400, 401, 403, 404, 413]);
const NON_RETRYABLE_UPLOAD_CODES = new Set([
  "UPLOAD_INVALID_CHUNK",
  "UPLOAD_SESSION_STATUS_INVALID",
  "UPLOAD_SESSION_NOT_FOUND",
]);

export class UploadAuthError extends Error {
  constructor() {
    super(AUTH_EXPIRED_MESSAGE);
    this.name = "UploadAuthError";
  }
}

function unwrap<T>(response: ApiResponse<T>): T {
  return response.data;
}

export async function createUploadSession(
  request: CreateUploadSessionRequest,
): Promise<CreateUploadSessionResponse> {
  const response = await http.post<ApiResponse<CreateUploadSessionResponse>>(
    "/api/uploads/sessions",
    request,
    { headers: authHeader() },
  );
  return unwrap(response.data);
}

export async function getMissingChunks(uploadId: string): Promise<MissingChunksResponse> {
  const response = await http.get<ApiResponse<MissingChunksResponse>>(
    `/api/uploads/sessions/${encodeURIComponent(uploadId)}/missing-chunks`,
    { headers: authHeader() },
  );
  return unwrap(response.data);
}

export async function uploadChunk(
  uploadId: string,
  chunkIndex: number,
  chunk: Blob,
  options: {
    onUploadProgress?: (event: AxiosProgressEvent) => void;
    signal?: AbortSignal;
  } = {},
): Promise<UploadChunkResponse> {
  const formData = new FormData();
  formData.append("file", chunk, `${chunkIndex}.part`);
  const response = await http.post<ApiResponse<UploadChunkResponse>>(
    `/api/uploads/sessions/${encodeURIComponent(uploadId)}/chunks/${chunkIndex}`,
    formData,
    { headers: authHeader(), onUploadProgress: options.onUploadProgress, signal: options.signal },
  );
  return unwrap(response.data);
}

export async function completeUpload(uploadId: string): Promise<CompleteUploadResponse> {
  const response = await http.post<ApiResponse<CompleteUploadResponse>>(
    `/api/uploads/sessions/${encodeURIComponent(uploadId)}/complete`,
    undefined,
    { headers: authHeader() },
  );
  return unwrap(response.data);
}

export function isUnauthorizedError(error: unknown): boolean {
  if (error instanceof UploadAuthError || error instanceof AccessTokenMissingError) {
    return true;
  }
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { status?: number } }).response;
    return response?.status === 401 || response?.status === 403;
  }
  return false;
}

function getUploadErrorStatus(error: unknown): number | undefined {
  if (typeof error === "object" && error !== null && "response" in error) {
    return (error as { response?: { status?: number } }).response?.status;
  }
  return undefined;
}

function getUploadErrorCode(error: unknown): string | undefined {
  const code = apiErrorCode(error);
  return code || undefined;
}

export function isUploadNetworkInterruption(error: unknown): boolean {
  return isNetworkError(error);
}

export function isUploadTimeoutError(error: unknown): boolean {
  return isTimeoutError(error);
}

export function isRetryableUploadError(error: unknown): boolean {
  if (isUnauthorizedError(error)) {
    return false;
  }
  const status = getUploadErrorStatus(error);
  const code = getUploadErrorCode(error);
  if (code && NON_RETRYABLE_UPLOAD_CODES.has(code)) {
    return false;
  }
  if (status && NON_RETRYABLE_UPLOAD_STATUSES.has(status)) {
    return false;
  }
  if (status && RETRYABLE_UPLOAD_STATUSES.has(status)) {
    return true;
  }
  return isUploadNetworkInterruption(error) || isUploadTimeoutError(error);
}

export function toUploadRetryingMessage(error: unknown): string {
  if (isUploadTimeoutError(error)) {
    return "分片上传超时，正在自动重试。";
  }
  if (isUploadNetworkInterruption(error)) {
    return "上传连接中断，正在自动重试。";
  }
  return "分片上传遇到网络波动，正在自动重试。";
}

export function toReadableUploadError(error: unknown): string {
  if (isUnauthorizedError(error)) {
    return AUTH_EXPIRED_MESSAGE;
  }
  if (isUploadTimeoutError(error)) {
    return "分片上传多次超时，请点击继续上传重试。";
  }
  const status = getUploadErrorStatus(error);
  if (status === 413) {
    return "上传分片过大，请检查分片大小和后端上传限制。";
  }
  if (isUploadNetworkInterruption(error)) {
    return "上传连接多次中断，请点击继续上传重试。";
  }
  return toUserFriendlyError(error, "上传失败，请稍后重试");
}
