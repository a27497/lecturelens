package com.example.courselingo.subtitle;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

class SubtitleTranslationMigrationTest {

    private static final Path MIGRATION = Path.of(
        "src",
        "main",
        "resources",
        "db",
        "migration",
        "V5__create_subtitle_translation_segment_table.sql"
    );

    @Test
    void d8MigrationFileExists() {
        assertThat(MIGRATION).isRegularFile();
    }

    @Test
    void d8MigrationIsLoadableFromFlywayClasspathLocation() throws IOException {
        Resource[] resources = new PathMatchingResourcePatternResolver()
            .getResources("classpath:db/migration/V5__create_subtitle_translation_segment_table.sql");

        assertThat(resources).hasSize(1);
        assertThat(resources[0].exists()).isTrue();
    }

    @Test
    void d8MigrationDefinesTranslationColumnsConstraintsAndIndexes() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS subtitle_translation_segment");
        assertThat(sql).contains("id BIGINT NOT NULL AUTO_INCREMENT");
        assertThat(sql).contains("task_id VARCHAR(64) NOT NULL");
        assertThat(sql).contains("user_id BIGINT NOT NULL");
        assertThat(sql).contains("segment_index INT NOT NULL");
        assertThat(sql).contains("start_millis BIGINT NOT NULL");
        assertThat(sql).contains("end_millis BIGINT NOT NULL");
        assertThat(sql).contains("source_language VARCHAR(32) NOT NULL");
        assertThat(sql).contains("target_language VARCHAR(32) NOT NULL");
        assertThat(sql).contains("translated_text TEXT NOT NULL");
        assertThat(sql).contains("provider VARCHAR(64) NULL");
        assertThat(sql).contains("created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)");
        assertThat(sql).contains("updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)");
        assertThat(sql).contains("PRIMARY KEY (id)");
        assertThat(sql).contains("UNIQUE KEY uk_subtitle_translation_task_user_lang_index (task_id, user_id, target_language, segment_index)");
        assertThat(sql).contains("KEY idx_subtitle_translation_task_user_lang (task_id, user_id, target_language)");
        assertThat(sql).contains("KEY idx_subtitle_translation_user_created (user_id, created_at)");
        assertThat(sql).contains("CONSTRAINT fk_subtitle_translation_task_id");
        assertThat(sql).contains("FOREIGN KEY (task_id) REFERENCES analysis_task (id)");
        assertThat(sql).contains("CONSTRAINT fk_subtitle_translation_user_id");
        assertThat(sql).contains("FOREIGN KEY (user_id) REFERENCES user_account (id)");
        assertThat(sql).contains("CONSTRAINT chk_subtitle_translation_index_non_negative CHECK (segment_index >= 0)");
        assertThat(sql).contains("CONSTRAINT chk_subtitle_translation_start_non_negative CHECK (start_millis >= 0)");
        assertThat(sql).contains("CONSTRAINT chk_subtitle_translation_end_after_start CHECK (end_millis >= start_millis)");
    }

    @Test
    void d8MigrationDoesNotCreateArtifactMetadataAiCallOrSecretFields() throws IOException {
        String normalizedSql = readMigrationSql().toLowerCase();

        assertThat(normalizedSql).doesNotContain("artifact");
        assertThat(normalizedSql).doesNotContain("object_key");
        assertThat(normalizedSql).doesNotContain("metadata");
        assertThat(normalizedSql).doesNotContain("authorization");
        assertThat(normalizedSql).doesNotContain("access_token");
        assertThat(normalizedSql).doesNotContain("refresh_token");
        assertThat(normalizedSql).doesNotContain("api_key");
        assertThat(normalizedSql).doesNotContain("secret");
        assertThat(normalizedSql).doesNotContain("ai_call_record");
        assertThat(normalizedSql).doesNotContain("insert into");
        assertThat(normalizedSql).doesNotContain("c:\\");
        assertThat(normalizedSql).doesNotContain("/users/");
        assertThat(normalizedSql).doesNotContain("/home/");
    }

    private String readMigrationSql() throws IOException {
        return Files.readString(MIGRATION, StandardCharsets.UTF_8);
    }
}
