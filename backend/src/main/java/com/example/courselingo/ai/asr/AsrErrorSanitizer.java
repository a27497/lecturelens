package com.example.courselingo.ai.asr;

import java.util.regex.Pattern;

final class AsrErrorSanitizer {

    private static final Pattern WIRE_SECRET = Pattern.compile(
        "(?i)authorization[^\\r\\n]*|bearer\\s+[^\\s\"]+|data:audio/[^\\s\"]+|\\bsk-[a-zA-Z0-9_-]+"
    );
    private static final int MAX_MESSAGE_LENGTH = 512;
    private static final Pattern SENSITIVE_PAIR = Pattern.compile(
        "(?i)\\b(?:token|secret|api[_-]?key|api\\s+key)\\b(?:\\s*[:=]\\s*|\\s+)\\S+"
    );
    private static final Pattern SENSITIVE_WORD = Pattern.compile(
        "(?i)\\b(?:token|secret|api[_-]?key|api\\s+key)\\b"
    );
    private static final Pattern WINDOWS_PATH = Pattern.compile("[A-Za-z]:\\\\\\S+");
    private static final Pattern UNIX_PRIVATE_PATH = Pattern.compile("(?i)(?:/users|/home)/\\S+");

    private AsrErrorSanitizer() {
    }

    static String sanitize(String message) {
        if (message == null || message.isBlank()) {
            return "ASR provider failed";
        }
        String sanitized = SENSITIVE_PAIR.matcher(WIRE_SECRET.matcher(message).replaceAll("[redacted]")).replaceAll("[redacted]");
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
        return WIRE_SECRET.matcher(text).find()
            || SENSITIVE_PAIR.matcher(text).find()
            || SENSITIVE_WORD.matcher(text).find()
            || WINDOWS_PATH.matcher(text).find()
            || UNIX_PRIVATE_PATH.matcher(text).find();
    }
}
