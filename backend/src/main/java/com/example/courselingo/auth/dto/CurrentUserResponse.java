package com.example.courselingo.auth.dto;

public record CurrentUserResponse(
    Long userId,
    String email,
    String status
) {
}
