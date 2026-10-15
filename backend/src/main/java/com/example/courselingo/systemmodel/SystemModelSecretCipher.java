package com.example.courselingo.systemmodel;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Component;

@Component
public final class SystemModelSecretCipher {
    public static final String MASTER_KEY_ENV = "SYSTEM_MODEL_MASTER_KEY";
    private static final String FORMAT = "v1.";
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private final SecretKey masterKey;
    private final SecureRandom random = new SecureRandom();

    public SystemModelSecretCipher() {
        // Read the deployment environment directly: YAML, JWT secrets and database values are not key sources.
        this(System.getenv(MASTER_KEY_ENV));
    }

    SystemModelSecretCipher(String encodedKey) {
        if (encodedKey == null || encodedKey.isEmpty()) {
            masterKey = null;
            return;
        }
        byte[] decoded = null;
        try {
            if (encodedKey.length() > 128) {
                throw new IllegalArgumentException();
            }
            decoded = Base64.getDecoder().decode(encodedKey);
            if (decoded.length != 32) {
                throw new IllegalArgumentException();
            }
            masterKey = new SecretKeySpec(decoded, "AES");
        } catch (IllegalArgumentException exception) {
            throw new BusinessException(ErrorCode.SYSTEM_MODEL_MASTER_KEY_INVALID);
        } finally {
            if (decoded != null) Arrays.fill(decoded, (byte) 0);
        }
    }

    public boolean configured() {
        return masterKey != null;
    }

    public EncryptedCredential encrypt(String credentialId, String apiKey) {
        requireMasterKey();
        if (!validId(credentialId) || apiKey == null || apiKey.length() < 8 || apiKey.length() > 4096
            || apiKey.chars().anyMatch(value -> value < 33 || value > 126)) {
            throw new BusinessException(ErrorCode.SYSTEM_MODEL_KEY_INVALID);
        }
        byte[] plain = apiKey.getBytes(StandardCharsets.UTF_8);
        byte[] nonce = new byte[NONCE_BYTES];
        random.nextBytes(nonce);
        try {
            Cipher cipher = cipher(Cipher.ENCRYPT_MODE, credentialId, nonce);
            byte[] encrypted = cipher.doFinal(plain);
            byte[] envelope = ByteBuffer.allocate(nonce.length + encrypted.length).put(nonce).put(encrypted).array();
            return new EncryptedCredential(
                FORMAT + Base64.getUrlEncoder().withoutPadding().encodeToString(envelope),
                apiKey.substring(apiKey.length() - 4)
            );
        } catch (GeneralSecurityException exception) {
            // Provider/library exception messages and causes must never escape the secret boundary.
            throw new BusinessException(ErrorCode.SYSTEM_MODEL_KEY_ENCRYPTION_FAILED);
        } finally {
            Arrays.fill(plain, (byte) 0);
        }
    }

    public String decrypt(String credentialId, String ciphertext) {
        requireMasterKey();
        byte[] plain = null;
        try {
            if (!validId(credentialId) || ciphertext == null || ciphertext.length() > 8192 || !ciphertext.startsWith(FORMAT)) {
                throw new IllegalArgumentException();
            }
            byte[] envelope = Base64.getUrlDecoder().decode(ciphertext.substring(FORMAT.length()));
            if (envelope.length < NONCE_BYTES + TAG_BITS / 8 + 8) {
                throw new IllegalArgumentException();
            }
            byte[] nonce = Arrays.copyOf(envelope, NONCE_BYTES);
            plain = cipher(Cipher.DECRYPT_MODE, credentialId, nonce).doFinal(envelope, NONCE_BYTES, envelope.length - NONCE_BYTES);
            return new String(plain, StandardCharsets.UTF_8);
        } catch (GeneralSecurityException | IllegalArgumentException exception) {
            throw new BusinessException(ErrorCode.SYSTEM_MODEL_KEY_DECRYPTION_FAILED);
        } finally {
            if (plain != null) Arrays.fill(plain, (byte) 0);
        }
    }

    private Cipher cipher(int mode, String credentialId, byte[] nonce) throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(mode, masterKey, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(("lecturelens/system-model/credential/v1/" + credentialId).getBytes(StandardCharsets.UTF_8));
        return cipher;
    }

    private void requireMasterKey() {
        if (masterKey == null) throw new BusinessException(ErrorCode.SYSTEM_MODEL_MASTER_KEY_MISSING);
    }

    private static boolean validId(String id) {
        return id != null && id.matches("[A-Za-z0-9_-]{1,64}");
    }

    public record EncryptedCredential(@JsonIgnore String ciphertext, String keyLast4) {
        @JsonProperty("hasKey")
        public boolean hasKey() { return true; }

        @Override
        public String toString() { return "EncryptedCredential[redacted]"; }
    }
}
