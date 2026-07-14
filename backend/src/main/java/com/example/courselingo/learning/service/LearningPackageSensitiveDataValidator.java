package com.example.courselingo.learning.service;

import java.util.regex.Pattern;

final class LearningPackageSensitiveDataValidator {

    private static final Pattern SENSITIVE_PAIR = Pattern.compile(
        "(?i)\\b(?:authorization|token|secret|api[_-]?key|api\\s+key)\\b(?:\\s*[:=]\\s*|\\s+)\\S+"
    );
    private static final Pattern SENSITIVE_WORD = Pattern.compile(
        "(?i)\\b(?:authorization|token|secret|api[_-]?key|api\\s+key)\\b"
    );
    private static final Pattern WINDOWS_PATH = Pattern.compile("[A-Za-z]:\\\\\\S+");
    private static final Pattern UNIX_PRIVATE_PATH = Pattern.compile("(?i)(?:/users|/home)/\\S+");

    private LearningPackageSensitiveDataValidator() {
    }

    static boolean containsSensitiveData(String text) {
        if (text == null || text.isBlank()) {
            return false;
        }
        return SENSITIVE_PAIR.matcher(text).find()
            || SENSITIVE_WORD.matcher(text).find()
            || WINDOWS_PATH.matcher(text).find()
            || UNIX_PRIVATE_PATH.matcher(text).find();
    }
}
