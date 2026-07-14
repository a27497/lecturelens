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
import com.example.courselingo.auth.dto.LoginResponse;
import com.example.courselingo.auth.dto.RefreshRequest;
import com.example.courselingo.auth.entity.RefreshToken;
import com.example.courselingo.auth.entity.UserAccount;
import com.example.courselingo.auth.mapper.RefreshTokenMapper;
import com.example.courselingo.auth.mapper.UserAccountMapper;
import com.example.courselingo.auth.service.JwtAccessTokenService;
import com.example.courselingo.auth.service.RefreshTokenGenerator;
import com.example.courselingo.auth.service.RefreshTokenHashService;
import com.example.courselingo.auth.service.RefreshTokenService;
import com.example.courselingo.auth.service.RefreshTokenServiceImpl;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.infrastructure.RefreshTokenProperties;
import java.time.LocalDateTime;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class RefreshTokenServiceTest {

    @Mock
    private RefreshTokenMapper refreshTokenMapper;

    @Mock
    private UserAccountMapper userAccountMapper;

    @Mock
    private JwtAccessTokenService jwtAccessTokenService;

    private RefreshTokenGenerator tokenGenerator;

    private RefreshTokenHashService hashService;

    private RefreshTokenService refreshTokenService;

    @BeforeEach
    void setUp() {
        TableInfoHelper.initTableInfo(new MapperBuilderAssistant(new Configuration(), ""), RefreshToken.class);
        tokenGenerator = new RefreshTokenGenerator();
        hashService = new RefreshTokenHashService();
        refreshTokenService = new RefreshTokenServiceImpl(
            refreshTokenMapper,
            userAccountMapper,
            jwtAccessTokenService,
            tokenGenerator,
            hashService,
            new RefreshTokenProperties(2592000L)
        );
    }

    @Test
    void generateCreatesNonBlankUrlSafeRefreshToken() {
        String refreshToken = tokenGenerator.generate();

        assertThat(refreshToken).isNotBlank();
        assertThat(refreshToken).doesNotContain("+", "/", "=");
        assertThat(refreshToken.length()).isGreaterThanOrEqualTo(43);
    }

    @Test
    void hashIsStableAndDoesNotExposeRawToken() {
        String refreshToken = tokenGenerator.generate();

        String firstHash = hashService.sha256Hex(refreshToken);
        String secondHash = hashService.sha256Hex(refreshToken);

        assertThat(firstHash).isEqualTo(secondHash);
        assertThat(firstHash).isNotEqualTo(refreshToken);
        assertThat(firstHash).hasSize(64);
    }

    @Test
    void issueStoresOnlyHashWithNullRevokedAtAndExpiry() {
        UserAccount userAccount = activeUser();

        String refreshToken = refreshTokenService.issue(userAccount);

        ArgumentCaptor<RefreshToken> captor = ArgumentCaptor.forClass(RefreshToken.class);
        verify(refreshTokenMapper).insert(captor.capture());
        RefreshToken saved = captor.getValue();
        assertThat(refreshToken).isNotBlank();
        assertThat(saved.getUserId()).isEqualTo(1L);
        assertThat(saved.getTokenHash()).isEqualTo(hashService.sha256Hex(refreshToken));
        assertThat(saved.getTokenHash()).isNotEqualTo(refreshToken);
        assertThat(saved.getRevokedAt()).isNull();
        assertThat(saved.getExpiresAt()).isAfter(LocalDateTime.now().plusSeconds(2591000L));
    }

    @Test
    void refreshRevokesOldTokenCreatesNewTokenAndReturnsNewAccessToken() {
        UserAccount userAccount = activeUser();
        RefreshToken oldToken = activeRefreshToken(userAccount.getId(), "old-refresh-token");
        when(refreshTokenMapper.selectOne(anyRefreshTokenWrapper())).thenReturn(oldToken);
        when(userAccountMapper.selectById(userAccount.getId())).thenReturn(userAccount);
        when(jwtAccessTokenService.generate(userAccount)).thenReturn("new-access-token");
        when(jwtAccessTokenService.expiresIn()).thenReturn(3600L);

        LoginResponse response = refreshTokenService.refresh(new RefreshRequest("old-refresh-token"));

        ArgumentCaptor<RefreshToken> insertCaptor = ArgumentCaptor.forClass(RefreshToken.class);
        verify(refreshTokenMapper).updateById(oldToken);
        verify(refreshTokenMapper).insert(insertCaptor.capture());
        assertThat(oldToken.getRevokedAt()).isNotNull();
        assertThat(insertCaptor.getValue().getTokenHash()).isEqualTo(hashService.sha256Hex(response.refreshToken()));
        assertThat(insertCaptor.getValue().getTokenHash()).isNotEqualTo(response.refreshToken());
        assertThat(response.accessToken()).isEqualTo("new-access-token");
        assertThat(response.refreshToken()).isNotBlank();
        assertThat(response.tokenType()).isEqualTo("Bearer");
        assertThat(response.expiresIn()).isEqualTo(3600L);
        assertThat(response.user().email()).isEqualTo("demo@example.com");
    }

    @Test
    void repeatedUseOfRevokedRefreshTokenFails() {
        RefreshToken oldToken = activeRefreshToken(1L, "old-refresh-token");
        oldToken.setRevokedAt(LocalDateTime.now());
        when(refreshTokenMapper.selectOne(anyRefreshTokenWrapper())).thenReturn(oldToken);

        assertThatThrownBy(() -> refreshTokenService.refresh(new RefreshRequest("old-refresh-token")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_REFRESH_TOKEN_REVOKED);

        verify(refreshTokenMapper, never()).insert(any(RefreshToken.class));
    }

    @Test
    void refreshRejectsMissingToken() {
        when(refreshTokenMapper.selectOne(anyRefreshTokenWrapper())).thenReturn(null);

        assertThatThrownBy(() -> refreshTokenService.refresh(new RefreshRequest("missing-refresh-token")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_REFRESH_TOKEN_INVALID);
    }

    @Test
    void refreshRejectsExpiredToken() {
        RefreshToken oldToken = activeRefreshToken(1L, "old-refresh-token");
        oldToken.setExpiresAt(LocalDateTime.now().minusSeconds(1));
        when(refreshTokenMapper.selectOne(anyRefreshTokenWrapper())).thenReturn(oldToken);

        assertThatThrownBy(() -> refreshTokenService.refresh(new RefreshRequest("old-refresh-token")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_TOKEN_EXPIRED);
    }

    @Test
    void refreshRejectsDisabledUser() {
        UserAccount userAccount = activeUser();
        userAccount.setStatus("DISABLED");
        RefreshToken oldToken = activeRefreshToken(userAccount.getId(), "old-refresh-token");
        when(refreshTokenMapper.selectOne(anyRefreshTokenWrapper())).thenReturn(oldToken);
        when(userAccountMapper.selectById(userAccount.getId())).thenReturn(userAccount);

        assertThatThrownBy(() -> refreshTokenService.refresh(new RefreshRequest("old-refresh-token")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_USER_DISABLED);

        verify(refreshTokenMapper, never()).insert(any(RefreshToken.class));
    }

    @Test
    void refreshQueriesByTokenHash() {
        refreshTokenService.issue(activeUser());
        String rawToken = tokenGenerator.generate();
        when(refreshTokenMapper.selectOne(anyRefreshTokenWrapper())).thenReturn(null);

        assertThatThrownBy(() -> refreshTokenService.refresh(new RefreshRequest(rawToken)))
            .isInstanceOf(BusinessException.class);

        ArgumentCaptor<Wrapper<RefreshToken>> queryCaptor = ArgumentCaptor.forClass(Wrapper.class);
        verify(refreshTokenMapper).selectOne(queryCaptor.capture());
        Wrapper<RefreshToken> capturedQuery = queryCaptor.getValue();
        assertThat(capturedQuery.getSqlSegment()).contains("token_hash");
        assertThat(((AbstractWrapper<?, ?, ?>) capturedQuery).getParamNameValuePairs())
            .containsValue(hashService.sha256Hex(rawToken));
    }

    private RefreshToken activeRefreshToken(Long userId, String rawToken) {
        RefreshToken refreshToken = new RefreshToken();
        refreshToken.setId(10L);
        refreshToken.setUserId(userId);
        refreshToken.setTokenHash(hashService.sha256Hex(rawToken));
        refreshToken.setExpiresAt(LocalDateTime.now().plusDays(1));
        return refreshToken;
    }

    private UserAccount activeUser() {
        UserAccount userAccount = new UserAccount();
        userAccount.setId(1L);
        userAccount.setEmail("demo@example.com");
        userAccount.setStatus("ACTIVE");
        return userAccount;
    }

    private Wrapper<RefreshToken> anyRefreshTokenWrapper() {
        return any();
    }
}
