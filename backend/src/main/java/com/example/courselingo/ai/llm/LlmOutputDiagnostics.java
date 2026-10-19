package com.example.courselingo.ai.llm;

/** Safe observations only; no content, headers, credentials or provider exception causes. */
public record LlmOutputDiagnostics(
    Reason reason, Integer httpStatus, LlmUsage usage, String finishReason, Integer reasoningTokens
) {
    public enum Reason { TRUNCATED, EMPTY_OUTPUT }
}
