package com.example.courselingo.ai.record.service;

import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class AiCallRecordSanitizer {

    private static final int MAX_ERROR_MESSAGE_LENGTH = 512;
    private static final Pattern SENSITIVE_WORDS = Pattern.compile(
        "(?i)(authorization|bearer|token|secret|api\\s*key|api[_-]?key|object[_-]?key)"
    );
    private static final Pattern WINDOWS_PATH = Pattern.compile("(?i)[a-z]:\\\\[^\\s]+");
    private static final Pattern UNIX_PATH = Pattern.compile("(?i)(/home/|/users/)[^\\s]+");

    public String sanitizeErrorMessage(String message) {
        if (message == null || message.isBlank()) {
            return null;
        }
        String sanitized = SENSITIVE_WORDS.matcher(message).replaceAll("[redacted]");
        sanitized = WINDOWS_PATH.matcher(sanitized).replaceAll("[redacted]");
        sanitized = UNIX_PATH.matcher(sanitized).replaceAll("[redacted]");
        sanitized = sanitized.replaceAll("\\s+", " ").trim();
        if (sanitized.length() <= MAX_ERROR_MESSAGE_LENGTH) {
            return sanitized;
        }
        return sanitized.substring(0, MAX_ERROR_MESSAGE_LENGTH);
    }

    public boolean containsSensitiveData(String value) {
        if (value == null || value.isBlank()) {
            return false;
        }
        return SENSITIVE_WORDS.matcher(value).find()
            || WINDOWS_PATH.matcher(value).find()
            || UNIX_PATH.matcher(value).find();
    }
}
