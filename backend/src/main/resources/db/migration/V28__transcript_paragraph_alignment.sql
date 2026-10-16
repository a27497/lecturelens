ALTER TABLE subtitle_segment
    ADD COLUMN timing_source VARCHAR(32) NOT NULL DEFAULT 'ESTIMATED',
    ADD COLUMN timing_reason VARCHAR(64) NULL;

-- Persist the measured plan and aggregate ASR attempt counts once, not once per paragraph.
CREATE TABLE transcript_timing_plan (
    task_id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    source_fingerprint CHAR(64) NOT NULL,
    plan_hash CHAR(64) NOT NULL,
    plan_json JSON NOT NULL,
    asr_attempt_count INT NOT NULL,
    clip_count INT NOT NULL,
    detected_silence_millis BIGINT NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT fk_timing_plan_task FOREIGN KEY(task_id) REFERENCES analysis_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE transcript_paragraph (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    source_fingerprint CHAR(64) NOT NULL,
    paragraph_no INT NOT NULL,
    start_millis BIGINT NOT NULL,
    end_millis BIGINT NOT NULL,
    member_count INT NOT NULL,
    short_reason VARCHAR(64) NULL,
    UNIQUE KEY uk_transcript_paragraph(task_id,user_id,source_fingerprint,paragraph_no),
    CONSTRAINT fk_paragraph_task FOREIGN KEY(task_id) REFERENCES analysis_task(id) ON DELETE CASCADE,
    CONSTRAINT chk_paragraph_interval CHECK(start_millis>=0 AND end_millis>start_millis)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE transcript_alignment_publication (
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    target_language VARCHAR(32) NOT NULL,
    source_fingerprint CHAR(64) NOT NULL,
    config_version BIGINT NOT NULL,
    PRIMARY KEY(task_id,user_id,target_language),
    CONSTRAINT fk_alignment_publication_task FOREIGN KEY(task_id) REFERENCES analysis_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE transcript_paragraph_member (
    paragraph_id VARCHAR(64) NOT NULL,
    ordinal INT NOT NULL,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    source_segment_index INT NOT NULL,
    source_hash CHAR(64) NOT NULL,
    PRIMARY KEY(paragraph_id,ordinal),
    UNIQUE KEY uk_paragraph_source(task_id,user_id,source_segment_index),
    CONSTRAINT fk_paragraph_member_parent FOREIGN KEY(paragraph_id) REFERENCES transcript_paragraph(id) ON DELETE CASCADE,
    CONSTRAINT fk_paragraph_member_source FOREIGN KEY(task_id,user_id,source_segment_index)
        REFERENCES subtitle_segment(task_id,user_id,segment_index) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
