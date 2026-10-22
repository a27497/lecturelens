import { http } from "./http";
import { authHeader } from "./authToken";
import type { ApiResponse } from "../types/task";

export interface LearningScope { version: 1; kind: "course" | "segments"; policy: "strict" | "course"; revision: number; evidence_ids: string[] }
export interface ScopeEvidence { evidenceId: string; revision: number; sourceType: string; startMs: number; endMs: number; normalizedText: string; retrievable: boolean }
export interface ScopePage { learningScopeVersion: number; revision: number; stale: boolean; items: ScopeEvidence[]; nextCursor: string | null }
export async function fetchScopeEvidence(taskId: string, after = "", revision?: number): Promise<ScopePage> {
  const response = await http.get<ApiResponse<ScopePage>>(`/api/tasks/${encodeURIComponent(taskId)}/evidence`, {
    headers: authHeader(), params: { limit: 200, after, ...(revision === undefined ? {} : { revision }) },
  });
  if (response.data.data.learningScopeVersion !== 1) throw Error("服务端尚不支持结构化学习范围，请使用兼容版本后重试。");
  return response.data.data;
}
export function scopeLabel(scope: LearningScope | null | undefined): string {
  if (!scope || scope.kind === "course") return "整节课程";
  return `选中 ${scope.evidence_ids.length} 个课程片段 · ${scope.policy === "strict" ? "仅限选中范围" : "允许扩展到整课"}`;
}
