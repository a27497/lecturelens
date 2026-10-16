package com.example.courselingo.subtitle.diagnostic;

import static org.assertj.core.api.Assertions.assertThat;
import com.example.courselingo.ai.llm.*;
import com.example.courselingo.systemmodel.SystemModelExecutionRef;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

class TranslationCallDiagnosticsTest {
    private JdbcTemplate jdbc;
    private TranslationCallDiagnostics diagnostics;
    private final SystemModelExecutionRef ref = new SystemModelExecutionRef("snapshot", 10, "task", 7);

    @BeforeEach void setup() {
        var ds = new DriverManagerDataSource("jdbc:h2:mem:" + java.util.UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE system_model_execution_snapshot(id VARCHAR(64) PRIMARY KEY,task_id VARCHAR(64),user_id BIGINT,config_version BIGINT)");
        jdbc.update("INSERT INTO system_model_execution_snapshot VALUES('snapshot','task',7,10)");
        new ResourceDatabasePopulator(new ClassPathResource("db/migration/V26__translation_call_diagnostic.sql")).execute(ds);
        jdbc.execute("ALTER TABLE translation_call_diagnostic ADD COLUMN attempt_id VARCHAR(64) NULL");
        diagnostics = new TranslationCallDiagnostics(jdbc, new DataSourceTransactionManager(ds));
    }

    @Test void failedResponseKeepsUsageAndRedactsBeforeTruncating() throws Exception {
        String key = "synthetic-active-credential";
        String body = "{\"api_key\":\"other-secret-value\",\"echo\":\"" + key + "\",\"note\":\"Bearer other-bearer-value\",\"padding\":\"" + "a".repeat(4050) + key + "\"}";
        var root = new ObjectMapper().readTree("{\"choices\":[{\"finish_reason\":\"length\",\"message\":{\"content\":\"\"}}],\"usage\":{\"prompt_tokens\":301,\"completion_tokens\":3072,\"total_tokens\":3373}}");
        diagnostics.provider("call", request(ref), "deepseek-flash", 1, 200, body, key, root, "CONTENT_EMPTY", 100);
        var row = jdbc.queryForMap("SELECT * FROM translation_call_diagnostic");
        assertThat(row.get("PROVIDER_REASON")).isEqualTo("CONTENT_EMPTY");
        assertThat(row.get("PROMPT_TOKENS")).isEqualTo(301);
        assertThat(row.get("COMPLETION_TOKENS")).isEqualTo(3072);
        assertThat(row.get("TOTAL_TOKENS")).isEqualTo(3373);
        assertThat(row.get("FINISH_REASON")).isEqualTo("length");
        String excerpt = (String) row.get("RESPONSE_EXCERPT");
        assertThat(excerpt).hasSize(4000).contains("[redacted]").doesNotContain(key, "other-secret-value", "other-bearer-value");
        assertThat(row.get("RESPONSE_TRUNCATED")).isEqualTo(true);
        assertThat(row.get("RESPONSE_CHARS")).isEqualTo(body.length());
    }

    @Test void unknownUsageStaysNullAndObservationSurvivesCallerRollback() {
        var outer = new org.springframework.transaction.support.TransactionTemplate(new DataSourceTransactionManager(jdbc.getDataSource()));
        outer.executeWithoutResult(tx -> {
            diagnostics.provider("call", request(ref), "deepseek-flash", 1, null, null, null, null, "TIMEOUT", 12);
            tx.setRollbackOnly();
        });
        var row = jdbc.queryForMap("SELECT * FROM translation_call_diagnostic");
        assertThat(row.get("PROMPT_TOKENS")).isNull();
        assertThat(row.get("TOTAL_TOKENS")).isNull();
        assertThat(row.get("HTTP_STATUS")).isNull();
    }

    @Test void ownershipAndVersionFenceApplyToInsertAndValidation() {
        var wrong = new SystemModelExecutionRef("snapshot", 10, "task", 8);
        diagnostics.provider("wrong", request(wrong), "deepseek-flash", 1, 200, "{}", null, null, "PASSED", 1);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM translation_call_diagnostic", Integer.class)).isZero();
        diagnostics.provider("call", request(ref), "deepseek-flash", 1, 200, "{}", null, null, "PASSED", 1);
        var result = new LlmResult("mock", "model", "{}", "stop", null, null, Map.of(TranslationCallDiagnostics.RESULT_ID, "call"));
        diagnostics.validation(wrong, result, "MISSING_TEXT example");
        assertThat(jdbc.queryForObject("SELECT validation_reason FROM translation_call_diagnostic", String.class)).isNull();
        diagnostics.validation(ref, result, "MISSING_TEXT example");
        assertThat(jdbc.queryForObject("SELECT validation_category FROM translation_call_diagnostic", String.class)).isEqualTo("FIELD");
    }

    @ParameterizedTest @CsvSource({"JSON_PARSE_ERROR bad,PARSE", "INCOMPLETE_JSON bad,PARSE", "MISSING_TEXT bad,FIELD",
        "EXTRA_SEGMENT bad,SEGMENT_COUNT", "OUTPUT_TRUNCATED,LENGTH", "TARGET_LANGUAGE_MISMATCH,LANGUAGE", "UNTRANSLATED_TEXT,LANGUAGE", "PASSED,PASSED", "untrusted text,UNKNOWN"})
    void validationUsesFixedCategories(String reason, String category) {
        assertThat(TranslationCallDiagnostics.category(reason)).isEqualTo(category);
    }

    @Test void escapedCredentialAndJsonQuotedSecretAreMasked() {
        String key = "synthetic-quoted-\"credential";
        String raw = "{\"echo\":\"synthetic-quoted-\\\"credential\",\"Authorization\":\"Bearer hidden\",\"apiKey\":\"hidden2\"}";
        assertThat(TranslationCallDiagnostics.redact(raw, key)).doesNotContain("credential", "hidden", "hidden2");
    }

    @Test void storageFailureDoesNotEscapeOrLogResponseOrCredentials() {
        var logger = (ch.qos.logback.classic.Logger) org.slf4j.LoggerFactory.getLogger(TranslationCallDiagnostics.class);
        var appender = new ch.qos.logback.core.read.ListAppender<ch.qos.logback.classic.spi.ILoggingEvent>();
        appender.start();
        logger.addAppender(appender);
        try {
            jdbc.execute("DROP TABLE translation_call_diagnostic");
            diagnostics.provider("call", request(ref), "deepseek-flash", 1, 200,
                "private-response synthetic-active-credential", "synthetic-active-credential", null, "CONTENT_EMPTY", 1);
            assertThat(appender.list).hasSize(1);
            assertThat(appender.list.getFirst().getFormattedMessage()).isEqualTo("event=translation_diagnostic_write_failed");
            assertThat(appender.list.getFirst().getThrowableProxy()).isNull();
        } finally { logger.detachAppender(appender); }
    }

    @Test void finalValidationPreservesBatchReasonAndTaskDeletionCascades() {
        diagnostics.provider("call", request(ref), "deepseek-flash", 1, 200, "{}", null, null, "PASSED", 1);
        var result = new LlmResult("mock", "model", "{}", "stop", null, null, Map.of(TranslationCallDiagnostics.RESULT_ID, "call"));
        diagnostics.validation(ref, result, "PASSED");
        diagnostics.finalValidation(ref, "TARGET_LANGUAGE_MISMATCH");
        assertThat(jdbc.queryForObject("SELECT validation_reason FROM translation_call_diagnostic", String.class)).isEqualTo("PASSED");
        assertThat(jdbc.queryForObject("SELECT final_validation_reason FROM translation_call_diagnostic", String.class)).isEqualTo("TARGET_LANGUAGE_MISMATCH");
        jdbc.update("DELETE FROM system_model_execution_snapshot WHERE id='snapshot'");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM translation_call_diagnostic", Integer.class)).isZero();
    }

    private static LlmRequest request(SystemModelExecutionRef ref) {
        return new LlmRequest("req", "task", List.of(new LlmMessage(LlmRole.USER,"JSON")), Duration.ofSeconds(1),
            0d, 3072, 3, Map.of("sourceSegmentCount", 1, "translationDiagnostic.inputChars", 100,
                "translationDiagnostic.indexes", "0"), LlmResponseFormat.JSON_OBJECT, ref);
    }
}
