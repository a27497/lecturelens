package com.example.courselingo.video.context;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class CourseVideoChunkMigrationTest {

    @Test
    void migrationCreatesCourseVideoChunkTableSafely() throws Exception {
        String sql = Files.readString(Path.of("src/main/resources/db/migration/V17__create_course_video_chunk.sql"));

        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS course_video_chunk");
        assertThat(sql).contains("uk_course_video_chunk_task_user_lang_index");
        assertThat(sql).contains("idx_course_video_chunk_task_user_time");
        assertThat(sql).contains("idx_course_video_chunk_user_created");
        assertThat(sql).contains("fk_course_video_chunk_task_id");
        assertThat(sql).contains("fk_course_video_chunk_user_id");
        assertThat(sql).doesNotContain("object_key");
        assertThat(sql).doesNotContain("local_path");
        assertThat(sql).doesNotContain("prompt");
        assertThat(sql).doesNotContain("response");
        assertThat(sql).doesNotContain("DROP TABLE");
        assertThat(sql).doesNotContain("TRUNCATE");
        assertThat(sql).doesNotContain("flyway_schema_history");
    }
}
