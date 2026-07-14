package com.example.courselingo.ai.llm;

public record LlmUsage(
    Integer promptTokens,
    Integer completionTokens,
    Integer totalTokens
) {
}
