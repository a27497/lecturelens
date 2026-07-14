package com.example.courselingo.ai.llm;

import java.net.URI;
import java.time.Duration;
import java.util.Map;

public record OpenAiCompatibleChatCompletionRequest(
    URI uri,
    Map<String, String> headers,
    String method,
    String contentType,
    String body,
    Duration timeout
) {

    public OpenAiCompatibleChatCompletionRequest {
        headers = headers == null ? Map.of() : Map.copyOf(headers);
        method = method == null ? "POST" : method;
        contentType = contentType == null ? "application/json" : contentType;
        body = body == null ? "" : body;
        timeout = timeout == null ? Duration.ofSeconds(60) : timeout;
    }
}
