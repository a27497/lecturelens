export interface CourseQaAskRequest {
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
  recordId: string;
  answer: string;
  evidence: CourseQaEvidenceItem[];
  usage: CourseQaUsage | null;
}
