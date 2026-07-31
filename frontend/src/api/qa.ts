import { authHeader } from "./authToken";
import { http } from "./http";
import type { ApiResponse } from "../types/task";
import type { CourseQaAskRequest, CourseQaResponse } from "../types/qa";
import { isTimeoutError, toUserFriendlyError } from "../utils/errorMessage";

export const COURSE_QA_REQUEST_TIMEOUT_MS = 55_000;
const COURSE_QA_TIMEOUT_MESSAGE = "课程问答请求已超时，本次请求已结束，请缩短问题或稍后重试。";

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
