package com.example.courselingo.ai.llm;

public record LlmMessage(
    LlmRole role,
    String content
) {
}
