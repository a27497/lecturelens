package com.example.courselingo.task;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class AnalysisTaskSoftDeleteMigrationTest {

    private static final Path MIGRATION = Path.of(
        "src", "main", "resources", "db", "migration", "V18__add_analysis_task_soft_delete.sql"
    );

    @Test
    void v18AddsNullableSoftDeleteTimestampAndListIndexes() throws IOException {
        String sql = Files.readString(MIGRATION, StandardCharsets.UTF_8);

        assertThat(sql).contains("ALTER TABLE analysis_task");
        assertThat(sql).contains("deleted_at DATETIME(3) NULL");
        assertThat(sql).contains("用户逻辑删除时间，NULL表示未删除");
        assertThat(sql).contains("idx_analysis_task_user_deleted_created (user_id, deleted_at, created_at)");
        assertThat(sql).contains("idx_analysis_task_user_deleted_status_created (user_id, deleted_at, status, created_at)");
    }

    @Test
    void v18DoesNotBackfillDeleteOrRebuildData() throws IOException {
        String sql = Files.readString(MIGRATION, StandardCharsets.UTF_8).toLowerCase();

        assertThat(sql).doesNotContain("drop table");
        assertThat(sql).doesNotContain("delete from");
        assertThat(sql).doesNotContain("update analysis_task");
        assertThat(sql).doesNotContain("insert into");
        assertThat(sql).doesNotContain("drop index");
    }
}
