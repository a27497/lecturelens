package com.example.courselingo.ai.llm;

/** Protocol failure independent of newer translation pipelines and recovery state. */
public final class LlmOutputException extends LlmProviderException {
    private final LlmOutputDiagnostics diagnostics;

    public LlmOutputException(LlmOutputDiagnostics diagnostics) {
        // The frozen aligned-translation recovery recognizes this bounded truncation marker.
        super(diagnostics.reason() == LlmOutputDiagnostics.Reason.TRUNCATED
            ? "LLM output truncated; finish_reason=length" : "LLM output empty");
        this.diagnostics = diagnostics;
    }

    public LlmOutputDiagnostics diagnostics() { return diagnostics; }

    public LlmProviderFailureDetails details() {
        return new LlmProviderFailureDetails(LlmProviderFailureCategory.OUTPUT_INVALID,
            diagnostics.httpStatus(), diagnostics.reason() == LlmOutputDiagnostics.Reason.TRUNCATED
                ? "OUTPUT_TRUNCATED" : "EMPTY_OUTPUT", false);
    }
}
