package com.example.courselingo.auth.dto;

import com.example.courselingo.auth.entity.UserRole;

public record CurrentUserResponse(
    Long userId,
    String email,
    String status,
    UserRole role
) {
    public CurrentUserResponse(Long userId, String email, String status) {
        this(userId, email, status, UserRole.USER);
    }
}
