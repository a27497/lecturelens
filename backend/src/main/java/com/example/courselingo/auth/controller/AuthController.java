package com.example.courselingo.auth.controller;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.dto.LoginRequest;
import com.example.courselingo.auth.dto.LoginResponse;
import com.example.courselingo.auth.dto.RefreshRequest;
import com.example.courselingo.auth.dto.RegisterRequest;
import com.example.courselingo.auth.dto.RegisterResponse;
import com.example.courselingo.auth.service.AuthLoginService;
import com.example.courselingo.auth.service.AuthRegistrationService;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.auth.service.RefreshTokenService;
import com.example.courselingo.common.response.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthController {

    private final AuthRegistrationService registrationService;
    private final AuthLoginService loginService;
    private final RefreshTokenService refreshTokenService;
    private final CurrentUserService currentUserService;

    public AuthController(
        AuthRegistrationService registrationService,
        AuthLoginService loginService,
        RefreshTokenService refreshTokenService,
        CurrentUserService currentUserService
    ) {
        this.registrationService = registrationService;
        this.loginService = loginService;
        this.refreshTokenService = refreshTokenService;
        this.currentUserService = currentUserService;
    }

    @PostMapping("/api/auth/register")
    public ApiResponse<RegisterResponse> register(@Valid @RequestBody RegisterRequest request) {
        return ApiResponse.success(registrationService.register(request));
    }

    @PostMapping("/api/auth/login")
    public ApiResponse<LoginResponse> login(@Valid @RequestBody LoginRequest request) {
        return ApiResponse.success(loginService.login(request));
    }

    @PostMapping("/api/auth/refresh")
    public ApiResponse<LoginResponse> refresh(@Valid @RequestBody RefreshRequest request) {
        return ApiResponse.success(refreshTokenService.refresh(request));
    }

    @GetMapping("/api/me")
    public ApiResponse<CurrentUserResponse> me(
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader
    ) {
        return ApiResponse.success(currentUserService.currentUser(authorizationHeader));
    }
}
