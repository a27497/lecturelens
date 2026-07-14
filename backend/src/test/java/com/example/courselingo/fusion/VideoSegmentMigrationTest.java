package com.example.courselingo.fusion;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class VideoSegmentMigrationTest {

    @Test
    void migrationCreatesVideoSegmentTableSafely() throws Exception {
        String sql = Files.readString(Path.of("src/main/resources/db/migration/V14__create_video_segment.sql"));

        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS video_segment");
        assertThat(sql).contains("uk_video_segment_task_user_index");
        assertThat(sql).contains("idx_video_segment_task_user_time");
        assertThat(sql).contains("fk_video_segment_task_id");
        assertThat(sql).contains("fk_video_segment_user_id");
        assertThat(sql).doesNotContain("DROP TABLE");
        assertThat(sql).doesNotContain("TRUNCATE");
        assertThat(sql).doesNotContain("flyway_schema_history");
    }
}
