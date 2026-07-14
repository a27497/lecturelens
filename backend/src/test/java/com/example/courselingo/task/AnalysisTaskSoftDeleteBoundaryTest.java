package com.example.courselingo.task;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class AnalysisTaskSoftDeleteBoundaryTest {

    private static final Path MAPPER = Path.of(
        "src", "main", "java", "com", "example", "courselingo", "task", "mapper", "AnalysisTaskMapper.java"
    );

    @Test
    void userVisibleReadsAndCommandsRequireDeletedAtNull() throws IOException {
        String source = Files.readString(MAPPER, StandardCharsets.UTF_8);

        assertThat(source).contains("selectByIdAndUserId");
        assertThat(source).contains("selectPageByUserId");
        assertThat(source).contains("countByUserId");
        assertThat(source).contains("updateStateByIdAndUserId");
        assertThat(source).contains("updateRetryingByIdAndUserId");
        assertThat(source).contains("updateRunningProgressByIdAndUserId");
        assertThat(source.split("isNull\\(AnalysisTask::getDeletedAt\\)", -1)).hasSizeGreaterThanOrEqualTo(7);
    }

    @Test
    void batchDeleteHasExplicitIncludingDeletedReadAndSingleUpdate() throws IOException {
        String source = Files.readString(MAPPER, StandardCharsets.UTF_8);

        assertThat(source).contains("selectByIdsAndUserIdIncludingDeleted");
        assertThat(source).contains("softDeleteByIdsAndUserId");
        assertThat(source).contains(".in(AnalysisTask::getId, ids)");
        assertThat(source).contains(".in(AnalysisTask::getStatus, allowedStatuses)");
        assertThat(source).contains(".set(AnalysisTask::getDeletedAt, deletedAt)");
        assertThat(source).doesNotContain("deleteById", "deleteBatchIds", "delete(Wrappers");
    }
}
