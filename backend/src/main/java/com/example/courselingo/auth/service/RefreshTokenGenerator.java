package com.example.courselingo.auth.service;

import java.security.SecureRandom;
import java.util.Base64;
import org.springframework.stereotype.Service;

@Service
public class RefreshTokenGenerator {

    private static final int TOKEN_BYTES = 32;

    private final SecureRandom secureRandom = new SecureRandom();

    public String generate() {
        byte[] randomBytes = new byte[TOKEN_BYTES];
        secureRandom.nextBytes(randomBytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(randomBytes);
    }
}
