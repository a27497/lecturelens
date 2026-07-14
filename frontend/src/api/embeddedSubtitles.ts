import type { ApiResponse } from "../types/media";
import type { EmbeddedSubtitleProbeResponse } from "../types/embeddedSubtitles";
import { authHeader } from "./authToken";
import { http } from "./http";
import { apiErrorCode, toUserFriendlyError } from "../utils/errorMessage";

function unwrap<T>(response: ApiResponse<T>): T {
  return response.data;
}

export async function probeUploadEmbeddedSubtitles(uploadId: string): Promise<EmbeddedSubtitleProbeResponse> {
  const response = await http.get<ApiResponse<EmbeddedSubtitleProbeResponse>>(
    `/api/uploads/${encodeURIComponent(uploadId)}/embedded-subtitles`,
    { headers: authHeader() },
  );
  return unwrap(response.data);
}

export async function downloadUploadEmbeddedSubtitle(uploadId: string, streamIndex: number): Promise<string> {
  const response = await http.get<string>(
    `/api/uploads/${encodeURIComponent(uploadId)}/embedded-subtitles/${streamIndex}/download`,
    {
      headers: { ...authHeader(), Accept: "text/vtt" },
      responseType: "text",
    },
  );
  return response.data;
}

export async function probeTaskEmbeddedSubtitles(taskId: string): Promise<EmbeddedSubtitleProbeResponse> {
  const response = await http.get<ApiResponse<EmbeddedSubtitleProbeResponse>>(
    `/api/tasks/${encodeURIComponent(taskId)}/embedded-subtitles`,
    { headers: authHeader() },
  );
  return unwrap(response.data);
}

export async function downloadTaskEmbeddedSubtitle(taskId: string, streamIndex: number): Promise<string> {
  const response = await http.get<string>(
    `/api/tasks/${encodeURIComponent(taskId)}/embedded-subtitles/${streamIndex}/download`,
    {
      headers: { ...authHeader(), Accept: "text/vtt" },
      responseType: "text",
    },
  );
  return response.data;
}

export function toReadableEmbeddedSubtitleError(error: unknown): string {
  const code = apiErrorCode(error);
  if (code === "MEDIA_SUBTITLE_UNSUPPORTED") {
    return "原视频自带字幕：暂不支持该字幕格式";
  }
  if (code === "MEDIA_SOURCE_NOT_FOUND") {
    return "原视频自带字幕：未检测到";
  }
  return toUserFriendlyError(error, "原视频自带字幕加载失败");
}
