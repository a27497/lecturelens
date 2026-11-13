package com.example.courselingo.subtitle.diagnostic;

import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResult;
import com.example.courselingo.systemmodel.SystemModelExecutionRef;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.Set;
import java.util.regex.Pattern;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

/** Private observations, deliberately separate from public task logs and error messages. */
@Service
public class TranslationCallDiagnostics {
    public static final String RESULT_ID = "translationDiagnostic.id";
    private static final int LIMIT = 4000;
    private static final Pattern CREDENTIAL_FIELD = Pattern.compile(
        "(?i)([\\\"']?(?:authorization|api[_-]?key|apikey|access[_-]?token|secret|password)[\\\"']?\\s*[:=]\\s*)(\\\"(?:\\\\.|[^\\\"])*\\\"|'[^']*'|[^\\s,;}]+)");
    private static final Pattern BEARER = Pattern.compile("(?i)bearer\\s+[^\\s\\\"'\\\\,;]+");
    private static final Pattern KEY = Pattern.compile("(?i)\\bsk-[a-z0-9_-]+");
    private static final Set<String> SCHEMA = Set.of("UNEXPECTED_SCHEMA", "INVALID_INDEX", "UNKNOWN_INDEX",
        "MISSING_TEXT", "BLANK_TEXT", "NON_STRING_TEXT", "SENSITIVE_TEXT");
    private static final Set<String> COUNTS = Set.of("MISSING_SEGMENT", "EXTRA_SEGMENT", "DUPLICATE_INDEX", "INCONSISTENT_INDEX");
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transaction;

    public TranslationCallDiagnostics(JdbcTemplate jdbc, PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        transaction = new TransactionTemplate(manager);
        transaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public void provider(String id, LlmRequest request, String model, int attempt, Integer status,
                         String body, String credential, JsonNode root, String reason, long millis) {
        if (id == null || request.execution() == null) return;
        var ref = request.execution();
        // Redact before truncation, including the active credential even if returned without a label.
        String excerpt = redact(body, credential);
        boolean truncated = excerpt != null && excerpt.length() > LIMIT;
        if (truncated) excerpt = excerpt.substring(0, LIMIT);
        final String safeExcerpt = excerpt;
        final boolean wasTruncated = truncated;
        safeWrite(() -> jdbc.update("""
            INSERT INTO translation_call_diagnostic
            (id,snapshot_id,task_id,user_id,config_version,feature,model,provider_attempt,
             segment_count,input_chars,batch_indexes,http_status,finish_reason,provider_reason,
             prompt_tokens,completion_tokens,total_tokens,duration_millis,response_chars,response_truncated,response_excerpt,attempt_id)
            SELECT ?,s.id,s.task_id,s.user_id,s.config_version,'TRANSLATION_FULL_TEXT',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            FROM system_model_execution_snapshot s WHERE s.id=? AND s.task_id=? AND s.user_id=? AND s.config_version=?
            """, id, model, attempt, request.metadata().get("sourceSegmentCount"),
            request.metadata().get("translationDiagnostic.inputChars"), request.metadata().get("translationDiagnostic.indexes"),
            status, finish(root), reason, token(root, "prompt_tokens"), token(root, "completion_tokens"),
            token(root, "total_tokens"), millis, body == null ? null : body.length(), wasTruncated, safeExcerpt,request.metadata().get("translationAttemptId"),
            ref.snapshotId(), ref.taskId(), ref.userId(), ref.configVersion()));
    }

    public void validation(SystemModelExecutionRef ref, LlmResult result, String reason) {
        if (ref == null || result == null || !(result.metadata().get(RESULT_ID) instanceof String id)) return;
        String category = category(reason);
        String safeReason = "PASSED".equals(category) ? "PASSED" : knownReason(reason);
        safeWrite(() -> jdbc.update("""
            UPDATE translation_call_diagnostic SET validation_category=?,validation_reason=?
            WHERE id=? AND snapshot_id=? AND task_id=? AND user_id=? AND config_version=?
            """, category, safeReason, id, ref.snapshotId(), ref.taskId(), ref.userId(), ref.configVersion()));
    }

    public void finalValidation(SystemModelExecutionRef ref, String reason) {
        if (ref == null) return;
        String safeReason = Set.of("PASSED", "COVERAGE_MISMATCH", "EMPTY_RESPONSE", "UNTRANSLATED_TEXT",
            "TARGET_LANGUAGE_MISMATCH").contains(reason) ? reason : "UNKNOWN";
        safeWrite(() -> jdbc.update("""
            UPDATE translation_call_diagnostic SET final_validation_reason=?
            WHERE snapshot_id=? AND task_id=? AND user_id=? AND config_version=?
            """, safeReason, ref.snapshotId(), ref.taskId(), ref.userId(), ref.configVersion()));
    }

    public static String category(String reason) {
        if ("PASSED".equals(reason)) return "PASSED";
        String known = knownReason(reason);
        if (SCHEMA.contains(known)) return "FIELD";
        if (COUNTS.contains(known)) return "SEGMENT_COUNT";
        if (Set.of("TARGET_LANGUAGE_MISMATCH", "UNTRANSLATED_TEXT").contains(known)) return "LANGUAGE";
        if ("OUTPUT_TRUNCATED".equals(known)) return "LENGTH";
        if (Set.of("EMPTY_RESPONSE", "INCOMPLETE_JSON", "JSON_PARSE_ERROR").contains(known)) return "PARSE";
        return "UNKNOWN";
    }

    private static String knownReason(String message) {
        if (message == null) return "UNKNOWN";
        String first = message.split(" ", 2)[0];
        return SCHEMA.contains(first) || COUNTS.contains(first)
            || Set.of("TARGET_LANGUAGE_MISMATCH", "UNTRANSLATED_TEXT", "OUTPUT_TRUNCATED",
                      "EMPTY_RESPONSE", "INCOMPLETE_JSON", "JSON_PARSE_ERROR").contains(first) ? first : "UNKNOWN";
    }

    static String redact(String body, String credential) {
        if (body == null) return null;
        String value = body;
        if (credential != null && !credential.isBlank()) {
            value = value.replace(credential, "[redacted]");
            try {
                String encoded = new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(credential);
                value = value.replace(encoded.substring(1, encoded.length() - 1), "[redacted]");
            } catch (Exception ignored) { return "[redacted: encoding unavailable]"; }
        }
        value = CREDENTIAL_FIELD.matcher(value).replaceAll("$1\"[redacted]\"");
        value = BEARER.matcher(value).replaceAll("Bearer [redacted]");
        return KEY.matcher(value).replaceAll("[redacted]");
    }

    private static Integer token(JsonNode root, String name) {
        JsonNode value = root == null ? null : root.path("usage").path(name);
        return value != null && value.isIntegralNumber() && value.canConvertToInt() && value.intValue() >= 0 ? value.intValue() : null;
    }

    private static String finish(JsonNode root) {
        if (root == null) return null;
        String value = root.path("choices").path(0).path("finish_reason").asText("");
        return Set.of("stop", "length", "tool_calls", "content_filter", "insufficient_system_resource").contains(value) ? value : null;
    }

    private void safeWrite(Runnable write) {
        try { transaction.executeWithoutResult(ignored -> write.run()); }
        catch (RuntimeException ignored) {
            // An observation failure cannot change translation outcome, retries or leak SQL parameters.
            LoggerFactory.getLogger(getClass()).warn("event=translation_diagnostic_write_failed");
        }
    }
}
