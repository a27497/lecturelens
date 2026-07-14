package com.example.courselingo.ai.llm;

import java.time.Duration;
import java.util.List;
import java.util.Map;

public record LlmRequest(
    String requestId,
    String taskId,
    List<LlmMessage> messages,
    Duration timeout,
    Double temperature,
    Integer maxTokens,
    Integer maxAttempts,
    Map<String, Object> metadata,
    LlmResponseFormat responseFormat
) {

    public LlmRequest {
        messages = messages == null ? List.of() : List.copyOf(messages);
        metadata = metadata == null ? Map.of() : Map.copyOf(metadata);
        responseFormat = responseFormat == null ? LlmResponseFormat.JSON_OBJECT : responseFormat;
    }

    public LlmRequest(
        String requestId,
        String taskId,
        List<LlmMessage> messages,
        Duration timeout,
        Double temperature,
        Integer maxTokens,
        Map<String, Object> metadata
    ) {
        this(requestId, taskId, messages, timeout, temperature, maxTokens, null, metadata, LlmResponseFormat.JSON_OBJECT);
    }

    public LlmRequest(
        String requestId,
        String taskId,
        List<LlmMessage> messages,
        Duration timeout,
        Double temperature,
        Integer maxTokens,
        Map<String, Object> metadata,
        LlmResponseFormat responseFormat
    ) {
        this(requestId, taskId, messages, timeout, temperature, maxTokens, null, metadata, responseFormat);
    }
}
