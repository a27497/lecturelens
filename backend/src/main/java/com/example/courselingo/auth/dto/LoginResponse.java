package com.example.courselingo.auth.dto;

import com.example.courselingo.auth.entity.UserRole;

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
        String status,
        UserRole role
    ) {
        public User(Long userId, String email, String status) {
            this(userId, email, status, UserRole.USER);
        }
    }
}
