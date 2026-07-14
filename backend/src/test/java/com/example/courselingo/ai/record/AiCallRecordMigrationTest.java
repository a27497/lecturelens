package com.example.courselingo.ai.record;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

class AiCallRecordMigrationTest {

    private static final Path MIGRATION = Path.of(
        "src",
        "main",
        "resources",
        "db",
        "migration",
        "V8__create_ai_call_record_table.sql"
    );

    @Test
    void d15MigrationFileExistsAndIsLoadableFromFlywayClasspathLocation() throws IOException {
        assertThat(MIGRATION).isRegularFile();
        Resource[] resources = new PathMatchingResourcePatternResolver()
            .getResources("classpath:db/migration/V8__create_ai_call_record_table.sql");

        assertThat(resources).hasSize(1);
        assertThat(resources[0].exists()).isTrue();
    }

    @Test
    void d15MigrationDefinesAiCallRecordColumnsConstraintsAndIndexes() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS ai_call_record");
        assertThat(sql).contains("id BIGINT NOT NULL AUTO_INCREMENT");
        assertThat(sql).contains("task_id VARCHAR(64) NOT NULL");
        assertThat(sql).contains("user_id BIGINT NOT NULL");
        assertThat(sql).contains("call_type VARCHAR(32) NOT NULL");
        assertThat(sql).contains("stage VARCHAR(64) NOT NULL");
        assertThat(sql).contains("provider VARCHAR(64) NOT NULL");
        assertThat(sql).contains("model VARCHAR(128) NULL");
        assertThat(sql).contains("status VARCHAR(32) NOT NULL");
        assertThat(sql).contains("started_at DATETIME(3) NOT NULL");
        assertThat(sql).contains("finished_at DATETIME(3) NULL");
        assertThat(sql).contains("duration_millis BIGINT NULL");
        assertThat(sql).contains("prompt_tokens INT NULL");
        assertThat(sql).contains("completion_tokens INT NULL");
        assertThat(sql).contains("total_tokens INT NULL");
        assertThat(sql).contains("input_units INT NULL");
        assertThat(sql).contains("output_units INT NULL");
        assertThat(sql).contains("request_fingerprint VARCHAR(128) NULL");
        assertThat(sql).contains("response_fingerprint VARCHAR(128) NULL");
        assertThat(sql).contains("error_code VARCHAR(64) NULL");
        assertThat(sql).contains("error_message VARCHAR(512) NULL");
        assertThat(sql).contains("retryable TINYINT(1) NULL");
        assertThat(sql).contains("PRIMARY KEY (id)");
        assertThat(sql).contains("KEY idx_ai_call_record_task_user (task_id, user_id)");
        assertThat(sql).contains("KEY idx_ai_call_record_user_created (user_id, created_at)");
        assertThat(sql).contains("KEY idx_ai_call_record_task_stage (task_id, stage)");
        assertThat(sql).contains("KEY idx_ai_call_record_status (status)");
        assertThat(sql).contains("CONSTRAINT fk_ai_call_record_task_id");
        assertThat(sql).contains("FOREIGN KEY (task_id) REFERENCES analysis_task (id)");
        assertThat(sql).contains("CONSTRAINT fk_ai_call_record_user_id");
        assertThat(sql).contains("FOREIGN KEY (user_id) REFERENCES user_account (id)");
        assertThat(sql).contains("CHECK (duration_millis IS NULL OR duration_millis >= 0)");
        assertThat(sql).contains("CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0)");
        assertThat(sql).contains("CHECK (completion_tokens IS NULL OR completion_tokens >= 0)");
        assertThat(sql).contains("CHECK (total_tokens IS NULL OR total_tokens >= 0)");
        assertThat(sql).contains("CHECK (input_units IS NULL OR input_units >= 0)");
        assertThat(sql).contains("CHECK (output_units IS NULL OR output_units >= 0)");
    }

    @Test
    void d15MigrationDoesNotStoreRawContentKeysSecretsOrPaths() throws IOException {
        String normalizedSql = readMigrationSql().toLowerCase();

        assertThat(normalizedSql).doesNotContain("raw_prompt");
        assertThat(normalizedSql).doesNotContain("raw_response");
        assertThat(normalizedSql).doesNotContain("completion_text");
        assertThat(normalizedSql).doesNotContain("asr_text");
        assertThat(normalizedSql).doesNotContain("subtitle_text");
        assertThat(normalizedSql).doesNotContain("audio_path");
        assertThat(normalizedSql).doesNotContain("local_path");
        assertThat(normalizedSql).doesNotContain("object_key");
        assertThat(normalizedSql).doesNotContain("authorization");
        assertThat(normalizedSql).doesNotContain("api_key");
        assertThat(normalizedSql).doesNotContain("access_token");
        assertThat(normalizedSql).doesNotContain("refresh_token");
        assertThat(normalizedSql).doesNotContain("api_token");
        assertThat(normalizedSql).doesNotContain("token_hash");
        assertThat(normalizedSql).doesNotContain("secret");
        assertThat(normalizedSql).doesNotContain("insert into");
        assertThat(normalizedSql).doesNotContain("c:\\");
        assertThat(normalizedSql).doesNotContain("/users/");
        assertThat(normalizedSql).doesNotContain("/home/");
    }

    private String readMigrationSql() throws IOException {
        return Files.readString(MIGRATION, StandardCharsets.UTF_8);
    }
}
