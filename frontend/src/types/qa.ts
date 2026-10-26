import type { LearningScope } from "../api/learningScope";
export interface CourseQaAskRequest {
  learning_scope?: LearningScope;
  question: string;
}

export interface CourseQaEvidenceItem {
  sourceType: string;
  sourceId: string;
  startTimeMillis: number;
  endTimeMillis: number;
  timeText: string;
  snippet: string;
  translatedSnippet: string;
  confidence: number | null;
  evidenceId?: string | null;
  revision?: number | null;
}

export interface CourseQaUsage {
  provider: string;
  model: string | null;
  promptTokens: number | null;
  completionTokens: number | null;
  totalTokens: number | null;
  durationMillis: number | null;
}

export interface CourseQaResponse {
  learning_scope?: LearningScope | null;
  recordId: string;
  answer: string;
  evidence: CourseQaEvidenceItem[];
  usage: CourseQaUsage | null;
}

export interface CourseQaHistoryItem {
  recordId: string; question: string; answer: string; status: "SUCCEEDED" | "FAILED";
  createdAt: string | null; evidence: CourseQaEvidenceItem[];
  sourceStatus: "current" | "partial" | "unavailable" | "none";
}
export interface CourseQaHistoryPage { items: CourseQaHistoryItem[]; nextCursor: string | null }
