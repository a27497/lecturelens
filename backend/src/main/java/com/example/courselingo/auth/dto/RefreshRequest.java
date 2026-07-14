package com.example.courselingo.auth.dto;

import jakarta.validation.constraints.NotBlank;

public record RefreshRequest(
    @NotBlank(message = "refreshToken不能为空")
    String refreshToken
) {
}
