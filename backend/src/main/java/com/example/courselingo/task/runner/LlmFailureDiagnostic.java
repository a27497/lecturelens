package com.example.courselingo.task.runner;

import com.example.courselingo.ai.llm.OpenAiCompatibleLlmException;
import com.example.courselingo.ai.llm.LlmProviderFailureClassifier;
import com.example.courselingo.ai.llm.LlmProviderFailureDetails;
import com.example.courselingo.ai.llm.LlmStageException;
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
        String semanticOutputReason = semanticOutputReason(exception);
        if (semanticOutputReason != null) {
            return new LlmFailureDiagnostic(
                fallbackProvider,
                null,
                "OUTPUT_INVALID",
                "category=OUTPUT_INVALID;reason=" + semanticOutputReason + ";retryable=false",
                false
            );
        }
        LlmStageException stageException = findStageException(exception);
        if (stageException != null) {
            return new LlmFailureDiagnostic(
                fallbackProvider,
                null,
                stageException.details().category().name(),
                stageException.safeDiagnosticSummary(),
                stageException.details().retryable()
            );
        }
        OpenAiCompatibleLlmException providerException = findProviderException(exception);
        if (providerException != null) {
            LlmProviderFailureDetails details = providerException.failureDetails();
            return new LlmFailureDiagnostic(
                providerException.provider().orElse(fallbackProvider),
                providerException.model().orElse(null),
                details.category().name(),
                details.safeSummary(),
                details.retryable()
            );
        }
        LlmProviderFailureDetails details = LlmProviderFailureClassifier.from(exception);
        return new LlmFailureDiagnostic(
            fallbackProvider,
            null,
            errorCode(exception, details),
            details.safeSummary(),
            details.retryable()
        );
    }

    private static LlmStageException findStageException(Throwable throwable) {
        Throwable current = throwable;
        while (current != null) {
            if (current instanceof LlmStageException stageException) {
                return stageException;
            }
            current = current.getCause();
        }
        return null;
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

    private static String errorCode(Throwable throwable, LlmProviderFailureDetails details) {
        if (throwable instanceof BusinessException businessException) {
            return businessException.errorCode().code();
        }
        return details.category().name();
    }

    private static String semanticOutputReason(Throwable throwable) {
        Throwable current = throwable;
        while (current != null) {
            String message = current.getMessage();
            if (message != null) {
                if (message.contains("TARGET_LANGUAGE_MISMATCH")) {
                    return "TARGET_LANGUAGE_MISMATCH";
                }
                if (message.contains("UNTRANSLATED_TEXT")) {
                    return "UNTRANSLATED_TEXT";
                }
                if (message.contains("EMPTY_RESPONSE")) {
                    return "EMPTY_RESPONSE";
                }
            }
            current = current.getCause();
        }
        return null;
    }
}
