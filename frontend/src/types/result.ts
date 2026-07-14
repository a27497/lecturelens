export interface ApiResponse<T> {
  code: string;
  message: string;
  data: T;
  timestamp: string;
  traceId: string;
}

export interface ResultSubtitleSegment {
  segmentIndex: number;
  startMillis: number;
  endMillis: number;
  language: string;
  sourceText: string;
}

export interface ResultTranslationSegment {
  segmentIndex: number;
  startMillis: number;
  endMillis: number;
  sourceLanguage: string;
  targetLanguage: string;
  translatedText: string;
}

export interface KeyPointItem {
  index: number;
  text: string;
}

export interface GlossaryItem {
  term: string;
  definition: string;
  translation: string;
}

export interface QaItem {
  question: string;
  answer: string;
}

export interface ResultLearningPackage {
  targetLanguage: string;
  title: string;
  summary: string;
  keyPoints: KeyPointItem[];
  glossary: GlossaryItem[];
  qa: QaItem[];
}

export interface ResultArtifactFile {
  artifactType: string;
  language: string;
  fileName: string;
  contentType: string;
  sizeBytes: number;
  sha256: string;
  createdAt: string;
}

export interface ResultKeyframe {
  frameId: number;
  timestampMillis: number;
  timeText: string;
  imageUrl: string;
  changeScore: number;
  selectReason: string;
  createdAt: string;
  ocr: ResultKeyframeOcr | null;
  visualAnalysis: ResultKeyframeVisualAnalysis | null;
}

export type ResultKeyframeOcrStatus = "PENDING" | "SUCCEEDED" | "EMPTY" | "FAILED" | "SKIPPED" | "DISABLED";

export interface ResultKeyframeOcr {
  status: ResultKeyframeOcrStatus;
  text: string;
  provider: string;
  languageHint: string;
  confidence: number | null;
  truncated: boolean;
  message: string;
}

export type ResultKeyframeVisualAnalysisStatus =
  "PENDING"
  | "SUCCEEDED"
  | "EMPTY"
  | "FAILED"
  | "SKIPPED"
  | "DISABLED";

export interface ResultKeyframeVisualAnalysis {
  status: ResultKeyframeVisualAnalysisStatus;
  screenType: string;
  summary: string;
  detectedElements: string[];
  provider: string;
  model: string;
  message: string;
}

export type ResultVideoSegmentStatus = "SUCCEEDED" | "EMPTY" | "FAILED" | "SKIPPED" | "DISABLED";

export interface ResultVideoSegmentEvidence {
  subtitleSegmentIds: number[];
  keyframeIds: number[];
  ocrIds: number[];
  visualAnalysisIds: number[];
  counts: Record<string, number>;
}

export interface ResultVideoSegment {
  segmentId: number;
  segmentIndex: number;
  startMillis: number;
  endMillis: number;
  timeText: string;
  asrText: string;
  ocrText: string;
  visualSummary: string;
  fusedSummary: string;
  keywords: string[];
  evidence: ResultVideoSegmentEvidence;
  status: ResultVideoSegmentStatus;
  confidence: number | null;
}

export interface ResultAiCallRecord {
  id: number;
  callType: string;
  stage: string;
  provider: string;
  model: string | null;
  status: string;
  durationMillis: number | null;
  promptTokens: number | null;
  completionTokens: number | null;
  totalTokens: number | null;
  createdAt: string;
}

export interface TaskResultResponse {
  taskId: string;
  targetLanguage: string;
  sourceFullText: string;
  sourceParagraphs: string[];
  translatedFullText: string;
  subtitles: ResultSubtitleSegment[];
  translations: ResultTranslationSegment[];
  learningPackage: ResultLearningPackage | null;
  artifacts: ResultArtifactFile[];
  keyframes: ResultKeyframe[];
  videoSegments: ResultVideoSegment[];
  aiCallRecords: ResultAiCallRecord[];
}
