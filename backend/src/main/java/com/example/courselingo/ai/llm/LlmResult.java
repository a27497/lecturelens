package com.example.courselingo.ai.llm;

import java.time.Duration;
import java.util.Map;

public record LlmResult(
    String provider,
    String model,
    String content,
    String finishReason,
    LlmUsage usage,
    Duration duration,
    Map<String, Object> metadata
) {

    public LlmResult {
        content = content == null ? "" : content;
        finishReason = finishReason == null ? "" : finishReason;
        usage = usage == null ? new LlmUsage(null, null, null) : usage;
        duration = duration == null ? Duration.ZERO : duration;
        metadata = metadata == null ? Map.of() : Map.copyOf(metadata);
    }
}
