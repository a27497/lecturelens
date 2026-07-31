package com.example.courselingo.artifact.service;

import java.util.Locale;
import java.util.function.Predicate;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class ArtifactSensitiveDataValidator {

    private static final Pattern SENSITIVE_PAIR = Pattern.compile(
        "(?i)\\b(?:authorization|token|secret|api[_-]?key|api\\s+key)\\b"
            + "(?:\\s*[:=]\\s*(?:bearer\\s+)?\\S+"
            + "|\\s+(?:bearer\\s+)?(?=\\S*(?:[0-9_./+=-]|[A-Za-z]{20}))\\S{6,})"
    );
    private static final Pattern WINDOWS_PATH = Pattern.compile("[A-Za-z]:\\\\\\S+");
    private static final Pattern UNIX_PRIVATE_PATH = Pattern.compile("(?i)(?:/users|/home)/\\S+");
    private static final String PRIVATE_KEY_TYPE = "((?:[A-Z0-9]+ )?PRIVATE KEY)";
    private static final Pattern PRIVATE_KEY_BEGIN = Pattern.compile(
        "-----BEGIN " + PRIVATE_KEY_TYPE + "-----",
        Pattern.CASE_INSENSITIVE
    );
    private static final Pattern PRIVATE_KEY_END = Pattern.compile(
        "-----END " + PRIVATE_KEY_TYPE + "-----",
        Pattern.CASE_INSENSITIVE
    );
    private static final Pattern PRIVATE_OBJECT_KEY = Pattern.compile(
        "(?i)\\b(?:uploads?|artifacts?|media|videos?)/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}/\\S+"
    );
    private static final Pattern EXAMPLE_VALUE = Pattern.compile(
        "(?i)(?:your[-_]?|example|sample|placeholder|changeme|replace[-_]?me|dummy|test[-_]?only|x{3,})"
    );
    private static final Pattern EXAMPLE_PRIVATE_PATH = Pattern.compile(
        "(?i)(?:\\\\users\\\\|/users/|/home/)(?:demo|example|sample|user|username|student|developer|dev)(?:[\\\\/]|$)"
    );

    private ArtifactSensitiveDataValidator() {
    }

    static boolean containsSensitiveData(String text) {
        if (text == null || text.isBlank()) {
            return false;
        }
        return containsMatch(SENSITIVE_PAIR, text, value -> !isExampleCredential(value))
            || PRIVATE_KEY_BEGIN.matcher(text).find()
            || PRIVATE_OBJECT_KEY.matcher(text).find()
            || containsMatch(WINDOWS_PATH, text, value -> !isExamplePath(value))
            || containsMatch(UNIX_PRIVATE_PATH, text, value -> !isExamplePath(value));
    }

    static String redactSensitiveData(String text) {
        if (text == null || text.isBlank()) {
            return text == null ? "" : text;
        }
        String redacted = redactMatches(SENSITIVE_PAIR, text, value -> !isExampleCredential(value));
        redacted = redactPrivateKeyBlocks(redacted);
        redacted = PRIVATE_OBJECT_KEY.matcher(redacted).replaceAll("[redacted]");
        redacted = redactMatches(WINDOWS_PATH, redacted, value -> !isExamplePath(value));
        return redactMatches(UNIX_PRIVATE_PATH, redacted, value -> !isExamplePath(value));
    }

    private static String redactPrivateKeyBlocks(String text) {
        Matcher beginMatcher = PRIVATE_KEY_BEGIN.matcher(text);
        if (!beginMatcher.find()) {
            return text;
        }

        StringBuilder output = new StringBuilder(text.length());
        int cursor = 0;
        do {
            output.append(text, cursor, beginMatcher.start()).append("[redacted]");
            String beginType = beginMatcher.group(1);
            Matcher endMatcher = PRIVATE_KEY_END.matcher(text);
            endMatcher.region(beginMatcher.end(), text.length());

            int blockEnd = -1;
            while (endMatcher.find()) {
                if (beginType.equalsIgnoreCase(endMatcher.group(1))) {
                    blockEnd = endMatcher.end();
                    break;
                }
            }
            if (blockEnd < 0) {
                return output.toString();
            }

            cursor = blockEnd;
            beginMatcher.region(cursor, text.length());
        } while (beginMatcher.find());
        output.append(text, cursor, text.length());
        return output.toString();
    }

    private static boolean isExampleCredential(String value) {
        return EXAMPLE_VALUE.matcher(value == null ? "" : value.toLowerCase(Locale.ROOT)).find();
    }

    private static boolean isExamplePath(String value) {
        return EXAMPLE_PRIVATE_PATH.matcher(value == null ? "" : value).find();
    }

    private static boolean containsMatch(Pattern pattern, String text, Predicate<String> sensitive) {
        Matcher matcher = pattern.matcher(text);
        while (matcher.find()) {
            if (sensitive.test(matcher.group())) {
                return true;
            }
        }
        return false;
    }

    private static String redactMatches(Pattern pattern, String text, Predicate<String> sensitive) {
        Matcher matcher = pattern.matcher(text);
        StringBuilder output = new StringBuilder(text.length());
        while (matcher.find()) {
            matcher.appendReplacement(
                output,
                Matcher.quoteReplacement(sensitive.test(matcher.group()) ? "[redacted]" : matcher.group())
            );
        }
        matcher.appendTail(output);
        return output.toString();
    }
}
