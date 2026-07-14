CREATE TABLE IF NOT EXISTS user_account (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '用户账号主键',
    email VARCHAR(255) NOT NULL COMMENT '登录邮箱，唯一',
    password_hash VARCHAR(255) NOT NULL COMMENT 'BCrypt 哈希后的密码，不保存明文',
    status VARCHAR(32) NOT NULL COMMENT '用户状态，例如 ACTIVE、DISABLED、LOCKED',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_user_account_email (email),
    KEY idx_user_account_status (status)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='用户账号表';

CREATE TABLE IF NOT EXISTS refresh_token (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '刷新令牌主键',
    user_id BIGINT NOT NULL COMMENT '所属用户 ID',
    token_hash VARCHAR(255) NOT NULL COMMENT 'Refresh Token 哈希值，不保存原始 token',
    expires_at DATETIME(3) NOT NULL COMMENT '过期时间',
    revoked_at DATETIME(3) NULL COMMENT '撤销时间，NULL 表示未撤销',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_refresh_token_user_expires (user_id, expires_at),
    KEY idx_refresh_token_hash (token_hash),
    KEY idx_refresh_token_revoked (revoked_at),
    CONSTRAINT fk_refresh_token_user_id
        FOREIGN KEY (user_id) REFERENCES user_account (id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='刷新令牌表';
