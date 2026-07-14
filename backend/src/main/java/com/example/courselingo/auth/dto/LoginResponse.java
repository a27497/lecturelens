package com.example.courselingo.auth.dto;

public record LoginResponse(
    String accessToken,
    String refreshToken,
    String tokenType,
    long expiresIn,
    User user
) {

    public record User(
        Long userId,
        String email,
        String status
    ) {
    }
}
