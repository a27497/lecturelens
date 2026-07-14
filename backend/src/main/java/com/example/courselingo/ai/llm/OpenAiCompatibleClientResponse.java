package com.example.courselingo.ai.llm;

import java.time.Duration;
import java.util.List;
import java.util.Map;

public record OpenAiCompatibleClientResponse(
    int statusCode,
    String body,
    Map<String, List<String>> headers,
    Duration duration
) {

    public OpenAiCompatibleClientResponse {
        body = body == null ? "" : body;
        headers = headers == null ? Map.of() : Map.copyOf(headers);
        duration = duration == null ? Duration.ZERO : duration;
    }
}
