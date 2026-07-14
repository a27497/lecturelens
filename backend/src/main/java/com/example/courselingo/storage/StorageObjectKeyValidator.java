package com.example.courselingo.storage;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.nio.file.Path;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class StorageObjectKeyValidator {

    private static final Pattern WINDOWS_ABSOLUTE_PATH = Pattern.compile("^[A-Za-z]:[/\\\\].*");

    public void validate(String objectKey) {
        if (objectKey == null || objectKey.isBlank()) {
            throw invalidObjectKey();
        }
        for (int index = 0; index < objectKey.length(); index++) {
            if (Character.isISOControl(objectKey.charAt(index))) {
                throw invalidObjectKey();
            }
        }
        if (objectKey.startsWith("/")
            || objectKey.contains("\\")
            || Path.of(objectKey).isAbsolute()
            || WINDOWS_ABSOLUTE_PATH.matcher(objectKey).matches()) {
            throw invalidObjectKey();
        }
        for (String segment : objectKey.split("/", -1)) {
            if ("..".equals(segment)) {
                throw invalidObjectKey();
            }
        }
    }

    private static BusinessException invalidObjectKey() {
        return new BusinessException(ErrorCode.STORAGE_INVALID_OBJECT_KEY);
    }
}
