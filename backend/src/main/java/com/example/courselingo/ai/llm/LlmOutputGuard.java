package com.example.courselingo.ai.llm;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Set;

public final class LlmOutputGuard {
    private static final Set<String> FINISH_REASONS = Set.of(
        "stop", "length", "tool_calls", "content_filter", "insufficient_system_resource");
    private LlmOutputGuard() {}

    public static void rejectTruncated(JsonNode root, int status) {
        // Provider-declared truncation wins over empty content and even syntactically valid JSON.
        if (root != null && "length".equals(root.path("choices").path(0).path("finish_reason").asText()))
            throw failure(root, status, LlmOutputDiagnostics.Reason.TRUNCATED);
    }

    public static void rejectEmpty(JsonNode root, int status) {
        if (root == null) return;
        var content = root.path("choices").path(0).path("message").path("content");
        if (content.isNull() || content.isTextual() && content.asText().isBlank())
            throw failure(root, status, LlmOutputDiagnostics.Reason.EMPTY_OUTPUT);
    }

    private static LlmOutputException failure(JsonNode root, int status, LlmOutputDiagnostics.Reason reason) {
        var usage = root.path("usage");
        var finish = root.path("choices").path(0).path("finish_reason").asText("");
        return new LlmOutputException(new LlmOutputDiagnostics(reason, status,
            new LlmUsage(integer(usage, "prompt_tokens"), integer(usage, "completion_tokens"), integer(usage, "total_tokens")),
            FINISH_REASONS.contains(finish) ? finish : null,
            integer(usage.path("completion_tokens_details"), "reasoning_tokens")));
    }

    private static Integer integer(JsonNode node, String key) {
        var value = node.path(key);
        return value.isIntegralNumber() && value.canConvertToInt() && value.intValue() >= 0 ? value.intValue() : null;
    }
}
