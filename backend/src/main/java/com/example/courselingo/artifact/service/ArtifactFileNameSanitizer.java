package com.example.courselingo.artifact.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.nio.file.Path;
import java.util.regex.Pattern;

final class ArtifactFileNameSanitizer {

    private static final Pattern WINDOWS_ABSOLUTE_PATH = Pattern.compile("^[A-Za-z]:[/\\\\].*");
    private static final int MAX_FILE_NAME_LENGTH = 255;

    private ArtifactFileNameSanitizer() {
    }

    static String validateFileName(String fileName) {
        String normalized = requiredText(fileName, "Artifact file name is required");
        if (normalized.length() > MAX_FILE_NAME_LENGTH
            || normalized.contains("/")
            || normalized.contains("\\")
            || normalized.contains("..")
            || normalized.startsWith(".")
            || Path.of(normalized).isAbsolute()
            || WINDOWS_ABSOLUTE_PATH.matcher(normalized).matches()
            || containsControlCharacter(normalized)
            || ArtifactSensitiveDataValidator.containsSensitiveData(normalized)) {
            throw validationFailure("Artifact file name is invalid");
        }
        return normalized;
    }

    static String toObjectKeySegment(String fileName) {
        StringBuilder safe = new StringBuilder();
        for (int index = 0; index < fileName.length(); index++) {
            char ch = fileName.charAt(index);
            if ((ch >= 'a' && ch <= 'z')
                || (ch >= 'A' && ch <= 'Z')
                || (ch >= '0' && ch <= '9')
                || ch == '.'
                || ch == '_'
                || ch == '-') {
                safe.append(ch);
            } else {
                safe.append('_');
            }
        }
        return safe.toString();
    }

    private static boolean containsControlCharacter(String value) {
        for (int index = 0; index < value.length(); index++) {
            if (Character.isISOControl(value.charAt(index))) {
                return true;
            }
        }
        return false;
    }

    private static String requiredText(String value, String message) {
        if (value == null || value.isBlank()) {
            throw validationFailure(message);
        }
        return value.strip();
    }

    private static BusinessException validationFailure(String message) {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, message);
    }
}
