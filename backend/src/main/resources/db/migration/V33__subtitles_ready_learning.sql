-- Subtitles-ready learning (PIPELINE_EARLY_LEARNING_ENABLED). A RUNNING course becomes learnable once
-- its subtitles are published; translation and materials then complete in the background. NULL keeps
-- the historical rule that only SUCCEEDED courses are learnable, so existing rows are unaffected.
ALTER TABLE analysis_task ADD COLUMN learning_ready_at DATETIME(3) NULL;

-- Independent outcome of each background stage of the current run. A failed stage disables only its
-- own feature; it never marks the whole course FAILED.
CREATE TABLE task_stage_outcome (
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    stage VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL,
    error_code VARCHAR(64) NULL,
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (task_id, stage),
    CONSTRAINT fk_stage_outcome_task FOREIGN KEY (task_id) REFERENCES analysis_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
