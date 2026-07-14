package com.example.courselingo.ai.llm;

public interface LlmProvider {

    LlmResult generate(LlmRequest request);

    String providerName();

    default String modelNameForDiagnostics() {
        return "";
    }
}
