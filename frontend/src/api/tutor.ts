import { http } from "./http";
import { authHeader } from "./authToken";
import type { ApiResponse } from "../types/task";
import type { Citation } from "./study";

export interface TutorSession {
  session_id: string; revision: number; status: "active" | "stale";
  model_calls: number; max_calls: number;
}
export interface TutorTurn {
  turn_id: string; client_turn_id: string; ordinal: number; learner_text: string; socratic: boolean;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  outcome: "answered" | "socratic_prompt" | "insufficient_evidence" | "failed" | null;
  answer: string | null; evaluation: string | null; citations: Citation[]; error_code: string | null;
}
export interface TutorView { session: TutorSession; turns: TutorTurn[]; replayed?: boolean }
function base(taskId: string) { return `/api/tasks/${encodeURIComponent(taskId)}/tutor/sessions`; }
export async function listTutorSessions(taskId: string): Promise<{ sessions: TutorSession[]; revision: number }> {
  return (await http.get<ApiResponse<{ sessions: TutorSession[]; revision: number }>>(base(taskId), { headers: authHeader() })).data.data;
}
export async function createTutorSession(taskId: string, requestKey: string): Promise<{ session: TutorSession }> {
  return (await http.post<ApiResponse<{ session: TutorSession }>>(base(taskId), { request_key: requestKey }, { headers: authHeader() })).data.data;
}
export async function getTutorSession(taskId: string, sessionId: string): Promise<TutorView> {
  return (await http.get<ApiResponse<TutorView>>(`${base(taskId)}/${encodeURIComponent(sessionId)}`, { headers: authHeader() })).data.data;
}
export async function submitTutorTurn(taskId: string, sessionId: string, turn: { client_turn_id: string; text: string; socratic: boolean }): Promise<TutorView> {
  return (await http.post<ApiResponse<TutorView>>(`${base(taskId)}/${encodeURIComponent(sessionId)}/turns`, turn, { headers: authHeader() })).data.data;
}
export async function cancelTutorTurn(taskId: string, sessionId: string, clientTurnId: string): Promise<TutorView> {
  return (await http.post<ApiResponse<TutorView>>(`${base(taskId)}/${encodeURIComponent(sessionId)}/turns/${encodeURIComponent(clientTurnId)}/cancel`, {}, { headers: authHeader() })).data.data;
}
