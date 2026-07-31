import { authHeader } from "./authToken";
import { http } from "./http";
import type { ApiResponse } from "../types/task";
import type { CourseChapterResponse } from "../types/chapter";
import { isTimeoutError, toUserFriendlyError } from "../utils/errorMessage";

export const COURSE_CHAPTER_REQUEST_TIMEOUT_MS = 70_000;
const COURSE_CHAPTER_TIMEOUT_MESSAGE = "课程章节生成请求已超时，本次请求已结束，请稍后重试。";

function unwrap<T>(response: ApiResponse<T>): T {
  return response.data;
}

export async function fetchCourseChapters(taskId: string): Promise<CourseChapterResponse[]> {
  const response = await http.get<ApiResponse<CourseChapterResponse[]>>(
    `/api/tasks/${encodeURIComponent(taskId)}/chapters`,
    { headers: authHeader() },
  );
  return unwrap(response.data);
}

export async function generateCourseChapters(taskId: string): Promise<CourseChapterResponse[]> {
  const response = await http.post<ApiResponse<CourseChapterResponse[]>>(
    `/api/tasks/${encodeURIComponent(taskId)}/chapters/generate`,
    undefined,
    { headers: authHeader(), timeout: COURSE_CHAPTER_REQUEST_TIMEOUT_MS },
  );
  return unwrap(response.data);
}

export function toReadableCourseChapterError(error: unknown): string {
  if (isTimeoutError(error)) {
    return COURSE_CHAPTER_TIMEOUT_MESSAGE;
  }
  return toUserFriendlyError(error, "课程章节操作失败，请稍后重试");
}
