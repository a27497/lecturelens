package com.example.courselingo.auth.service;

import com.example.courselingo.auth.entity.UserRole;

public record AccessTokenClaims(Long userId, UserRole role) {
    public AccessTokenClaims(Long userId) {
        this(userId, UserRole.USER);
    }
}
