package com.example.courselingo.storage;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import org.junit.jupiter.api.Test;

class StorageObjectKeyValidatorTest {

    private final StorageObjectKeyValidator validator = new StorageObjectKeyValidator();

    @Test
    void acceptsInternalObjectKey() {
        assertThatCode(() -> validator.validate("raw/1/up_test/source.mp4"))
            .doesNotThrowAnyException();
    }

    @Test
    void rejectsBlankObjectKey() {
        assertInvalidObjectKey(null);
        assertInvalidObjectKey("");
        assertInvalidObjectKey("   ");
    }

    @Test
    void rejectsObjectKeyStartingWithSlash() {
        assertInvalidObjectKey("/raw/1/source.mp4");
    }

    @Test
    void rejectsObjectKeyContainingBackslash() {
        assertInvalidObjectKey("raw\\1\\source.mp4");
    }

    @Test
    void rejectsObjectKeyContainingPathTraversalSegment() {
        assertInvalidObjectKey("../raw/1/source.mp4");
        assertInvalidObjectKey("raw/../source.mp4");
        assertInvalidObjectKey("raw/..");
    }

    @Test
    void rejectsObjectKeyContainingControlCharacter() {
        assertInvalidObjectKey("raw/1/source\n.mp4");
    }

    @Test
    void rejectsWindowsAbsolutePathObjectKey() {
        assertInvalidObjectKey("C:\\test\\a.mp4");
        assertInvalidObjectKey("C:/test/a.mp4");
    }

    private void assertInvalidObjectKey(String objectKey) {
        assertThatThrownBy(() -> validator.validate(objectKey))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.STORAGE_INVALID_OBJECT_KEY);
    }
}
