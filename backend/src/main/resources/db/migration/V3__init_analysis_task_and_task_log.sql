CREATE TABLE IF NOT EXISTS analysis_task (
    id VARCHAR(64) NOT NULL COMMENT '分析任务 ID，由后端生成',
    user_id BIGINT NOT NULL COMMENT '任务所属用户 ID',
    upload_id VARCHAR(64) NOT NULL COMMENT '关联上传会话 ID',
    target_language VARCHAR(32) NOT NULL COMMENT '目标语言',
    status VARCHAR(32) NOT NULL DEFAULT 'CREATED' COMMENT '任务状态，状态流转由 C2 实现',
    progress_percent INT NOT NULL DEFAULT 0 COMMENT '任务进度百分比，范围 0 到 100',
    current_stage VARCHAR(64) NULL COMMENT '当前处理阶段',
    error_code VARCHAR(64) NULL COMMENT '失败错误码',
    error_message VARCHAR(1024) NULL COMMENT '失败错误摘要，不记录密钥或本地路径',
    retry_count INT NOT NULL DEFAULT 0 COMMENT '已重试次数',
    max_retry_count INT NOT NULL DEFAULT 3 COMMENT '最大重试次数',
    started_at DATETIME(3) NULL COMMENT '任务开始时间',
    finished_at DATETIME(3) NULL COMMENT '任务结束时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_analysis_task_user_created (user_id, created_at),
    KEY idx_analysis_task_user_status_created (user_id, status, created_at),
    KEY idx_analysis_task_upload (upload_id),
    KEY idx_analysis_task_status_created (status, created_at),
    CONSTRAINT fk_analysis_task_user_id
        FOREIGN KEY (user_id) REFERENCES user_account (id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT fk_analysis_task_upload_id
        FOREIGN KEY (upload_id) REFERENCES upload_session (id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT,
    CONSTRAINT chk_analysis_task_progress_percent_range CHECK (progress_percent >= 0 AND progress_percent <= 100),
    CONSTRAINT chk_analysis_task_retry_count_non_negative CHECK (retry_count >= 0),
    CONSTRAINT chk_analysis_task_max_retry_count_non_negative CHECK (max_retry_count >= 0)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='分析任务表';

CREATE TABLE IF NOT EXISTS task_log (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '任务日志主键',
    task_id VARCHAR(64) NOT NULL COMMENT '所属分析任务 ID',
    user_id BIGINT NOT NULL COMMENT '日志所属用户 ID',
    level VARCHAR(16) NOT NULL COMMENT '日志级别：INFO、WARN、ERROR',
    stage VARCHAR(64) NULL COMMENT '任务阶段',
    message VARCHAR(1024) NOT NULL COMMENT '日志摘要，不记录密钥或本地路径',
    detail TEXT NULL COMMENT '内部错误详情，不记录 access token、refresh token、API key、secret key、本地路径或 MinIO secret',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_task_log_task_created (task_id, created_at),
    KEY idx_task_log_user_created (user_id, created_at),
    KEY idx_task_log_level_created (level, created_at),
    CONSTRAINT fk_task_log_task_id
        FOREIGN KEY (task_id) REFERENCES analysis_task (id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT fk_task_log_user_id
        FOREIGN KEY (user_id) REFERENCES user_account (id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT chk_task_log_level_known CHECK (level IN ('INFO', 'WARN', 'ERROR'))
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='任务日志表';
