package com.example.courselingo.ai.llm;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

public final class LlmStructuredOutputExecutor {

    private LlmStructuredOutputExecutor() {
    }

    public static LlmResult execute(LlmProvider provider, LlmRequest request) {
        long startedNanos = LlmCallTiming.startedNanos();
        LlmResult result = provider.generate(request);
        if (result == null) {
            throw new LlmProviderException("LLM provider returned no result");
        }
        Duration duration = LlmCallTiming.measuredDuration(startedNanos, result.duration());
        Map<String, Object> metadata = new LinkedHashMap<>(result.metadata());
        metadata.putIfAbsent("responseFormatUsed", request.responseFormat().name());
        return new LlmResult(
            result.provider(), result.model(), result.content(), result.finishReason(), result.usage(), duration, metadata
        );
    }
}
