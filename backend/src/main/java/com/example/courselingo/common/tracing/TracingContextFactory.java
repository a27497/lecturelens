package com.example.courselingo.common.tracing;

import java.util.UUID;
import java.util.regex.Pattern;

public final class TracingContextFactory {

    private static final Pattern SAFE_ID = Pattern.compile("[A-Za-z0-9._:-]{1,128}");
    private static final Pattern SENSITIVE_WORD = Pattern.compile(
        "(?i)\\b(authorization|cookie|set-cookie|api[_-]?key|apiKey|access[_-]?token|refresh[_-]?token|refreshToken|token|secret|password)\\b"
    );
    private static final Pattern WINDOWS_PATH = Pattern.compile("[A-Za-z]:\\\\\\S*");
    private static final Pattern UNIX_PATH = Pattern.compile("/(?:home|tmp|var/tmp|Users)/\\S*");

    private TracingContextFactory() {
    }

    public static TracingContext fromHeaders(String traceIdHeader, String requestIdHeader) {
        return new TracingContext(resolveId(traceIdHeader), resolveId(requestIdHeader));
    }

    public static TracingContext create() {
        return new TracingContext(newId(), newId());
    }

    public static String resolveId(String candidate) {
        if (candidate == null) {
            return newId();
        }
        String trimmed = candidate.trim();
        if (!SAFE_ID.matcher(trimmed).matches()
            || SENSITIVE_WORD.matcher(trimmed).find()
            || WINDOWS_PATH.matcher(trimmed).find()
            || UNIX_PATH.matcher(trimmed).find()) {
            return newId();
        }
        return trimmed;
    }

    private static String newId() {
        return UUID.randomUUID().toString();
    }
}
