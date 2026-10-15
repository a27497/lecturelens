package com.example.courselingo.ai.asr;

/** Closed error vocabulary: no upstream messages, payloads, headers or cause chains. */
public final class AsrCallFailure extends AsrProviderException {
    public enum Category {
        AUTHENTICATION,
        MODEL_NOT_FOUND,
        RATE_LIMIT,
        SERVER_ERROR,
        INVALID_REQUEST,
        OUTPUT_INVALID,
        TIMEOUT,
        NETWORK,
        REDIRECT_FORBIDDEN,
        RESPONSE_TOO_LARGE,
        CANCELLED
    }

    private final Category category;

    public AsrCallFailure(Category category, boolean retryable, Integer status) {
        super("ASR request failed: " + category.name(), retryable, status);
        this.category = category;
    }

    public Category category() {
        return category;
    }

    public static AsrCallFailure provider(AsrProviderException failure) {
        if (failure instanceof AsrCallFailure safe) return safe;
        Integer status = failure.statusCode().orElse(null);
        Category category =
                status == null
                        ? Category.OUTPUT_INVALID
                        : status == 401 || status == 403
                                ? Category.AUTHENTICATION
                                : status == 404
                                        ? Category.MODEL_NOT_FOUND
                                        : status == 429
                                                ? Category.RATE_LIMIT
                                                : status == 408
                                                        ? Category.TIMEOUT
                                                        : status >= 500
                                                                ? Category.SERVER_ERROR
                                                                : Category.INVALID_REQUEST;
        if (status == null) {
            // Only local adapter messages are classified; no message is propagated.
            String message = failure.getMessage() == null ? "" : failure.getMessage();
            if (message.contains("configuration") || message.contains("settings"))
                category = Category.INVALID_REQUEST;
            else if (message.contains("timed out")) category = Category.TIMEOUT;
            else if (failure.retryable()) category = Category.NETWORK;
        }
        return new AsrCallFailure(category, failure.retryable(), status);
    }
}
