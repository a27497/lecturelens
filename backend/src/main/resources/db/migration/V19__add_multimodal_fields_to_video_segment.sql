ALTER TABLE video_segment
  ADD COLUMN translated_text TEXT NULL AFTER asr_text,
  ADD COLUMN source_status_json TEXT NULL AFTER evidence_json;
