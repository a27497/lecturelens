CREATE TABLE IF NOT EXISTS video_keyframe (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Video keyframe primary key',
    task_id VARCHAR(64) NOT NULL COMMENT 'Owner analysis task ID',
    user_id BIGINT NOT NULL COMMENT 'Owner user ID',
    frame_index INT NOT NULL COMMENT 'Extracted thumbnail frame index',
    timestamp_millis BIGINT NOT NULL COMMENT 'Video timestamp in milliseconds',
    time_text VARCHAR(32) NOT NULL COMMENT 'Display timestamp text',
    change_score DECIMAL(10,6) NOT NULL DEFAULT 0 COMMENT 'Normalized frame change score',
    select_reason VARCHAR(32) NOT NULL COMMENT 'FIRST_FRAME, PERIODIC_ANCHOR, SCENE_CHANGE, CONTENT_CHANGE',
    content_type VARCHAR(128) NOT NULL DEFAULT 'image/jpeg' COMMENT 'Thumbnail content type',
    storage_backend VARCHAR(32) NOT NULL DEFAULT 'MINIO' COMMENT 'Storage backend',
    object_key VARCHAR(512) NOT NULL COMMENT 'Internal storage object key, never returned by API',
    size_bytes BIGINT NOT NULL DEFAULT 0 COMMENT 'Thumbnail object size in bytes',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Created time',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT 'Updated time',
    PRIMARY KEY (id),
    UNIQUE KEY uk_video_keyframe_task_frame (task_id, frame_index),
    KEY idx_video_keyframe_task_time (task_id, timestamp_millis),
    KEY idx_video_keyframe_user_task_time (user_id, task_id, timestamp_millis),
    CONSTRAINT fk_video_keyframe_task_id
        FOREIGN KEY (task_id) REFERENCES analysis_task (id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT fk_video_keyframe_user_id
        FOREIGN KEY (user_id) REFERENCES user_account (id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT chk_video_keyframe_timestamp_non_negative CHECK (timestamp_millis >= 0),
    CONSTRAINT chk_video_keyframe_size_non_negative CHECK (size_bytes >= 0),
    CONSTRAINT chk_video_keyframe_reason_known CHECK (
        select_reason IN ('FIRST_FRAME', 'PERIODIC_ANCHOR', 'SCENE_CHANGE', 'CONTENT_CHANGE')
    )
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Low-cost video keyframe candidates';
