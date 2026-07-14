export type EmbeddedSubtitleStatus = "FOUND" | "NOT_FOUND" | "UNSUPPORTED";

export interface EmbeddedSubtitleTrack {
  streamIndex: number;
  codecName: string;
  language: string;
  title: string;
  defaultTrack: boolean;
  supported: boolean;
  unsupportedReason: string;
}

export interface EmbeddedSubtitleProbeResponse {
  status: EmbeddedSubtitleStatus;
  tracks: EmbeddedSubtitleTrack[];
  selectedStreamIndex: number | null;
}
