package com.example.courselingo.ai.llm;

/** Safe output metadata only: never retain provider content, headers, or exception causes. */
public record LlmOutputDiagnostics(
    TranslationFailure.Reason reason, Integer httpStatus, LlmUsage usage, String finishReason
) {
    public static LlmOutputDiagnostics from(TranslationFailure failure) {
        return new LlmOutputDiagnostics(failure.reason(), failure.status(), failure.usage(), failure.finishReason());
    }
}
