package com.example.courselingo.fusion;

import static org.assertj.core.api.Assertions.assertThat;

import com.baomidou.mybatisplus.annotation.TableField;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;
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

    @Test
    void multimodalMigrationOnlyAddsNullableBackwardCompatibleColumns() throws Exception {
        String sql = Files.readString(Path.of(
            "src/main/resources/db/migration/V19__add_multimodal_fields_to_video_segment.sql"
        ));

        assertThat(sql)
            .contains("ALTER TABLE video_segment")
            .contains("translated_text TEXT NULL")
            .contains("source_status_json TEXT NULL")
            .doesNotContain("DROP ", "TRUNCATE", "NOT NULL", "flyway_schema_history");
        assertThat(sql.lines().filter(line -> line.contains("ADD COLUMN")).count()).isEqualTo(2);
        assertThat(sql.strip()).endsWith(";");
        assertThat(sql).doesNotContain("AUTOINCREMENT", "NVARCHAR", "CLOB", "GO\n");

        Map<String, String> mappedColumns = Arrays.stream(VideoSegment.class.getDeclaredFields())
            .filter(field -> field.isAnnotationPresent(TableField.class))
            .collect(Collectors.toMap(field -> field.getName(), field -> field.getAnnotation(TableField.class).value()));
        assertThat(mappedColumns)
            .containsEntry("translatedText", "translated_text")
            .containsEntry("sourceStatusJson", "source_status_json");
    }
}
