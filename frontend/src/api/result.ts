import { AccessTokenMissingError, authHeader } from "./authToken";
import { http } from "./http";
import type { ApiResponse, ResultArtifactFile, TaskResultResponse } from "../types/result";
import { toUserFriendlyError } from "../utils/errorMessage";

function unwrap<T>(response: ApiResponse<T>): T {
  return response.data;
}

export async function fetchTaskResult(taskId: string): Promise<TaskResultResponse> {
  const response = await http.get<ApiResponse<TaskResultResponse>>(
    `/api/tasks/${encodeURIComponent(taskId)}/results`,
    { headers: authHeader() },
  );
  return unwrap(response.data);
}

export async function downloadTaskArtifactText(
  taskId: string,
  artifact: Pick<ResultArtifactFile, "artifactType" | "language">,
): Promise<string> {
  const response = await http.get<string>(
    `/api/tasks/${encodeURIComponent(taskId)}/artifacts/${encodeURIComponent(
      artifact.artifactType,
    )}/${encodeURIComponent(artifact.language)}/download`,
    {
      headers: {
        ...authHeader(),
        Accept: "text/plain, text/vtt, text/markdown, application/json, */*",
      },
      responseType: "text",
      transformResponse: [(data) => data],
    },
  );
  return typeof response.data === "string" ? response.data : "";
}

export async function downloadTaskKeyframeImage(taskId: string, frameId: number): Promise<Blob> {
  const response = await http.get<Blob>(
    `/api/tasks/${encodeURIComponent(taskId)}/keyframes/${encodeURIComponent(String(frameId))}/image`,
    {
      headers: {
        ...authHeader(),
        Accept: "image/jpeg,image/*",
      },
      responseType: "blob",
    },
  );
  return response.data;
}

export function isTaskResultAuthError(error: unknown): boolean {
  if (error instanceof AccessTokenMissingError) {
    return true;
  }
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { status?: number } }).response;
    return response?.status === 401 || response?.status === 403;
  }
  return false;
}

export function toReadableTaskResultError(error: unknown): string {
  return toUserFriendlyError(error, "结果加载失败，请稍后重试");
}
