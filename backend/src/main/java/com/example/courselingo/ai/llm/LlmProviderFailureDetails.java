package com.example.courselingo.ai.llm;

public record LlmProviderFailureDetails(
    LlmProviderFailureCategory category,
    Integer httpStatus,
    String providerErrorCode,
    boolean retryable
) {

    public LlmProviderFailureDetails {
        category = category == null ? LlmProviderFailureCategory.UNKNOWN : category;
        providerErrorCode = safeCode(providerErrorCode);
    }

    public String safeSummary() {
        return "category=" + category
            + ";httpStatus=" + (httpStatus == null ? "" : httpStatus)
            + ";providerErrorCode=" + (providerErrorCode == null ? "" : providerErrorCode)
            + ";retryable=" + retryable;
    }

    private static String safeCode(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String normalized = value.strip().replaceAll("[^A-Za-z0-9_.-]", "");
        return normalized.isBlank() ? null : normalized.substring(0, Math.min(64, normalized.length()));
    }
}
