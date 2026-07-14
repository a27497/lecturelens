package com.example.courselingo.auth.dto;

public record RegisterResponse(
    Long userId,
    String email,
    String status
) {
}
