package com.example.courselingo.ai.llm;

import java.util.regex.Pattern;

final class LlmErrorSanitizer {

    private static final int MAX_MESSAGE_LENGTH = 512;
    private static final Pattern AUTH_HEADER = Pattern.compile("(?i)\\bauthorization\\b\\s*[:=]?\\s*bearer\\s+\\S+");
    private static final Pattern SENSITIVE_PAIR = Pattern.compile(
        "(?i)\\b(?:token|secret|api[_-]?key|api\\s+key|authorization)\\b(?:\\s*[:=]\\s*|\\s+)\\S+"
    );
    private static final Pattern SENSITIVE_WORD = Pattern.compile(
        "(?i)\\b(?:token|secret|api[_-]?key|api\\s+key|authorization)\\b"
    );
    private static final Pattern WINDOWS_PATH = Pattern.compile("[A-Za-z]:\\\\\\S+");
    private static final Pattern UNIX_PRIVATE_PATH = Pattern.compile("(?i)(?:/users|/home)/\\S+");

    private LlmErrorSanitizer() {
    }

    static String sanitize(String message) {
        if (message == null || message.isBlank()) {
            return "LLM provider failed";
        }
        String sanitized = AUTH_HEADER.matcher(message).replaceAll("[redacted]");
        sanitized = SENSITIVE_PAIR.matcher(sanitized).replaceAll("[redacted]");
        sanitized = SENSITIVE_WORD.matcher(sanitized).replaceAll("[redacted]");
        sanitized = WINDOWS_PATH.matcher(sanitized).replaceAll("[path]");
        sanitized = UNIX_PRIVATE_PATH.matcher(sanitized).replaceAll("[path]");
        if (sanitized.length() > MAX_MESSAGE_LENGTH) {
            return sanitized.substring(0, MAX_MESSAGE_LENGTH) + "...";
        }
        return sanitized;
    }

    static boolean containsSensitiveData(String text) {
        if (text == null || text.isBlank()) {
            return false;
        }
        return AUTH_HEADER.matcher(text).find()
            || SENSITIVE_PAIR.matcher(text).find()
            || SENSITIVE_WORD.matcher(text).find()
            || WINDOWS_PATH.matcher(text).find()
            || UNIX_PRIVATE_PATH.matcher(text).find();
    }
}
