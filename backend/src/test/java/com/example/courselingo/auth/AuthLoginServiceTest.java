package com.example.courselingo.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.baomidou.mybatisplus.core.conditions.AbstractWrapper;
import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import com.example.courselingo.auth.dto.LoginRequest;
import com.example.courselingo.auth.dto.LoginResponse;
import com.example.courselingo.auth.entity.UserAccount;
import com.example.courselingo.auth.mapper.UserAccountMapper;
import com.example.courselingo.auth.service.AuthLoginService;
import com.example.courselingo.auth.service.AuthLoginServiceImpl;
import com.example.courselingo.auth.service.JwtAccessTokenService;
import com.example.courselingo.auth.service.RefreshTokenService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.apache.ibatis.session.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@ExtendWith(MockitoExtension.class)
class AuthLoginServiceTest {

    @Mock
    private UserAccountMapper userAccountMapper;

    @Mock
    private JwtAccessTokenService jwtAccessTokenService;

    @Mock
    private RefreshTokenService refreshTokenService;

    private PasswordEncoder passwordEncoder;

    private AuthLoginService loginService;

    @BeforeEach
    void setUp() {
        TableInfoHelper.initTableInfo(new MapperBuilderAssistant(new Configuration(), ""), UserAccount.class);
        passwordEncoder = new BCryptPasswordEncoder();
        loginService = new AuthLoginServiceImpl(userAccountMapper, passwordEncoder, jwtAccessTokenService, refreshTokenService);
    }

    @Test
    void loginNormalizesEmailVerifiesPasswordAndReturnsAccessToken() {
        UserAccount userAccount = activeUser();
        when(userAccountMapper.selectOne(anyUserAccountWrapper())).thenReturn(userAccount);
        when(jwtAccessTokenService.generate(userAccount)).thenReturn("access-token");
        when(jwtAccessTokenService.expiresIn()).thenReturn(3600L);
        when(refreshTokenService.issue(userAccount)).thenReturn("refresh-token");

        LoginResponse response = loginService.login(new LoginRequest("  Demo@Example.COM  ", "Password123!"));

        ArgumentCaptor<Wrapper<UserAccount>> queryCaptor = ArgumentCaptor.forClass(Wrapper.class);
        verify(userAccountMapper).selectOne(queryCaptor.capture());
        Wrapper<UserAccount> capturedQuery = queryCaptor.getValue();
        assertThat(capturedQuery.getSqlSegment()).contains("email");
        assertThat(((AbstractWrapper<?, ?, ?>) capturedQuery).getParamNameValuePairs())
            .containsValue("demo@example.com");
        assertThat(response.accessToken()).isEqualTo("access-token");
        assertThat(response.refreshToken()).isEqualTo("refresh-token");
        assertThat(response.tokenType()).isEqualTo("Bearer");
        assertThat(response.expiresIn()).isEqualTo(3600L);
        assertThat(response.user().userId()).isEqualTo(1L);
        assertThat(response.user().email()).isEqualTo("demo@example.com");
        assertThat(response.user().status()).isEqualTo("ACTIVE");
    }

    @Test
    void loginRejectsMissingUserAsInvalidCredentials() {
        when(userAccountMapper.selectOne(anyUserAccountWrapper())).thenReturn(null);

        assertThatThrownBy(() -> loginService.login(new LoginRequest("demo@example.com", "Password123!")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_INVALID_CREDENTIALS);

        verify(jwtAccessTokenService, never()).generate(any(UserAccount.class));
        verify(refreshTokenService, never()).issue(any(UserAccount.class));
    }

    @Test
    void loginRejectsBadPasswordAsInvalidCredentials() {
        UserAccount userAccount = activeUser();
        when(userAccountMapper.selectOne(anyUserAccountWrapper())).thenReturn(userAccount);

        assertThatThrownBy(() -> loginService.login(new LoginRequest("demo@example.com", "WrongPassword123!")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_INVALID_CREDENTIALS);

        verify(jwtAccessTokenService, never()).generate(any(UserAccount.class));
        verify(refreshTokenService, never()).issue(any(UserAccount.class));
    }

    @Test
    void loginRejectsDisabledUser() {
        UserAccount userAccount = activeUser();
        userAccount.setStatus("DISABLED");
        when(userAccountMapper.selectOne(anyUserAccountWrapper())).thenReturn(userAccount);

        assertThatThrownBy(() -> loginService.login(new LoginRequest("demo@example.com", "Password123!")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_USER_DISABLED);

        verify(jwtAccessTokenService, never()).generate(any(UserAccount.class));
        verify(refreshTokenService, never()).issue(any(UserAccount.class));
    }

    @Test
    void loginResponseDoesNotExposePasswordOrTokenHash() {
        assertThat(LoginResponse.class.getRecordComponents())
            .extracting(component -> component.getName())
            .containsExactly("accessToken", "refreshToken", "tokenType", "expiresIn", "user");
        assertThat(LoginResponse.User.class.getRecordComponents())
            .extracting(component -> component.getName())
            .containsExactly("userId", "email", "status");
    }

    private UserAccount activeUser() {
        UserAccount userAccount = new UserAccount();
        userAccount.setId(1L);
        userAccount.setEmail("demo@example.com");
        userAccount.setPasswordHash(passwordEncoder.encode("Password123!"));
        userAccount.setStatus("ACTIVE");
        return userAccount;
    }

    private Wrapper<UserAccount> anyUserAccountWrapper() {
        return any();
    }
}
