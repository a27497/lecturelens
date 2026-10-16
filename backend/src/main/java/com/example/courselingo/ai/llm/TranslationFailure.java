package com.example.courselingo.ai.llm;

import com.example.courselingo.ai.llm.*;

/** Only bounded enums and usage cross the failure boundary; no response, header or cause. */
public final class TranslationFailure extends LlmProviderException {
    public enum Reason {
        TRUNCATED, EMPTY_OUTPUT, FORMAT_INVALID, VALIDATION_INVALID, TIMEOUT, RATE_LIMITED,
        UPSTREAM_5XX, AUTHENTICATION, MODEL_NOT_FOUND, INVALID_REQUEST, NETWORK, UNKNOWN,
        OUTPUT_BUDGET_TOO_SMALL, SPLIT_DEPTH_EXHAUSTED, CALL_BUDGET_EXHAUSTED,
        TOKEN_BUDGET_EXHAUSTED, DEADLINE_EXCEEDED, CANCELED, ACCOUNTING_INCOMPLETE,
        SOURCE_CHANGED, SNAPSHOT_INVALID
    }
    public enum Check {
        OUTPUT_TRUNCATED, CONTENT_EMPTY, CONTENT_NULL, CONTENT_MISSING, CONTENT_NON_STRING,
        ENVELOPE_JSON_INVALID, CONTENT_JSON_INVALID, FINISH_REASON, FIELD, SEGMENT_COUNT, LANGUAGE
    }
    private final Reason reason;
    private final Integer status;
    private final LlmUsage usage;
    private final String finishReason;
    private final long retryAfterMillis;
    private final Check check;

    public TranslationFailure(Reason reason, Integer status, LlmUsage usage, String finishReason, long retryAfterMillis) {
        this(reason,status,usage,finishReason,retryAfterMillis,null);
    }
    public TranslationFailure(Reason reason, Integer status, LlmUsage usage, String finishReason, long retryAfterMillis, Check check) {
        super("Translation failed: " + reason.name());
        this.reason = reason; this.status = status;
        this.usage = usage == null ? new LlmUsage(null, null, null) : usage;
        this.finishReason = switch (finishReason == null ? "" : finishReason) {
            case "stop", "length", "content_filter", "tool_calls", "aborted", "insufficient_system_resource" -> finishReason;
            default -> null;
        };
        this.retryAfterMillis = Math.max(0, retryAfterMillis);
        this.check = check;
    }
    public static TranslationFailure of(Reason reason) { return new TranslationFailure(reason, null, null, null, 0); }
    public Reason reason() { return reason; }
    public Integer status() { return status; }
    public LlmUsage usage() { return usage; }
    public String finishReason() { return finishReason; }
    public long retryAfterMillis() { return retryAfterMillis; }
    public Check check() { return check; }
    public String observationReason() { return check == null ? reason.name() : check.name(); }
    public boolean transportRetryable() { return switch (reason) {
        case TIMEOUT, RATE_LIMITED, UPSTREAM_5XX, NETWORK -> true;
        default -> false;
    }; }
    public LlmProviderFailureDetails details() {
        var category = switch (reason) {
            case AUTHENTICATION -> LlmProviderFailureCategory.AUTHENTICATION;
            case MODEL_NOT_FOUND -> LlmProviderFailureCategory.MODEL_NOT_FOUND;
            case RATE_LIMITED -> LlmProviderFailureCategory.RATE_LIMIT;
            case TIMEOUT, DEADLINE_EXCEEDED -> LlmProviderFailureCategory.TIMEOUT;
            case UPSTREAM_5XX -> LlmProviderFailureCategory.SERVER_ERROR;
            case NETWORK -> LlmProviderFailureCategory.NETWORK;
            case TRUNCATED, EMPTY_OUTPUT, FORMAT_INVALID, VALIDATION_INVALID -> LlmProviderFailureCategory.OUTPUT_INVALID;
            case UNKNOWN -> LlmProviderFailureCategory.UNKNOWN;
            default -> LlmProviderFailureCategory.INVALID_REQUEST;
        };
        return new LlmProviderFailureDetails(category, status, null, transportRetryable());
    }
    public static TranslationFailure from(Throwable failure) {
        if (failure instanceof TranslationFailure typed) return typed;
        var details = LlmProviderFailureClassifier.from(failure);
        var reason = switch (details.category()) {
            case AUTHENTICATION -> Reason.AUTHENTICATION;
            case MODEL_NOT_FOUND -> Reason.MODEL_NOT_FOUND;
            case RATE_LIMIT -> Reason.RATE_LIMITED;
            case TIMEOUT -> Reason.TIMEOUT;
            case SERVER_ERROR -> Reason.UPSTREAM_5XX;
            case NETWORK -> Reason.NETWORK;
            case OUTPUT_INVALID -> Reason.FORMAT_INVALID;
            case INVALID_REQUEST, CONTEXT_TOO_LARGE, UNSUPPORTED_RESPONSE_FORMAT -> Reason.INVALID_REQUEST;
            default -> Reason.UNKNOWN;
        };
        return new TranslationFailure(reason, details.httpStatus(), null, null, 0);
    }
}
