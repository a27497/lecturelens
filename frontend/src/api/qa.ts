import { authHeader } from "./authToken";
import { http } from "./http";
import type { ApiResponse } from "../types/task";
import type { CourseQaAskRequest, CourseQaResponse } from "../types/qa";
import { isTimeoutError, toUserFriendlyError } from "../utils/errorMessage";

// Covers bounded retrieval + answer generation; document indexing runs in the background.
const configuredTimeout = Number(import.meta.env.VITE_COURSE_QA_TIMEOUT_MS);
export const COURSE_QA_REQUEST_TIMEOUT_MS = Number.isFinite(configuredTimeout) && configuredTimeout >= 5000
  ? Math.min(configuredTimeout, 600_000) : 180_000;
const COURSE_QA_TIMEOUT_MESSAGE = "等待课程回答超时，请稍后重试；后台处理可能仍在继续。";

function unwrap<T>(response: ApiResponse<T>): T {
  return response.data;
}

export async function askCourseQa(taskId: string, request: CourseQaAskRequest): Promise<CourseQaResponse> {
  const response = await http.post<ApiResponse<CourseQaResponse>>(
    `/api/tasks/${encodeURIComponent(taskId)}/qa`,
    request,
    { headers: authHeader(), timeout: COURSE_QA_REQUEST_TIMEOUT_MS },
  );
  return unwrap(response.data);
}

export function toReadableCourseQaError(error: unknown): string {
  if (isTimeoutError(error)) {
    return COURSE_QA_TIMEOUT_MESSAGE;
  }
  return toUserFriendlyError(error, "课程问答失败，请稍后重试");
}

export interface EvidenceIndexStatus {
  status: "DISABLED" | "PENDING" | "INDEXING" | "READY" | "FAILED";
  revision: number;
  indexedRevision: number | null;
  indexVersion: string | null;
  attempts: number;
  lastError: string | null;
  updatedAt: string | null;
}

export async function getEvidenceIndexStatus(taskId: string): Promise<EvidenceIndexStatus> {
  const response = await http.get<ApiResponse<EvidenceIndexStatus>>(
    `/api/tasks/${encodeURIComponent(taskId)}/evidence/index-status`, { headers: authHeader() },
  );
  return unwrap(response.data);
}
