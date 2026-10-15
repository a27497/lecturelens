package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Arrays;
import java.util.Base64;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class SystemModelSecretCipherTest {
    static final String TEST_KEY = Base64.getEncoder().encodeToString(new byte[32]);
    private static final String API_KEY = "test-only-opaque-model-secret-9347";
    private final SystemModelSecretCipher cipher = new SystemModelSecretCipher(TEST_KEY);

    @Test
    void roundTripUsesFreshNoncesAndExposesOnlyMask() throws Exception {
        var first = cipher.encrypt("provider-17", API_KEY);
        var second = cipher.encrypt("provider-17", API_KEY);

        assertThat(cipher.decrypt("provider-17", first.ciphertext())).isEqualTo(API_KEY);
        assertThat(first.ciphertext()).startsWith("v1.").isNotEqualTo(second.ciphertext()).doesNotContain(API_KEY);
        assertThat(first.keyLast4()).isEqualTo("9347");
        assertThat(first.toString()).doesNotContain(API_KEY, first.ciphertext(), "9347");
        var response = new ObjectMapper().readTree(new ObjectMapper().writeValueAsString(first));
        assertThat(response.size()).isEqualTo(2);
        assertThat(response.path("hasKey").asBoolean()).isTrue();
        assertThat(response.path("keyLast4").asText()).isEqualTo("9347");
        assertThat(response.has("ciphertext")).isFalse();
    }

    @Test
    void maximumSizeKeyRoundTripsWithinStorageLimit() {
        String key = "a".repeat(4096);
        String encrypted = cipher.encrypt("provider-17", key).ciphertext();
        assertThat(encrypted.length()).isLessThanOrEqualTo(8192);
        assertThat(cipher.decrypt("provider-17", encrypted)).isEqualTo(key);
    }

    @Test
    void wrongKeyAndObjectSubstitutionFailWithoutSensitiveCauses() {
        String encrypted = cipher.encrypt("provider-17", API_KEY).ciphertext();
        byte[] otherKey = new byte[32];
        Arrays.fill(otherKey, (byte) 7);
        var otherCipher = new SystemModelSecretCipher(Base64.getEncoder().encodeToString(otherKey));
        assertDecryptFailure(() -> otherCipher.decrypt("provider-17", encrypted));
        assertDecryptFailure(() -> cipher.decrypt("provider-18", encrypted));
    }

    @ParameterizedTest
    @ValueSource(ints = {0, 12, 20, 58})
    void nonceCiphertextAndTagTamperingFail(int offset) {
        String encrypted = cipher.encrypt("provider-17", API_KEY).ciphertext();
        byte[] envelope = Base64.getUrlDecoder().decode(encrypted.substring(3));
        envelope[Math.min(offset, envelope.length - 1)] ^= 1;
        String changed = "v1." + Base64.getUrlEncoder().withoutPadding().encodeToString(envelope);
        assertDecryptFailure(() -> cipher.decrypt("provider-17", changed));
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {"v2.invalid", "v1.***", "v1.AAAA", "opaque-secret-value"})
    void malformedCiphertextFailsWithoutEchoingInput(String encrypted) {
        assertDecryptFailure(() -> cipher.decrypt("provider-17", encrypted));
    }

    @ParameterizedTest
    @ValueSource(strings = {"invalid-base64", "YWJj", " ", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"})
    void rejectsInvalidMasterKeyWithoutEchoingIt(String key) {
        assertThatThrownBy(() -> new SystemModelSecretCipher(key))
            .isInstanceOf(BusinessException.class)
            .hasMessage(ErrorCode.SYSTEM_MODEL_MASTER_KEY_INVALID.defaultMessage())
            .hasNoCause();
    }

    @Test
    void absentMasterAllowsLegacyStartupButCannotEncryptOrDecrypt() {
        var absent = new SystemModelSecretCipher(null);
        assertThat(absent.configured()).isFalse();
        assertThatThrownBy(() -> absent.encrypt("provider-17", API_KEY))
            .hasMessage(ErrorCode.SYSTEM_MODEL_MASTER_KEY_MISSING.defaultMessage()).hasNoCause();
        assertThatThrownBy(() -> absent.decrypt("provider-17", "v1.AAAA"))
            .hasMessage(ErrorCode.SYSTEM_MODEL_MASTER_KEY_MISSING.defaultMessage()).hasNoCause();
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {"short", "secret\r\nAuthorization", "key with spaces", "密钥密钥密钥密钥"})
    void invalidApiKeysAreRejectedBeforeStorage(String key) {
        assertThatThrownBy(() -> cipher.encrypt("provider-17", key))
            .hasMessage(ErrorCode.SYSTEM_MODEL_KEY_INVALID.defaultMessage()).hasNoCause();
    }

    private void assertDecryptFailure(org.assertj.core.api.ThrowableAssert.ThrowingCallable action) {
        assertThatThrownBy(action).isInstanceOf(BusinessException.class)
            .hasMessage(ErrorCode.SYSTEM_MODEL_KEY_DECRYPTION_FAILED.defaultMessage())
            .hasNoCause();
    }
}
