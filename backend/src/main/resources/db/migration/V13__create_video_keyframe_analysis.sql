CREATE TABLE IF NOT EXISTS video_keyframe_analysis (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    keyframe_id BIGINT NOT NULL,
    timestamp_millis BIGINT NOT NULL,
    provider VARCHAR(64) NULL,
    model VARCHAR(128) NULL,
    screen_type VARCHAR(64) NULL,
    visual_summary TEXT NULL,
    detected_elements_json TEXT NULL,
    status VARCHAR(32) NOT NULL,
    error_code VARCHAR(64) NULL,
    error_message VARCHAR(512) NULL,
    duration_millis BIGINT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_video_keyframe_analysis_keyframe (keyframe_id),
    KEY idx_video_keyframe_analysis_task_user_time (task_id, user_id, timestamp_millis),
    CONSTRAINT fk_video_keyframe_analysis_keyframe_id
        FOREIGN KEY (keyframe_id) REFERENCES video_keyframe(id)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT fk_video_keyframe_analysis_task_id
        FOREIGN KEY (task_id) REFERENCES analysis_task(id)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT fk_video_keyframe_analysis_user_id
        FOREIGN KEY (user_id) REFERENCES user_account(id)
        ON DELETE CASCADE ON UPDATE RESTRICT
);
