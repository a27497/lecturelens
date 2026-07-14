package com.example.courselingo.auth.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import org.springframework.stereotype.Service;

@Service
public class RefreshTokenHashService {

    public String sha256Hex(String refreshToken) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(refreshToken.getBytes(StandardCharsets.UTF_8));
            return toHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is not available", exception);
        }
    }

    private String toHex(byte[] bytes) {
        StringBuilder builder = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) {
            builder.append(String.format("%02x", value));
        }
        return builder.toString();
    }
}
