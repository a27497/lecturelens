export interface PlaybackTokenResponse {
  token: string;
  expiresAt: string;
  playbackUrl: string;
}

export interface ApiResponse<T> {
  code: string;
  message: string;
  data: T;
  timestamp: string;
  traceId: string;
}
