package com.example.courselingo.auth;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.auth.controller.AuthController;
import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.dto.LoginResponse;
import com.example.courselingo.auth.dto.RegisterResponse;
import com.example.courselingo.auth.service.AuthLoginService;
import com.example.courselingo.auth.service.AuthRegistrationService;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.auth.service.RefreshTokenService;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(AuthController.class)
@Import(GlobalExceptionHandler.class)
class AuthControllerTest {

    private final MockMvc mockMvc;

    @Autowired
    private AuthRegistrationService registrationService;

    @Autowired
    private AuthLoginService loginService;

    @Autowired
    private RefreshTokenService refreshTokenService;

    @Autowired
    private CurrentUserService currentUserService;

    @Autowired
    AuthControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @Test
    void authControllerRequiresRegistrationLoginAndRefreshServiceConstructorInjection() throws NoSuchMethodException {
        assertThat(AuthController.class.getConstructor(
            AuthRegistrationService.class,
            AuthLoginService.class,
            RefreshTokenService.class,
            CurrentUserService.class
        )).isNotNull();
    }

    @TestConfiguration
    static class TestConfig {

        @Bean
        AuthRegistrationService registrationService() {
            return Mockito.mock(AuthRegistrationService.class);
        }

        @Bean
        AuthLoginService loginService() {
            return Mockito.mock(AuthLoginService.class);
        }

        @Bean
        RefreshTokenService refreshTokenService() {
            return Mockito.mock(RefreshTokenService.class);
        }

        @Bean
        CurrentUserService currentUserService() {
            return Mockito.mock(CurrentUserService.class);
        }
    }

