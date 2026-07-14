CREATE TABLE IF NOT EXISTS upload_session (
    id VARCHAR(64) NOT NULL COMMENT '上传会话 ID，由后端生成',
    user_id BIGINT NOT NULL COMMENT '上传所属用户 ID',
    filename VARCHAR(255) NOT NULL COMMENT '原始展示文件名，仅用于展示，不作为真实存储路径',
    ext VARCHAR(32) NOT NULL COMMENT '文件扩展名，后续上传安全校验使用',
    total_chunks INT NOT NULL COMMENT '总分片数',
    chunk_size_bytes BIGINT NOT NULL COMMENT '每个分片大小，单位字节',
    size_bytes BIGINT NOT NULL COMMENT '文件总大小，单位字节',
    file_md5 VARCHAR(64) NOT NULL COMMENT '完整文件 MD5，后续用于秒传和防重复分析',
    status VARCHAR(32) NOT NULL COMMENT '上传状态，例如 CREATED、UPLOADING、UPLOADED、MERGING、COMPLETED、FAILED、CANCELLED',
    storage_type VARCHAR(32) NOT NULL COMMENT '存储类型，最终版为 MinIO',
    object_key VARCHAR(255) NOT NULL COMMENT '对象存储 key，由后端生成，不使用用户原始文件名',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_upload_session_user_created (user_id, created_at),
    KEY idx_upload_session_md5 (file_md5),
    KEY idx_upload_session_user_status_created (user_id, status, created_at),
    CONSTRAINT fk_upload_session_user_id
        FOREIGN KEY (user_id) REFERENCES user_account (id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT chk_upload_session_total_chunks_positive CHECK (total_chunks > 0),
    CONSTRAINT chk_upload_session_chunk_size_positive CHECK (chunk_size_bytes > 0),
    CONSTRAINT chk_upload_session_size_positive CHECK (size_bytes > 0)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='上传会话表';
