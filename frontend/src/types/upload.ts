export interface ApiResponse<T> {
  code: string;
  message: string;
  data: T;
  timestamp: string;
  traceId: string;
}

export interface CreateUploadSessionRequest {
  filename: string;
  sizeBytes: number;
  chunkSizeBytes: number;
  totalChunks: number;
  fileMd5: string;
}

export interface CreateUploadSessionResponse {
  uploadId: string;
  status: string;
}

export interface MissingChunksResponse {
  uploadId: string;
  totalChunks: number;
  uploadedChunks: number[];
  missingChunks: number[];
  allUploaded: boolean;
  status: string;
}

export interface UploadChunkResponse {
  uploadId: string;
  chunkIndex: number;
  uploaded: boolean;
  status: string;
}

export interface CompleteUploadResponse {
  uploadId: string;
  status: string;
  sizeBytes: number;
  fileMd5: string;
}

export interface SelectedUploadFile {
  file: File;
  extension: string;
  isSupportedExtension: boolean;
}

export type UploadPhase =
  | "empty"
  | "ready"
  | "hashing"
  | "creating"
  | "checking"
  | "uploading"
  | "paused"
  | "completing"
  | "success"
  | "error";

export interface UploadProgressSnapshot {
  phase: UploadPhase;
  statusText: string;
  progressPercent: number;
  uploadedChunks: number;
  totalChunks: number;
}
