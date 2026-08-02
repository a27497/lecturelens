package com.example.courselingo.learning.service;

import com.example.courselingo.common.security.CredentialLeakDetector;
import java.util.regex.Pattern;

final class LearningPackageSensitiveDataValidator {

    private static final Pattern WINDOWS_PATH = Pattern.compile("[A-Za-z]:\\\\\\S+");
    private static final Pattern UNIX_PRIVATE_PATH = Pattern.compile("(?i)(?:/users|/home)/\\S+");

    private LearningPackageSensitiveDataValidator() {
    }

    static boolean containsSensitiveData(String text) {
        if (text == null || text.isBlank()) {
            return false;
        }
        return CredentialLeakDetector.containsCredential(text)
            || WINDOWS_PATH.matcher(text).find()
            || UNIX_PRIVATE_PATH.matcher(text).find();
    }
}
