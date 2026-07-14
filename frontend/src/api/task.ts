import type {
  ApiResponse,
  CreateAnalysisTaskRequest,
  CreateAnalysisTaskResponse,
  TaskCommandResponse,
  TaskBatchDeleteRequest,
  TaskBatchDeleteResponse,
  TaskDetailResponse,
  TaskListResponse,
  TaskRetryResponse,
} from "../types/task";
import { authHeader } from "./authToken";
import { http } from "./http";
import { apiErrorCode, toUserFriendlyError } from "../utils/errorMessage";

export type TaskStatusFilter =
  | "ALL"
  | "CREATED"
  | "QUEUED"
  | "RUNNING"
  | "RETRYING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELED";

function unwrap<T>(response: ApiResponse<T>): T {
  return response.data;
}

export async function fetchTasks(
  page = 1,
  pageSize = 20,
  status: TaskStatusFilter = "ALL",
): Promise<TaskListResponse> {
  const response = await http.get<ApiResponse<TaskListResponse>>("/api/tasks", {
    headers: authHeader(),
    params: {
      page,
      pageSize,
      ...(status === "ALL" ? {} : { status }),
    },
  });
  return unwrap(response.data);
}

export async function fetchTaskDetail(taskId: string): Promise<TaskDetailResponse> {
  const response = await http.get<ApiResponse<TaskDetailResponse>>(
    `/api/tasks/${encodeURIComponent(taskId)}`,
    { headers: authHeader() },
  );
  return unwrap(response.data);
}

export async function createAnalysisTask(
  request: CreateAnalysisTaskRequest,
): Promise<CreateAnalysisTaskResponse> {
  const response = await http.post<ApiResponse<CreateAnalysisTaskResponse>>(
    "/api/tasks",
    request,
    { headers: authHeader() },
  );
  return unwrap(response.data);
}

export async function cancelTask(taskId: string): Promise<TaskCommandResponse> {
  const response = await http.post<ApiResponse<TaskCommandResponse>>(
    `/api/tasks/${encodeURIComponent(taskId)}/cancel`,
    undefined,
    { headers: authHeader() },
  );
  return unwrap(response.data);
}

export async function retryTask(taskId: string): Promise<TaskRetryResponse> {
  const response = await http.post<ApiResponse<TaskRetryResponse>>(
    `/api/tasks/${encodeURIComponent(taskId)}/retry`,
    undefined,
    { headers: authHeader() },
  );
  return unwrap(response.data);
}

export async function batchDeleteTasks(taskIds: string[]): Promise<TaskBatchDeleteResponse> {
  const request: TaskBatchDeleteRequest = { taskIds };
  const response = await http.post<ApiResponse<TaskBatchDeleteResponse>>(
    "/api/tasks/batch-delete",
    request,
    { headers: authHeader() },
  );
  return unwrap(response.data);
}

export function toReadableBatchDeleteError(error: unknown): string {
  const code = apiErrorCode(error);
  if (code === "TASK_DELETE_NOT_ALLOWED") {
    return "存在仍在处理中的课程，请先取消处理后再删除";
  }
  if (code === "TASK_NOT_FOUND") {
    return "部分课程已不存在，请刷新列表后重试";
  }
  return "删除失败，请稍后重试";
}

export function toReadableTaskError(error: unknown): string {
  return toUserFriendlyError(error, "任务请求失败，请稍后重试");
}
