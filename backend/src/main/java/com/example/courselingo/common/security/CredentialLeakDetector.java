package com.example.courselingo.common.security;

import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class CredentialLeakDetector {

    private static final Pattern AUTHORIZATION_BEARER = Pattern.compile(
        "(?i)\\bauthorization\\b(?:\\s*[:=]\\s*|\\s+)bearer\\s+\\S{4,}"
    );
    private static final Pattern LABELED_CREDENTIAL = Pattern.compile(
        "(?i)\\b(?:token|secret|api[_-]?key|api\\s+key)\\b"
            + "(?:\\s*[:=]\\s*|\\s+)(?:bearer\\s+)?"
            + "(?=\\S*(?:[0-9_/+=-]|[A-Za-z]{20}))\\S{6,}"
    );
    private static final Pattern JWT = Pattern.compile(
        "(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{5,}\\.[A-Za-z0-9_-]{5,}\\.[A-Za-z0-9_-]{5,}"
            + "(?![A-Za-z0-9_-])"
    );
    private static final Pattern EXAMPLE_VALUE = Pattern.compile(
        "(?i)(?:your[-_]?|example|sample|placeholder|changeme|replace[-_]?me|dummy|test[-_]?only|x{3,})"
    );

    private CredentialLeakDetector() {
    }

    public static boolean containsCredential(String text) {
        if (text == null || text.isBlank()) {
            return false;
        }
        return containsRealMatch(AUTHORIZATION_BEARER, text)
            || containsRealMatch(LABELED_CREDENTIAL, text)
            || containsRealMatch(JWT, text);
    }

    public static String redactCredentials(String text) {
        if (text == null || text.isBlank()) {
            return text == null ? "" : text;
        }
        return redactRealMatches(
            JWT,
            redactRealMatches(LABELED_CREDENTIAL, redactRealMatches(AUTHORIZATION_BEARER, text))
        );
    }

    private static boolean containsRealMatch(Pattern pattern, String text) {
        Matcher matcher = pattern.matcher(text);
        while (matcher.find()) {
            if (!isExampleValue(matcher.group())) {
                return true;
            }
        }
        return false;
    }

    private static String redactRealMatches(Pattern pattern, String text) {
        Matcher matcher = pattern.matcher(text);
        StringBuilder output = new StringBuilder(text.length());
        while (matcher.find()) {
            matcher.appendReplacement(
                output,
                Matcher.quoteReplacement(isExampleValue(matcher.group()) ? matcher.group() : "[redacted]")
            );
        }
        matcher.appendTail(output);
        return output.toString();
    }

    private static boolean isExampleValue(String value) {
        return EXAMPLE_VALUE.matcher(value == null ? "" : value.toLowerCase(Locale.ROOT)).find();
    }
}
