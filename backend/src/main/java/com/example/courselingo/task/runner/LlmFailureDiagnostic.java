package com.example.courselingo.task.runner;

import com.example.courselingo.ai.llm.OpenAiCompatibleLlmException;
import com.example.courselingo.common.exception.BusinessException;

record LlmFailureDiagnostic(
    String provider,
    String model,
    String errorCode,
    String errorMessage,
    boolean retryable
) {

    static LlmFailureDiagnostic from(
        RuntimeException exception,
        PipelineAnalysisTaskStepContext context,
        String fallbackProvider
    ) {
        OpenAiCompatibleLlmException providerException = findProviderException(exception);
        if (providerException != null) {
            return new LlmFailureDiagnostic(
                providerException.provider().orElse(fallbackProvider),
                providerException.model().orElse(null),
                providerException.failureType().name(),
                withUploadId(context, providerException.getMessage()),
                providerException.retryable()
            );
        }
        String message = exception == null ? "" : exception.getMessage();
        return new LlmFailureDiagnostic(
            fallbackProvider,
            null,
            errorCode(exception, message),
            withUploadId(context, message),
            retryable(message)
        );
    }

    private static OpenAiCompatibleLlmException findProviderException(Throwable throwable) {
        Throwable current = throwable;
        while (current != null) {
            if (current instanceof OpenAiCompatibleLlmException providerException) {
                return providerException;
            }
            current = current.getCause();
        }
        return null;
    }

    private static String errorCode(Throwable throwable, String message) {
        if (message != null) {
            for (String prefix : new String[] {
                "HTTP_ERROR",
                "TIMEOUT",
                "CONNECTION_ERROR",
                "EMPTY_RESPONSE",
                "MALFORMED_RESPONSE",
                "JSON_PARSE_ERROR",
                "UNEXPECTED_SCHEMA",
                "PROVIDER_RATE_LIMIT",
                "PROVIDER_AUTH_FAILED"
            }) {
                if (message.contains(prefix)) {
                    return prefix;
                }
            }
        }
        if (throwable instanceof BusinessException businessException) {
            return businessException.errorCode().code();
        }
        return "AI_PROVIDER_FAILED";
    }

    private static boolean retryable(String message) {
        if (message == null) {
            return true;
        }
        return !(message.contains("JSON_PARSE_ERROR")
            || message.contains("UNEXPECTED_SCHEMA")
            || message.contains("MALFORMED_RESPONSE")
            || message.contains("EMPTY_RESPONSE")
            || message.contains("PROVIDER_AUTH_FAILED"));
    }

    private static String withUploadId(PipelineAnalysisTaskStepContext context, String message) {
        String uploadId = context == null ? "" : context.uploadId();
        String safeMessage = message == null ? "" : message;
        return "uploadId=" + uploadId + " " + safeMessage;
    }
}
