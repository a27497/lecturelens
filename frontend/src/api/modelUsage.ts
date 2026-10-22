import { authHeader } from "./authToken";
import { http } from "./http";
import type { ApiResponse } from "../types/task";

export interface ModelRoute { feature: string; source: string; model: string | null }
export interface ModelSelection { snapshotId: string | null; configVersion: number; origin: string; recordedAt: string | null; routes: ModelRoute[] }
export interface CourseModelUsage {
  taskId: string; current: ModelSelection | null; pipeline: ModelSelection[];
  qa: { recordId: string; invocationState: string | null; callRecordId: string | null; provider: string | null; model: string | null; status: string; totalTokens: number | null; recordedAt: string; selection: ModelSelection | null }[];
  calls: { recordId: string; stage: string; provider: string; model: string | null; status: string; totalTokens: number | null; startedAt: string }[];
}
export async function getCourseModelUsage(taskId: string, signal?: AbortSignal): Promise<CourseModelUsage> {
  const result = await http.get<ApiResponse<CourseModelUsage>>(`/api/tasks/${encodeURIComponent(taskId)}/model-usage`, { headers: authHeader(), signal });
  return result.data.data;
}

export const featureLabels: Record<string, string> = { ASR_TRANSCRIPTION: "语音转写", TRANSLATION_FULL_TEXT: "全文翻译", SUBTITLE_TRANSLATION: "字幕翻译", LEARNING_PACKAGE: "学习资料", COURSE_CHAPTER: "课程章节", VISION_FRAME_ANALYSIS: "画面分析", COURSE_QA: "普通 QA" };
export function selectionSource(source: string) { return ({ DATABASE: "系统模型配置", ENV: "服务器默认", MOCK: "本地 Mock", NONE: "未配置" } as Record<string, string>)[source] ?? source; }
export function invocationLabel(state: string | null) { return ({ SKIPPED_NO_EVIDENCE: "跳过调用：证据不足", NOT_STARTED: "未发起调用", DISPATCHED: "已交给 Provider 适配器，未记录响应", RESPONSE_RECEIVED: "Provider 适配器已返回响应" } as Record<string, string>)[state ?? ""] ?? "调用阶段未记录"; }


interface SingleTurnEvidence { ok: boolean; code: string | null; checked_at: number; version: number }
export function singleTurnEvidence(value: unknown, version: unknown): SingleTurnEvidence | null {
  if (!value || typeof value !== "object" || Array.isArray(value) || typeof version !== "number" || !Number.isInteger(version) || version < 1 || version > 2147483647) return null;
  const check = value as Record<string, unknown>;
  if (check.version !== version || typeof check.checked_at !== "number" || !Number.isInteger(check.checked_at)
      || check.checked_at < 1 || check.checked_at > 253402300799 || typeof check.ok !== "boolean"
      || ![null, "MODEL_CHECK_FAILED", "MODEL_CHECK_TIMEOUT", "MODEL_TOOL_CONTRACT"].includes(check.code as string | null)
      || (check.ok && check.code !== null)) return null;
  return { ok: check.ok, code: check.code as string | null, checked_at: check.checked_at, version };
}
