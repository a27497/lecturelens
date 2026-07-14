package com.example.courselingo.ai.asr;

import java.time.Duration;
import java.util.List;
import java.util.Map;

public record SiliconFlowAsrClientResponse(
    int statusCode,
    String body,
    Map<String, List<String>> headers,
    Duration duration
) {

    public SiliconFlowAsrClientResponse {
        body = body == null ? "" : body;
        headers = headers == null ? Map.of() : Map.copyOf(headers);
        duration = duration == null ? Duration.ZERO : duration;
    }
}
