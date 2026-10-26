import type { LearningScope } from "./learningScope";
import { authHeader } from "./authToken";
import { http } from "./http";
import type { ApiResponse } from "../types/task";

export type RunStatus = "queued" | "running" | "awaiting_approval" | "succeeded" | "failed" | "cancelled" | "budget_exceeded";
export interface StudyRun {
  learning_scope?: LearningScope | null;
  run_id: string; session_id: string; goal: string; request_key?: string; status: RunStatus;
  approval_required?: boolean;
  model_mode: "real" | "mock"; model_calls: number; tool_calls: number; error_code: string | null;
  created_at?: string;
  model_selection?: Record<string, { connection_id?: string | null; name: string; model: string; version: number;
    single_turn_evidence?: { ok: boolean; code: string | null; checked_at: number; version: number } | null }>;
}
export interface Citation { evidence_id: string; text: string; start_ms: number; end_ms: number; source_type: string }
export interface PracticeQuestion { question: string; evidence_ids: string[]; answer?: string; rubric?: string }
export interface StudyArtifact {
  kind?: "practice" | "insufficient_evidence"; artifact_id: string; title: string; explanation: string; evidence_ids: string[];
  human_edited?: boolean; edited_by?: number;
  questions: PracticeQuestion[]; citations: Citation[]; revision: number; mode: string;
}
export interface StudyApproval {
  kind: "practice" | "feedback"; decision: "approve" | "edit" | "reject" | null;
  preview?: { explanation?: string; title?: string; reason?: string; questions?: PracticeQuestion[];
    observations?: { observation: string; next_step?: string }[] };
}
export interface StudyResponse {
  approval?: StudyApproval | null;
  session_id?: string; revision?: number; mode?: string; events?: StudyEvent[];
  sessions?: { session_id: string; revision: number; created_at?: string }[];
  runs?: { run_id: string; goal: string; status: RunStatus; created_at: string }[];
  run?: StudyRun | null; artifact?: StudyArtifact | null; questions?: PracticeQuestion[];
  practice_results?: PracticeResult[];
  attempt?: StudyAttempt; attempts?: StudyAttempt[]; next_before_version?: number | null;
  feedback_enabled?: boolean; feedback?: StudyFeedback | null; feedback_runs?: StudyFeedbackRun[];
  note?: FeedbackNote; notes?: FeedbackNote[];
}
export interface StudyAttempt {
  attempt_id: string; artifact_id: string; question_index: number; version: number;
  answer_text: string; created_at: string;
}
export interface FeedbackNote {
  note_id: string; version: number; disposition: "disputed" | "acknowledged"; note_text: string; created_at: string;
}
export interface StudyFeedback {
  feedback_id: string; attempt_id: string; answer_version: number; question_index: number; answer_text: string;
  content: { kind: "guidance" | "insufficient_evidence"; reason?: string; human_guidance?: string; human_edited?: boolean; mode: string; citations: Citation[];
    observations?: { learner_quote: string; observation: string; next_step: string; action?: "revise" | "retain" | "clarify"; evidence_id: string; evidence_ids?: string[]; anchor_evidence_ids?: string[]; evidence_quote: string }[] };
  note: FeedbackNote | null;
}
export interface StudyFeedbackRun {
  run_id: string; request_key?: string; status: RunStatus; error_code: string | null;
  attempt_id: string; question_index: number; answer_version: number; feedback: StudyFeedback | null;
}
export interface StudyEvent { sequence: number; event_type: string; payload: { [key: string]: unknown; tool?: string; status?: RunStatus; error_code?: string; accepted?: boolean } }
export interface StudyCommand {
  learning_scope?: LearningScope;
  approval_required?: boolean; approval_decision?: "approve" | "edit" | "reject"; approval_edit?: string;
  operation: string; after?: number; session_id?: string; run_id?: string; goal?: string; request_key?: string;
  artifact_id?: string; question_index?: number; answer_text?: string; expected_version?: number; before_version?: number;
  attempt_id?: string; feedback_id?: string; note_text?: string; disposition?: "disputed" | "acknowledged";
}

export async function studyStatus(taskId: string): Promise<{ enabled: boolean; revision: number }> {
  const result = await http.get<ApiResponse<{ enabled: boolean; revision: number }>>(`/api/tasks/${encodeURIComponent(taskId)}/study/status`, { headers: authHeader() });
  return result.data.data;
}
export async function studyCommand(taskId: string, command: StudyCommand): Promise<StudyResponse> {
  // Capability reads and writes can reach different gateway versions during rollout.
  // Never fall back to the legacy route after a scoped request fails.
  const route = command.learning_scope ? "scoped-command" : "command";
  const result = await http.post<ApiResponse<StudyResponse>>(`/api/tasks/${encodeURIComponent(taskId)}/study/${route}`, command, { headers: authHeader() });
  return result.data.data;
}

export function drainStudyEvents(buffer: string): { events: StudyEvent[]; remaining: string } {
  const parts = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const remaining = parts.pop() ?? "";
  const events = parts.flatMap(part => {
    const data = part.split("\n").filter(line => line.startsWith("data:")).map(line => line.slice(5).trimStart()).join("\n");
    if (!data) return [];
    const event = JSON.parse(data) as StudyEvent;
    return Number.isSafeInteger(event.sequence) && event.sequence > 0 ? [event] : [];
  });
  return { events, remaining };
}

export async function studyEvents(taskId: string, sessionId: string, runId: string, after: number, signal: AbortSignal, onEvent: (event: StudyEvent) => void) {
  const base = (http.defaults.baseURL ?? "").replace(/\/$/, "");
  const url = `${base}/api/tasks/${encodeURIComponent(taskId)}/study/runs/${encodeURIComponent(runId)}/events?sessionId=${encodeURIComponent(sessionId)}&after=${after}`;
  const response = await fetch(url, { headers: { ...authHeader(), Accept: "text/event-stream" }, signal });
  if (!response.ok || !response.body) throw new Error(response.status === 404 || response.status === 409 ? "课程或会话已更新，请开启新会话。" : "连接中断，正在尝试恢复。 ");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let cursor = after;
  try {
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      if (buffer.length > 262144) throw new Error("事件数据过大");
      const parsed = drainStudyEvents(buffer);
      buffer = parsed.remaining;
      for (const event of parsed.events) {
        if (event.sequence > cursor) { cursor = event.sequence; onEvent(event); }
      }
    }
  } finally { reader.releaseLock(); }
}

export interface PracticeResult {
  question_index: number; attempt: StudyAttempt | null; feedback_run: StudyFeedbackRun | null;
  latest_feedback_status: RunStatus | null; latest_feedback_answer_version?: number | null;
}
