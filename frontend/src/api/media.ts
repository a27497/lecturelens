import type { ApiResponse, PlaybackTokenResponse } from "../types/media";
import { authHeader } from "./authToken";
import { http } from "./http";
import { toUserFriendlyError } from "../utils/errorMessage";

function unwrap<T>(response: ApiResponse<T>): T {
  return response.data;
}

export async function requestUploadPlaybackToken(uploadId: string): Promise<PlaybackTokenResponse> {
  const response = await http.post<ApiResponse<PlaybackTokenResponse>>(
    `/api/uploads/${encodeURIComponent(uploadId)}/playback-token`,
    undefined,
    { headers: authHeader() },
  );
  return unwrap(response.data);
}

export async function requestTaskPlaybackToken(taskId: string): Promise<PlaybackTokenResponse> {
  const response = await http.post<ApiResponse<PlaybackTokenResponse>>(
    `/api/tasks/${encodeURIComponent(taskId)}/playback-token`,
    undefined,
    { headers: authHeader() },
  );
  return unwrap(response.data);
}

export function toReadablePlaybackError(error: unknown): string {
  return toUserFriendlyError(error, "播放链接获取失败，请稍后重试");
}
