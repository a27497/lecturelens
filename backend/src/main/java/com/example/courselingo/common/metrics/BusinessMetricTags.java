package com.example.courselingo.common.metrics;

import java.util.Locale;
import java.util.regex.Pattern;

final class BusinessMetricTags {

    static final String OUTCOME = "outcome";
    static final String FROM = "from";
    static final String TO = "to";
    static final String STAGE = "stage";
    static final String TOPIC = "topic";
    static final String TAG = "tag";
    static final String TYPE = "type";

    private static final int MAX_TAG_LENGTH = 64;
    private static final Pattern SAFE_VALUE = Pattern.compile("[a-z0-9_.:-]+");
    private static final Pattern IDENTIFIER_SHAPED_VALUE = Pattern.compile("(?i)(task|up|upload|user)[_-][a-z0-9_-]+");
    private static final Pattern SENSITIVE_VALUE = Pattern.compile(
        "(?i)(user\\s*id|userid|task\\s*id|taskid|upload\\s*id|uploadid|object\\s*key|objectkey|"
            + "file\\s*name|filename|path|token|secret|api\\s*key|apikey|authorization|cookie|password|"
            + "prompt|response|subtitle|learning\\s*package|learningpackage)"
    );

    private BusinessMetricTags() {
    }

    static String normalize(String value) {
        if (value == null || value.isBlank()) {
            return "unknown";
        }
        String normalized = value.trim().toLowerCase(Locale.ROOT);
        if (normalized.length() > MAX_TAG_LENGTH
            || normalized.contains("/")
            || normalized.contains("\\")
            || normalized.contains("..")
            || IDENTIFIER_SHAPED_VALUE.matcher(normalized).matches()
            || SENSITIVE_VALUE.matcher(normalized).find()
            || !SAFE_VALUE.matcher(normalized).matches()) {
            return "other";
        }
        return normalized;
    }
}
