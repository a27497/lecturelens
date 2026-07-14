export type AnalysisTaskStatus =
  | "CREATED"
  | "QUEUED"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELED"
  | "RETRYING";

export type TaskEventName =
  | "snapshot"
  | "progress"
  | "heartbeat"
  | "completed"
  | "failed"
  | "canceled"
  | "error";

export type TaskConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "closed"
  | "error";

export interface TaskEventPayload {
  taskId: string;
  status: AnalysisTaskStatus;
  progressPercent: number;
  currentStage: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  updatedAt: string;
  completedChunks?: number | null;
  totalChunks?: number | null;
  currentChunkIndex?: number | null;
  stepDetail?: string | null;
}

export interface TaskEventMessage {
  event: TaskEventName;
  data: TaskEventPayload | null;
}

export interface ApiResponse<T> {
  code: string;
  message: string;
  data: T;
  timestamp: string;
  traceId: string;
}

export interface TaskSummaryResponse {
  taskId: string;
  uploadId: string;
  targetLanguage: string;
  status: AnalysisTaskStatus;
  progressPercent: number | null;
  currentStage: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  retryCount: number | null;
  maxRetryCount: number | null;
  createdAt: string | null;
  updatedAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
}

export type TaskDetailResponse = TaskSummaryResponse;

export interface TaskListResponse {
  items: TaskSummaryResponse[];
  page: number;
  pageSize: number;
  total: number;
}

export interface CreateAnalysisTaskRequest {
  uploadId: string;
  targetLanguage: string;
}

export interface CreateAnalysisTaskResponse {
  taskId: string;
  uploadId: string;
  status: AnalysisTaskStatus;
  targetLanguage: string;
}

export interface TaskCommandResponse {
  taskId: string;
  status: AnalysisTaskStatus;
}

export interface TaskRetryResponse {
  originalTaskId: string;
  newTaskId: string;
  status: AnalysisTaskStatus;
  message: string;
}

export interface TaskBatchDeleteRequest {
  taskIds: string[];
}

export interface TaskBatchDeleteResponse {
  requestedCount: number;
  deletedCount: number;
}
