package com.example.courselingo.auth.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record RegisterRequest(
    @NotBlank(message = "邮箱不能为空")
    @Email(message = "邮箱格式不正确")
    String email,

    @NotBlank(message = "密码不能为空")
    @Size(min = 8, max = 72, message = "密码长度必须在 8 到 72 个字符之间")
    @Pattern(
        regexp = "^(?=.*[A-Za-z])(?=.*\\d).+$",
        message = "密码至少包含字母和数字"
    )
    String password
) {
}