    @Test
    void registerReturnsApiResponseSuccessForValidRequest() throws Exception {
        when(registrationService.register(any()))
            .thenReturn(new RegisterResponse(1L, "demo@example.com", "ACTIVE"));

        mockMvc.perform(post("/api/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"demo@example.com\",\"password\":\"Password123!\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("0"))
            .andExpect(jsonPath("$.message").value("ok"))
            .andExpect(jsonPath("$.data.userId").value(1))
            .andExpect(jsonPath("$.data.email").value("demo@example.com"))
            .andExpect(jsonPath("$.data.status").value("ACTIVE"))
            .andExpect(jsonPath("$.data.password").doesNotExist())
            .andExpect(jsonPath("$.data.passwordHash").doesNotExist())
            .andExpect(content().string(not(containsString("Password123!"))))
            .andExpect(content().string(not(containsString("passwordHash"))));
    }

    @Test
    void loginReturnsApiResponseSuccessForValidRequest() throws Exception {
        when(loginService.login(any()))
            .thenReturn(new LoginResponse(
                "access-token",
                "refresh-token",
                "Bearer",
                3600L,
                new LoginResponse.User(1L, "demo@example.com", "ACTIVE")
            ));

        mockMvc.perform(post("/api/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"demo@example.com\",\"password\":\"Password123!\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("0"))
            .andExpect(jsonPath("$.message").value("ok"))
            .andExpect(jsonPath("$.data.accessToken").value("access-token"))
            .andExpect(jsonPath("$.data.refreshToken").value("refresh-token"))
            .andExpect(jsonPath("$.data.tokenType").value("Bearer"))
            .andExpect(jsonPath("$.data.expiresIn").value(3600))
            .andExpect(jsonPath("$.data.user.userId").value(1))
            .andExpect(jsonPath("$.data.user.email").value("demo@example.com"))
            .andExpect(jsonPath("$.data.user.status").value("ACTIVE"))
            .andExpect(jsonPath("$.data.password").doesNotExist())
            .andExpect(jsonPath("$.data.passwordHash").doesNotExist())
            .andExpect(jsonPath("$.data.tokenHash").doesNotExist())
            .andExpect(content().string(not(containsString("Password123!"))))
            .andExpect(content().string(not(containsString("passwordHash"))))
            .andExpect(content().string(not(containsString("tokenHash"))));
    }

    @Test
    void refreshReturnsApiResponseSuccessForValidRequest() throws Exception {
        when(refreshTokenService.refresh(any()))
            .thenReturn(new LoginResponse(
                "new-access-token",
                "new-refresh-token",
                "Bearer",
                3600L,
                new LoginResponse.User(1L, "demo@example.com", "ACTIVE")
            ));

        mockMvc.perform(post("/api/auth/refresh")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"refreshToken\":\"old-refresh-token\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("0"))
            .andExpect(jsonPath("$.message").value("ok"))
            .andExpect(jsonPath("$.data.accessToken").value("new-access-token"))
            .andExpect(jsonPath("$.data.refreshToken").value("new-refresh-token"))
            .andExpect(jsonPath("$.data.tokenType").value("Bearer"))
            .andExpect(jsonPath("$.data.expiresIn").value(3600))
            .andExpect(jsonPath("$.data.user.userId").value(1))
            .andExpect(jsonPath("$.data.user.email").value("demo@example.com"))
            .andExpect(jsonPath("$.data.user.status").value("ACTIVE"))
            .andExpect(jsonPath("$.data.tokenHash").doesNotExist())
            .andExpect(jsonPath("$.data.password").doesNotExist())
            .andExpect(jsonPath("$.data.passwordHash").doesNotExist())
            .andExpect(content().string(not(containsString("tokenHash"))))
            .andExpect(content().string(not(containsString("passwordHash"))));
    }

    @Test
    void refreshReturnsValidationErrorForBlankRefreshToken() throws Exception {
        mockMvc.perform(post("/api/auth/refresh")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"refreshToken\":\"   \"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_VALIDATION_FAILED.code()))
            .andExpect(jsonPath("$.data.refreshToken").exists());
    }

    @Test
    void meReturnsCurrentUserForValidBearerAccessToken() throws Exception {
        doReturn(new CurrentUserResponse(1L, "demo@example.com", "ACTIVE"))
            .when(currentUserService).currentUser("Bearer access-token");

        mockMvc.perform(get("/api/me")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("0"))
            .andExpect(jsonPath("$.message").value("ok"))
            .andExpect(jsonPath("$.data.userId").value(1))
            .andExpect(jsonPath("$.data.email").value("demo@example.com"))
            .andExpect(jsonPath("$.data.status").value("ACTIVE"))
            .andExpect(jsonPath("$.data.password").doesNotExist())
            .andExpect(jsonPath("$.data.passwordHash").doesNotExist())
            .andExpect(jsonPath("$.data.refreshToken").doesNotExist())
            .andExpect(jsonPath("$.data.tokenHash").doesNotExist())
            .andExpect(content().string(not(containsString("passwordHash"))))
            .andExpect(content().string(not(containsString("refreshToken"))))
            .andExpect(content().string(not(containsString("tokenHash"))));
    }

    @Test
    void meReturnsUnauthorizedWhenAuthorizationHeaderMissing() throws Exception {
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(currentUserService).currentUser(null);

        mockMvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_UNAUTHORIZED.code()));
    }

    @Test
    void meReturnsUnauthorizedWhenAuthorizationHeaderIsNotBearer() throws Exception {
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(currentUserService).currentUser("Basic access-token");

        mockMvc.perform(get("/api/me")
                .header("Authorization", "Basic access-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_UNAUTHORIZED.code()));
    }

    @Test
    void meRejectsRefreshOrNonAccessToken() throws Exception {
        doThrow(new BusinessException(ErrorCode.AUTH_TOKEN_INVALID))
            .when(currentUserService).currentUser("Bearer refresh-token");

        mockMvc.perform(get("/api/me")
                .header("Authorization", "Bearer refresh-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value(ErrorCode.AUTH_TOKEN_INVALID.code()));
    }

    @Test
    void loginReturnsValidationErrorForInvalidEmail() throws Exception {
        mockMvc.perform(post("/api/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"not-an-email\",\"password\":\"Password123!\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_VALIDATION_FAILED.code()))
            .andExpect(jsonPath("$.data.email").exists());
    }

    @Test
    void loginReturnsValidationErrorForBlankPassword() throws Exception {
        mockMvc.perform(post("/api/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"demo@example.com\",\"password\":\"   \"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_VALIDATION_FAILED.code()))
            .andExpect(jsonPath("$.data.password").exists());
    }

    @Test
    void registerReturnsValidationErrorForInvalidEmail() throws Exception {
        mockMvc.perform(post("/api/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"not-an-email\",\"password\":\"Password123!\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_VALIDATION_FAILED.code()))
            .andExpect(jsonPath("$.data.email").exists());
    }

    @Test
    void registerReturnsValidationErrorForShortPassword() throws Exception {
        mockMvc.perform(post("/api/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"demo@example.com\",\"password\":\"P1!\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_VALIDATION_FAILED.code()))
            .andExpect(jsonPath("$.data.password").exists());
    }
}
