package com.example.courselingo.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.example.courselingo.auth.dto.RegisterRequest;
import com.example.courselingo.auth.dto.RegisterResponse;
import com.example.courselingo.auth.entity.UserAccount;
import com.example.courselingo.auth.mapper.UserAccountMapper;
import com.example.courselingo.auth.service.AuthRegistrationService;
import com.example.courselingo.auth.service.AuthRegistrationServiceImpl;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@ExtendWith(MockitoExtension.class)
class AuthRegistrationServiceTest {

    @Mock
    private UserAccountMapper userAccountMapper;

    private AuthRegistrationService registrationService;

    private PasswordEncoder passwordEncoder;

    @BeforeEach
    void setUp() {
        passwordEncoder = new BCryptPasswordEncoder();
        registrationService = new AuthRegistrationServiceImpl(userAccountMapper, passwordEncoder);
    }

    @Test
    void registerNormalizesEmailHashesPasswordAndReturnsCreatedUser() {
        when(userAccountMapper.selectOne(anyUserAccountWrapper())).thenReturn(null);
        when(userAccountMapper.insert(any(UserAccount.class))).thenAnswer(invocation -> {
            UserAccount userAccount = invocation.getArgument(0);
            userAccount.setId(1L);
            return 1;
        });

        RegisterResponse response = registrationService.register(
            new RegisterRequest("  Demo@Example.COM  ", "Password123!")
        );

        ArgumentCaptor<UserAccount> captor = ArgumentCaptor.forClass(UserAccount.class);
        verify(userAccountMapper).insert(captor.capture());
        UserAccount saved = captor.getValue();

        assertThat(saved.getEmail()).isEqualTo("demo@example.com");
        assertThat(saved.getStatus()).isEqualTo("ACTIVE");
        assertThat(saved.getPasswordHash()).isNotEqualTo("Password123!");
        assertThat(passwordEncoder.matches("Password123!", saved.getPasswordHash())).isTrue();
        assertThat(response.userId()).isEqualTo(1L);
        assertThat(response.email()).isEqualTo("demo@example.com");
        assertThat(response.status()).isEqualTo("ACTIVE");
    }

    @Test
    void registerRejectsDuplicateEmail() {
        UserAccount existing = new UserAccount();
        existing.setId(9L);
        existing.setEmail("demo@example.com");
        when(userAccountMapper.selectOne(anyUserAccountWrapper())).thenReturn(existing);

        assertThatThrownBy(() -> registrationService.register(new RegisterRequest("demo@example.com", "Password123!")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_EMAIL_ALREADY_EXISTS);

        verify(userAccountMapper, never()).insert(any(UserAccount.class));
    }

    @Test
    void registerConvertsUniqueIndexConflictToDuplicateEmailBusinessError() {
        when(userAccountMapper.selectOne(anyUserAccountWrapper())).thenReturn(null);
        when(userAccountMapper.insert(any(UserAccount.class))).thenThrow(new DuplicateKeyException("uk_user_account_email"));

        assertThatThrownBy(() -> registrationService.register(new RegisterRequest("demo@example.com", "Password123!")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_EMAIL_ALREADY_EXISTS);
    }

    @Test
    void registerRejectsWeakPasswordWithoutPersistingUser() {
        assertThatThrownBy(() -> registrationService.register(new RegisterRequest("demo@example.com", "password")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_PASSWORD_WEAK);

        verify(userAccountMapper, never()).insert(any(UserAccount.class));
    }

    @Test
    void registerDoesNotReturnTokens() {
        RegisterResponse response = new RegisterResponse(1L, "demo@example.com", "ACTIVE");

        assertThat(RegisterResponse.class.getRecordComponents())
            .extracting(component -> component.getName())
            .containsExactly("userId", "email", "status");
        assertThat(response.email()).isEqualTo("demo@example.com");
    }

    private Wrapper<UserAccount> anyUserAccountWrapper() {
        return any();
    }
}
