package com.example.courselingo.task;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class AnalysisTaskMigrationTest {

    private static final Path MIGRATION = Path.of(
        "src",
        "main",
        "resources",
        "db",
        "migration",
        "V3__init_analysis_task_and_task_log.sql"
    );

    @Test
    void c1MigrationFileExists() {
        assertThat(MIGRATION).isRegularFile();
    }

    @Test
    void c1MigrationDefinesAnalysisTaskTableColumnsConstraintsAndIndexes() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS analysis_task");
        assertThat(sql).contains("id VARCHAR(64) NOT NULL");
        assertThat(sql).contains("user_id BIGINT NOT NULL");
        assertThat(sql).contains("upload_id VARCHAR(64) NOT NULL");
        assertThat(sql).contains("target_language VARCHAR(32) NOT NULL");
        assertThat(sql).contains("status VARCHAR(32) NOT NULL DEFAULT 'CREATED'");
        assertThat(sql).contains("progress_percent INT NOT NULL DEFAULT 0");
        assertThat(sql).contains("current_stage VARCHAR(64) NULL");
        assertThat(sql).contains("error_code VARCHAR(64) NULL");
        assertThat(sql).contains("error_message VARCHAR(1024) NULL");
        assertThat(sql).contains("retry_count INT NOT NULL DEFAULT 0");
        assertThat(sql).contains("max_retry_count INT NOT NULL DEFAULT 3");
        assertThat(sql).contains("PRIMARY KEY (id)");
        assertThat(sql).contains("KEY idx_analysis_task_user_created (user_id, created_at)");
        assertThat(sql).contains("KEY idx_analysis_task_user_status_created (user_id, status, created_at)");
        assertThat(sql).contains("KEY idx_analysis_task_upload (upload_id)");
        assertThat(sql).contains("KEY idx_analysis_task_status_created (status, created_at)");
        assertThat(sql).contains("CONSTRAINT fk_analysis_task_user_id");
        assertThat(sql).contains("FOREIGN KEY (user_id) REFERENCES user_account (id)");
        assertThat(sql).contains("CONSTRAINT fk_analysis_task_upload_id");
        assertThat(sql).contains("FOREIGN KEY (upload_id) REFERENCES upload_session (id)");
        assertThat(sql).contains("CONSTRAINT chk_analysis_task_progress_percent_range CHECK (progress_percent >= 0 AND progress_percent <= 100)");
        assertThat(sql).contains("CONSTRAINT chk_analysis_task_retry_count_non_negative CHECK (retry_count >= 0)");
        assertThat(sql).contains("CONSTRAINT chk_analysis_task_max_retry_count_non_negative CHECK (max_retry_count >= 0)");
    }

    @Test
    void c1MigrationDefinesTaskLogTableColumnsConstraintsAndIndexes() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS task_log");
        assertThat(sql).contains("id BIGINT NOT NULL AUTO_INCREMENT");
        assertThat(sql).contains("task_id VARCHAR(64) NOT NULL");
        assertThat(sql).contains("user_id BIGINT NOT NULL");
        assertThat(sql).contains("level VARCHAR(16) NOT NULL");
        assertThat(sql).contains("stage VARCHAR(64) NULL");
        assertThat(sql).contains("message VARCHAR(1024) NOT NULL");
        assertThat(sql).contains("detail TEXT NULL");
        assertThat(sql).contains("PRIMARY KEY (id)");
        assertThat(sql).contains("KEY idx_task_log_task_created (task_id, created_at)");
        assertThat(sql).contains("KEY idx_task_log_user_created (user_id, created_at)");
        assertThat(sql).contains("KEY idx_task_log_level_created (level, created_at)");
        assertThat(sql).contains("CONSTRAINT fk_task_log_task_id");
        assertThat(sql).contains("FOREIGN KEY (task_id) REFERENCES analysis_task (id)");
        assertThat(sql).contains("CONSTRAINT fk_task_log_user_id");
        assertThat(sql).contains("FOREIGN KEY (user_id) REFERENCES user_account (id)");
        assertThat(sql).contains("CONSTRAINT chk_task_log_level_known CHECK (level IN ('INFO', 'WARN', 'ERROR'))");
    }

    @Test
    void c1MigrationUsesExpectedForeignKeyDeletePolicies() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).containsPattern("(?s)CONSTRAINT fk_analysis_task_user_id.*ON DELETE CASCADE\\s+ON UPDATE RESTRICT");
        assertThat(sql).containsPattern("(?s)CONSTRAINT fk_analysis_task_upload_id.*ON DELETE RESTRICT\\s+ON UPDATE RESTRICT");
        assertThat(sql).containsPattern("(?s)CONSTRAINT fk_task_log_task_id.*ON DELETE CASCADE\\s+ON UPDATE RESTRICT");
        assertThat(sql).containsPattern("(?s)CONSTRAINT fk_task_log_user_id.*ON DELETE CASCADE\\s+ON UPDATE RESTRICT");
    }

    @Test
    void c1MigrationDoesNotSeedDataOrLeakSecretsOrLocalPaths() throws IOException {
        String normalizedSql = readMigrationSql().toLowerCase();

        assertThat(normalizedSql).doesNotContain("insert into");
        assertThat(normalizedSql).doesNotContain("access_token");
        assertThat(normalizedSql).doesNotContain("refresh_token");
        assertThat(normalizedSql).doesNotContain("api_key");
        assertThat(normalizedSql).doesNotContain("secret_key");
        assertThat(normalizedSql).doesNotContain("minio_secret");
        assertThat(normalizedSql).doesNotContain("c:\\");
        assertThat(normalizedSql).doesNotContain("/users/");
        assertThat(normalizedSql).doesNotContain("/home/");
    }

    @Test
    void c1MigrationDefinesConstraintsForRequiredRuntimeBehavior() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("target_language VARCHAR(32) NOT NULL");
        assertThat(sql).contains("status VARCHAR(32) NOT NULL DEFAULT 'CREATED'");
        assertThat(sql).contains("level VARCHAR(16) NOT NULL");
        assertThat(sql).contains("message VARCHAR(1024) NOT NULL");
        assertThat(sql).contains("ON DELETE RESTRICT");
        assertThat(sql).contains("CONSTRAINT chk_analysis_task_progress_percent_range CHECK (progress_percent >= 0 AND progress_percent <= 100)");
        assertThat(sql).contains("CONSTRAINT chk_analysis_task_retry_count_non_negative CHECK (retry_count >= 0)");
        assertThat(sql).contains("CONSTRAINT chk_analysis_task_max_retry_count_non_negative CHECK (max_retry_count >= 0)");
    }

    private String readMigrationSql() throws IOException {
        return Files.readString(MIGRATION, StandardCharsets.UTF_8);
    }
}
