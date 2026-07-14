package com.example.courselingo.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.entity.UserAccount;
import com.example.courselingo.auth.mapper.UserAccountMapper;
import com.example.courselingo.auth.service.AccessTokenClaims;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.auth.service.CurrentUserServiceImpl;
import com.example.courselingo.auth.service.JwtAccessTokenService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CurrentUserServiceTest {

    @Mock
    private JwtAccessTokenService jwtAccessTokenService;

    @Mock
    private UserAccountMapper userAccountMapper;

    private CurrentUserService currentUserService;

    @BeforeEach
    void setUp() {
        currentUserService = new CurrentUserServiceImpl(jwtAccessTokenService, userAccountMapper);
    }

    @Test
    void currentUserUsesDatabaseUserInsteadOfTokenClaims() {
        when(jwtAccessTokenService.parseAccessToken("access-token"))
            .thenReturn(new AccessTokenClaims(1L));
        UserAccount databaseUser = activeUser();
        databaseUser.setEmail("database@example.com");
        when(userAccountMapper.selectById(1L)).thenReturn(databaseUser);

        CurrentUserResponse response = currentUserService.currentUser("Bearer access-token");

        assertThat(response.userId()).isEqualTo(1L);
        assertThat(response.email()).isEqualTo("database@example.com");
        assertThat(response.status()).isEqualTo("ACTIVE");
    }

    @Test
    void currentUserRejectsMissingAuthorizationHeader() {
        assertThatThrownBy(() -> currentUserService.currentUser(null))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_UNAUTHORIZED);
    }

    @Test
    void currentUserRejectsNonBearerAuthorizationHeader() {
        assertThatThrownBy(() -> currentUserService.currentUser("Basic access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_UNAUTHORIZED);
    }

    @Test
    void currentUserRejectsMissingUser() {
        when(jwtAccessTokenService.parseAccessToken("access-token"))
            .thenReturn(new AccessTokenClaims(1L));
        when(userAccountMapper.selectById(1L)).thenReturn(null);

        assertThatThrownBy(() -> currentUserService.currentUser("Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_INVALID_CREDENTIALS);
    }

    @Test
    void currentUserRejectsDisabledUser() {
        when(jwtAccessTokenService.parseAccessToken("access-token"))
            .thenReturn(new AccessTokenClaims(1L));
        UserAccount databaseUser = activeUser();
        databaseUser.setStatus("DISABLED");
        when(userAccountMapper.selectById(1L)).thenReturn(databaseUser);

        assertThatThrownBy(() -> currentUserService.currentUser("Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_USER_DISABLED);
    }

    @Test
    void currentUserResponseDoesNotExposeSensitiveFields() {
        assertThat(CurrentUserResponse.class.getRecordComponents())
            .extracting(component -> component.getName())
            .containsExactly("userId", "email", "status");
    }

    private UserAccount activeUser() {
        UserAccount userAccount = new UserAccount();
        userAccount.setId(1L);
        userAccount.setEmail("demo@example.com");
        userAccount.setPasswordHash("password-hash");
        userAccount.setStatus("ACTIVE");
        return userAccount;
    }
}
