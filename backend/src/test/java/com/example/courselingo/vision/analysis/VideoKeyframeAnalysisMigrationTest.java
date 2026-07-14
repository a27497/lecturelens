package com.example.courselingo.vision.analysis;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

class VideoKeyframeAnalysisMigrationTest {

    private static final Path MIGRATION = Path.of(
        "src",
        "main",
        "resources",
        "db",
        "migration",
        "V13__create_video_keyframe_analysis.sql"
    );

    @Test
    void v13MigrationFileExistsAndIsLoadableFromFlywayClasspathLocation() throws IOException {
        assertThat(MIGRATION).isRegularFile();
        Resource[] resources = new PathMatchingResourcePatternResolver()
            .getResources("classpath:db/migration/V13__create_video_keyframe_analysis.sql");

        assertThat(resources).hasSize(1);
        assertThat(resources[0].exists()).isTrue();
    }

    @Test
    void v13MigrationIsIdempotentAndDoesNotMutateHistory() throws IOException {
        String sql = Files.readString(MIGRATION, StandardCharsets.UTF_8);

        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS video_keyframe_analysis");
        assertThat(sql).doesNotContain("CREATE TABLE video_keyframe_analysis");
        assertThat(sql.toLowerCase()).doesNotContain("drop table");
        assertThat(sql.toLowerCase()).doesNotContain("insert into flyway_schema_history");
    }

    @Test
    void v13MigrationDefinesColumnsIndexesAndForeignKeys() throws IOException {
        String sql = Files.readString(MIGRATION, StandardCharsets.UTF_8);

        assertThat(sql).contains("task_id VARCHAR(64) NOT NULL");
        assertThat(sql).contains("user_id BIGINT NOT NULL");
        assertThat(sql).contains("keyframe_id BIGINT NOT NULL");
        assertThat(sql).contains("timestamp_millis BIGINT NOT NULL");
        assertThat(sql).contains("provider VARCHAR(64) NULL");
        assertThat(sql).contains("model VARCHAR(128) NULL");
        assertThat(sql).contains("screen_type VARCHAR(64) NULL");
        assertThat(sql).contains("visual_summary TEXT NULL");
        assertThat(sql).contains("detected_elements_json TEXT NULL");
        assertThat(sql).contains("status VARCHAR(32) NOT NULL");
        assertThat(sql).contains("UNIQUE KEY uk_video_keyframe_analysis_keyframe (keyframe_id)");
        assertThat(sql).contains("KEY idx_video_keyframe_analysis_task_user_time (task_id, user_id, timestamp_millis)");
        assertThat(sql).contains("CONSTRAINT fk_video_keyframe_analysis_keyframe_id");
        assertThat(sql).contains("CONSTRAINT fk_video_keyframe_analysis_task_id");
        assertThat(sql).contains("CONSTRAINT fk_video_keyframe_analysis_user_id");
    }
}
