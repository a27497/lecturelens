package com.example.courselingo.ai.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.ConnectException;
import java.net.SocketException;
import java.net.http.HttpTimeoutException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Locale;
import java.util.Set;

public final class LlmProviderFailureClassifier {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    private LlmProviderFailureClassifier() {
    }

    public static LlmProviderFailureDetails classify(Integer status, String providerBody, Throwable failure) {
        String body = providerBody == null ? "" : providerBody.toLowerCase(Locale.ROOT);
        String failureText = failureText(failure);
        String errorCode = providerErrorCode(providerBody);
        if (status != null && (status == 401 || status == 403)
            || containsAny(failureText, "401 unauthorized", "403 forbidden", "authentication failed")) {
            return details(LlmProviderFailureCategory.AUTHENTICATION, status, errorCode, false);
        }
        if (status != null && status == 404 || containsAny(failureText, "404 model", "model not found")) {
            return details(LlmProviderFailureCategory.MODEL_NOT_FOUND, status, errorCode, false);
        }
        if (status != null && status == 429) {
            return details(LlmProviderFailureCategory.RATE_LIMIT, status, errorCode, true);
        }
        if ((status != null && status == 413)
            || containsAny(body, "context length", "context_length", "context too large", "too many tokens")) {
            return details(LlmProviderFailureCategory.CONTEXT_TOO_LARGE, status, errorCode, false);
        }
        if ((status != null && (status == 400 || status == 422)) && explicitlyRejectsStructuredOutput(body)) {
            return details(LlmProviderFailureCategory.UNSUPPORTED_RESPONSE_FORMAT, status, errorCode, false);
        }
        if ((status != null && status == 408) || isTimeout(failure)) {
            return details(LlmProviderFailureCategory.TIMEOUT, status, errorCode, true);
        }
        if (status != null && status >= 500) {
            return details(LlmProviderFailureCategory.SERVER_ERROR, status, errorCode, true);
        }
        if (status != null && status >= 400) {
            return details(LlmProviderFailureCategory.INVALID_REQUEST, status, errorCode, false);
        }
        if (isNetwork(failure)) {
            return details(LlmProviderFailureCategory.NETWORK, status, errorCode, true);
        }
        return details(LlmProviderFailureCategory.UNKNOWN, status, errorCode, false);
    }

    public static LlmProviderFailureDetails from(Throwable failure) {
        Throwable current = failure;
        Set<Throwable> visited = Collections.newSetFromMap(new IdentityHashMap<>());
        while (current != null && visited.add(current)) {
            if (current instanceof OpenAiCompatibleLlmException openAiFailure) {
                return openAiFailure.failureDetails();
            }
            if (current instanceof LangChain4jLlmException langChainFailure) {
                LlmProviderFailureCategory category = langChainFailure.retryable()
                    ? (isTimeout(langChainFailure) ? LlmProviderFailureCategory.TIMEOUT : LlmProviderFailureCategory.NETWORK)
                    : LlmProviderFailureCategory.UNKNOWN;
                return new LlmProviderFailureDetails(category, null, null, langChainFailure.retryable());
            }
            current = current.getCause();
        }
        return classify(null, null, failure);
    }

    public static boolean explicitlyRejectsStructuredOutput(String body) {
        if (body == null || body.isBlank()) {
            return false;
        }
        String normalized = body.toLowerCase(Locale.ROOT);
        boolean mentionsFormat = containsAny(normalized, "response_format", "response format", "json_object", "json object", "structured output");
        boolean rejects = containsAny(normalized, "unsupported", "not support", "does not support", "unknown", "unrecognized", "not allowed", "invalid parameter");
        return mentionsFormat && rejects;
    }

    private static LlmProviderFailureDetails details(
        LlmProviderFailureCategory category,
        Integer status,
        String code,
        boolean retryable
    ) {
        return new LlmProviderFailureDetails(category, status, code, retryable);
    }

    private static String providerErrorCode(String body) {
        if (body == null || body.isBlank()) {
            return null;
        }
        try {
            JsonNode root = OBJECT_MAPPER.readTree(body);
            JsonNode error = root.path("error");
            for (JsonNode candidate : new JsonNode[]{root.path("code"), error.path("code"), root.path("error_code")}) {
                if (!candidate.isMissingNode() && !candidate.isNull() && !candidate.asText().isBlank()) {
                    return candidate.asText();
                }
            }
        } catch (Exception ignored) {
            // Provider bodies are deliberately not retained when they are not valid JSON.
        }
        return null;
    }

    private static boolean containsAny(String value, String... needles) {
        for (String needle : needles) {
            if (value.contains(needle)) {
                return true;
            }
        }
        return false;
    }

    private static boolean isTimeout(Throwable throwable) {
        Throwable current = throwable;
        Set<Throwable> visited = Collections.newSetFromMap(new IdentityHashMap<>());
        while (current != null && visited.add(current)) {
            String name = current.getClass().getSimpleName().toLowerCase(Locale.ROOT);
            String message = current.getMessage() == null ? "" : current.getMessage().toLowerCase(Locale.ROOT);
            if (current instanceof HttpTimeoutException || name.contains("timeout")
                || message.contains("timed out") || message.contains("timeout")) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private static boolean isNetwork(Throwable throwable) {
        Throwable current = throwable;
        Set<Throwable> visited = Collections.newSetFromMap(new IdentityHashMap<>());
        while (current != null && visited.add(current)) {
            if (current instanceof ConnectException || current instanceof SocketException) {
                return true;
            }
            String name = current.getClass().getSimpleName().toLowerCase(Locale.ROOT);
            String message = current.getMessage() == null ? "" : current.getMessage().toLowerCase(Locale.ROOT);
            if (name.contains("connect") || name.contains("socket")
                || containsAny(message, "connection refused", "connection reset", "network is unreachable", "dns")) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private static String failureText(Throwable throwable) {
        StringBuilder text = new StringBuilder();
        Throwable current = throwable;
        Set<Throwable> visited = Collections.newSetFromMap(new IdentityHashMap<>());
        while (current != null && visited.add(current)) {
            if (current.getMessage() != null) {
                text.append(' ').append(current.getMessage().toLowerCase(Locale.ROOT));
            }
            current = current.getCause();
        }
        return text.toString();
    }
}
