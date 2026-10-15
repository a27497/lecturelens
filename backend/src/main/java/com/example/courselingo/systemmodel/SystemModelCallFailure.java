package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.llm.LlmProviderException;
import com.example.courselingo.ai.llm.LlmProviderFailureCategory;
import com.example.courselingo.ai.llm.LlmProviderFailureDetails;

public final class SystemModelCallFailure extends LlmProviderException {
    private final LlmProviderFailureDetails details;
    private final String category;

    public SystemModelCallFailure(
            String category,
            LlmProviderFailureCategory failure,
            Integer status,
            boolean retryable) {
        super("System model request failed: " + category);
        this.category = category;
        this.details = new LlmProviderFailureDetails(failure, status, null, retryable);
    }

    public LlmProviderFailureDetails details() {
        return details;
    }

    public String category() {
        return category;
    }
}
