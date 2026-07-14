package com.example.courselingo.common.logging;

import java.util.regex.Pattern;

public final class SafeLogSanitizer {

    public static final int DEFAULT_LIMIT = 512;
    private static final String REDACTED = "[redacted]";
    private static final Pattern AUTHORIZATION = Pattern.compile(
        "(?i)authorization\\s*[:=]\\s*bearer\\s+[^\\s,;]+"
    );
    private static final Pattern COOKIE = Pattern.compile("(?i)(set-cookie|cookie)\\s*[:=]\\s*[^\\r\\n;]+");
    private static final Pattern SENSITIVE_KEY_VALUE = Pattern.compile(
        "(?i)(api[_\\s-]?key|apiKey|access[_\\s-]?token|refresh[_\\s-]?token|refreshToken|secret[_\\s-]?key|secretKey|token|secret|password)"
            + "\\s*[:=]\\s*[^\\s,;&]+"
    );
    private static final Pattern SENSITIVE_WORD = Pattern.compile(
        "(?i)\\b(authorization|cookie|set-cookie|api[_\\s-]?key|apiKey|access[_\\s-]?token|refresh[_\\s-]?token|refreshToken|secret[_\\s-]?key|secretKey|token|secret|password)\\b"
    );
    private static final Pattern OBJECT_KEY = Pattern.compile(
        "(?i)object[_-]?key\\s*[:=]\\s*[^\\s,;&]+"
    );
    private static final Pattern RAW_AI_FIELD = Pattern.compile(
        "(?is)raw[_\\s-]?(prompt|response)\\s*[:=]\\s*[^\\r\\n]*"
    );
    private static final Pattern WINDOWS_PATH = Pattern.compile("[A-Za-z]:\\\\[^\\s,;]+");
    private static final Pattern UNIX_PATH = Pattern.compile("/(?:home|tmp|var/tmp|Users)/[^\\s,;]+");

    private SafeLogSanitizer() {
    }

    public static String sanitize(String value) {
        if (value == null) {
            return null;
        }
        String sanitized = AUTHORIZATION.matcher(value).replaceAll("Authorization=" + REDACTED);
        sanitized = COOKIE.matcher(sanitized).replaceAll("$1=" + REDACTED);
        sanitized = SENSITIVE_KEY_VALUE.matcher(sanitized).replaceAll("$1=" + REDACTED);
        sanitized = OBJECT_KEY.matcher(sanitized).replaceAll(REDACTED);
        sanitized = RAW_AI_FIELD.matcher(sanitized).replaceAll(REDACTED);
        sanitized = WINDOWS_PATH.matcher(sanitized).replaceAll("[local-path]");
        sanitized = UNIX_PATH.matcher(sanitized).replaceAll("[local-path]");
        sanitized = SENSITIVE_WORD.matcher(sanitized).replaceAll(REDACTED);
        return sanitized;
    }

    public static String sanitizeAndLimit(String value) {
        return sanitizeAndLimit(value, DEFAULT_LIMIT);
    }

    public static String sanitizeAndLimit(String value, int limit) {
        String sanitized = sanitize(value);
        if (sanitized == null || sanitized.length() <= limit) {
            return sanitized;
        }
        return sanitized.substring(0, limit);
    }
}
