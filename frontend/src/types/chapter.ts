export interface CourseChapterEvidenceItem {
  index: number;
  startTimeMillis: number;
  endTimeMillis: number;
  timeText: string;
  text: string;
}

export interface CourseChapterUsage {
  provider: string | null;
  model: string | null;
  promptTokens: number | null;
  completionTokens: number | null;
  totalTokens: number | null;
  durationMillis: number | null;
}

export interface CourseChapterResponse {
  id: number | null;
  chapterIndex: number;
  title: string;
  summary: string;
  keywords: string[];
  startTimeMillis: number;
  endTimeMillis: number;
  timeText: string;
  evidence: CourseChapterEvidenceItem[];
  usage: CourseChapterUsage | null;
}
