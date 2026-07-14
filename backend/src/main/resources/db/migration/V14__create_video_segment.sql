CREATE TABLE IF NOT EXISTS video_segment (
  id BIGINT NOT NULL AUTO_INCREMENT,
  task_id VARCHAR(64) NOT NULL,
  user_id BIGINT NOT NULL,
  segment_index INT NOT NULL,
  start_millis BIGINT NOT NULL,
  end_millis BIGINT NOT NULL,
  time_text VARCHAR(64),
  asr_text TEXT,
  ocr_text TEXT,
  visual_summary TEXT,
  fused_summary TEXT,
  keywords_json TEXT,
  evidence_json TEXT,
  confidence DECIMAL(8,4),
  status VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_video_segment_task_user_index (task_id, user_id, segment_index),
  KEY idx_video_segment_task_user_time (task_id, user_id, start_millis),
  CONSTRAINT fk_video_segment_task_id
    FOREIGN KEY (task_id) REFERENCES analysis_task (id)
    ON DELETE CASCADE
    ON UPDATE RESTRICT,
  CONSTRAINT fk_video_segment_user_id
    FOREIGN KEY (user_id) REFERENCES user_account (id)
    ON DELETE CASCADE
    ON UPDATE RESTRICT,
  CONSTRAINT chk_video_segment_index CHECK (segment_index >= 0),
  CONSTRAINT chk_video_segment_time CHECK (start_millis >= 0 AND end_millis >= start_millis),
  CONSTRAINT chk_video_segment_status CHECK (status IN ('SUCCEEDED', 'EMPTY', 'FAILED', 'SKIPPED', 'DISABLED'))
);
