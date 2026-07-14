package com.example.courselingo.vision.ocr;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

class VideoKeyframeOcrMigrationTest {

    private static final Path MIGRATION = Path.of(
        "src",
        "main",
        "resources",
        "db",
        "migration",
        "V12__create_video_keyframe_ocr_table.sql"
    );

    @Test
    void v12MigrationFileExistsAndIsLoadableFromFlywayClasspathLocation() throws IOException {
        assertThat(MIGRATION).isRegularFile();
        Resource[] resources = new PathMatchingResourcePatternResolver()
            .getResources("classpath:db/migration/V12__create_video_keyframe_ocr_table.sql");

        assertThat(resources).hasSize(1);
        assertThat(resources[0].exists()).isTrue();
    }

    @Test
    void v12MigrationIsIdempotentForServerDeployment() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS video_keyframe_ocr");
        assertThat(sql).doesNotContain("CREATE TABLE video_keyframe_ocr");
        assertThat(sql.toLowerCase()).doesNotContain("drop table");
        assertThat(sql.toLowerCase()).doesNotContain("insert into flyway_schema_history");
    }

    @Test
    void v12MigrationDefinesOcrColumnsConstraintsAndIndexes() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("task_id VARCHAR(64) NOT NULL");
        assertThat(sql).contains("user_id BIGINT NOT NULL");
        assertThat(sql).contains("keyframe_id BIGINT NOT NULL");
        assertThat(sql).contains("timestamp_millis BIGINT NOT NULL");
        assertThat(sql).contains("provider VARCHAR(64) NOT NULL");
        assertThat(sql).contains("language_hint VARCHAR(64) NOT NULL");
        assertThat(sql).contains("ocr_text TEXT NULL");
        assertThat(sql).contains("text_length INT NOT NULL DEFAULT 0");
        assertThat(sql).contains("text_truncated TINYINT(1) NOT NULL DEFAULT 0");
        assertThat(sql).contains("confidence DECIMAL(5,4) NULL");
        assertThat(sql).contains("status VARCHAR(32) NOT NULL");
        assertThat(sql).contains("error_code VARCHAR(64) NULL");
        assertThat(sql).contains("error_message VARCHAR(255) NULL");
        assertThat(sql).contains("duration_millis BIGINT NULL");
        assertThat(sql).contains("UNIQUE KEY uk_video_keyframe_ocr_keyframe (keyframe_id)");
        assertThat(sql).contains("KEY idx_video_keyframe_ocr_task_user_time (task_id, user_id, timestamp_millis)");
        assertThat(sql).contains("CONSTRAINT fk_video_keyframe_ocr_keyframe_id");
        assertThat(sql).contains("CONSTRAINT fk_video_keyframe_ocr_task_id");
        assertThat(sql).contains("CONSTRAINT fk_video_keyframe_ocr_user_id");
    }

    private String readMigrationSql() throws IOException {
        return Files.readString(MIGRATION, StandardCharsets.UTF_8);
    }
}
