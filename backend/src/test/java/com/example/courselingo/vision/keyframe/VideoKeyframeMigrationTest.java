package com.example.courselingo.vision.keyframe;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

class VideoKeyframeMigrationTest {

    private static final Path MIGRATION = Path.of(
        "src",
        "main",
        "resources",
        "db",
        "migration",
        "V11__create_video_keyframe_table.sql"
    );

    @Test
    void v11MigrationFileExistsAndIsLoadableFromFlywayClasspathLocation() throws IOException {
        assertThat(MIGRATION).isRegularFile();
        Resource[] resources = new PathMatchingResourcePatternResolver()
            .getResources("classpath:db/migration/V11__create_video_keyframe_table.sql");

        assertThat(resources).hasSize(1);
        assertThat(resources[0].exists()).isTrue();
    }

    @Test
    void v11MigrationIsIdempotentForServerManualTableBackfill() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS video_keyframe");
        assertThat(sql).doesNotContain("CREATE TABLE video_keyframe");
        assertThat(sql.toLowerCase()).doesNotContain("drop table");
        assertThat(sql.toLowerCase()).doesNotContain("insert into flyway_schema_history");
    }

    @Test
    void v11MigrationDefinesKeyframeColumnsConstraintsAndIndexes() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("task_id VARCHAR(64) NOT NULL");
        assertThat(sql).contains("user_id BIGINT NOT NULL");
        assertThat(sql).contains("frame_index INT NOT NULL");
        assertThat(sql).contains("timestamp_millis BIGINT NOT NULL");
        assertThat(sql).contains("object_key VARCHAR(512) NOT NULL");
        assertThat(sql).contains("UNIQUE KEY uk_video_keyframe_task_frame (task_id, frame_index)");
        assertThat(sql).contains("KEY idx_video_keyframe_task_time (task_id, timestamp_millis)");
        assertThat(sql).contains("KEY idx_video_keyframe_user_task_time (user_id, task_id, timestamp_millis)");
        assertThat(sql).contains("CONSTRAINT fk_video_keyframe_task_id");
        assertThat(sql).contains("CONSTRAINT fk_video_keyframe_user_id");
    }

    private String readMigrationSql() throws IOException {
        return Files.readString(MIGRATION, StandardCharsets.UTF_8);
    }
}
