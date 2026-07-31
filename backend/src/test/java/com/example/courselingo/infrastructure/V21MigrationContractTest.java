package com.example.courselingo.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

class V21MigrationContractTest {

    @Test
    void legacySourceLanguageRemainsNullableAndAiTimingMetricsAreAdded() throws Exception {
        String sql = new ClassPathResource(
            "db/migration/V21__add_analysis_task_source_language.sql"
        ).getContentAsString(StandardCharsets.UTF_8);
        String normalized = sql.replaceAll("\\s+", " ");

        assertThat(normalized)
            .contains("source_language VARCHAR(32) NULL")
            .doesNotContain("source_language VARCHAR(32) NOT NULL")
            .doesNotContain("DEFAULT 'auto'")
            .contains("provider_duration_millis BIGINT NULL")
            .contains("batch_count INT NULL")
            .contains("retry_count INT NULL");
    }
}
