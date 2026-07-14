package com.example.courselingo.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.auth.entity.UserAccount;
import com.example.courselingo.auth.service.AccessTokenClaims;
import com.example.courselingo.auth.service.JwtAccessTokenService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.infrastructure.JwtAccessTokenProperties;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import javax.crypto.SecretKey;
import org.junit.jupiter.api.Test;

class JwtAccessTokenServiceTest {

    private static final String SECRET = "test-access-secret-at-least-32-characters";

    @Test
    void generateCreatesAccessTokenWithExpectedClaims() {
        JwtAccessTokenProperties properties = new JwtAccessTokenProperties(SECRET, 3600L);
        JwtAccessTokenService service = new JwtAccessTokenService(properties);
        UserAccount userAccount = activeUser();

        String token = service.generate(userAccount);

        Claims claims = parseClaims(token);
        assertThat(token).isNotBlank();
        assertThat(service.expiresIn()).isEqualTo(3600L);
        assertThat(claims.getSubject()).isEqualTo("1");
        assertThat(claims.get("email", String.class)).isEqualTo("demo@example.com");
        assertThat(claims.get("status", String.class)).isEqualTo("ACTIVE");
        assertThat(claims.get("type", String.class)).isEqualTo("access");
        assertThat(claims.getIssuedAt()).isNotNull();
        assertThat(claims.getExpiration()).isAfter(claims.getIssuedAt());
        assertThat(token).doesNotContain(SECRET);
    }

    @Test
    void parseValidAccessTokenReturnsUserId() {
        JwtAccessTokenService service = new JwtAccessTokenService(new JwtAccessTokenProperties(SECRET, 3600L));
        String token = service.generate(activeUser());

        AccessTokenClaims claims = service.parseAccessToken(token);

        assertThat(claims.userId()).isEqualTo(1L);
    }

    @Test
    void parseExpiredAccessTokenThrowsTokenExpired() {
        JwtAccessTokenService service = new JwtAccessTokenService(new JwtAccessTokenProperties(SECRET, 3600L));
        String token = buildToken("1", "access", Instant.now().minusSeconds(120), Instant.now().minusSeconds(60));

        assertThatThrownBy(() -> service.parseAccessToken(token))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_TOKEN_EXPIRED);
    }

    @Test
    void parseInvalidTokenThrowsTokenInvalid() {
        JwtAccessTokenService service = new JwtAccessTokenService(new JwtAccessTokenProperties(SECRET, 3600L));

        assertThatThrownBy(() -> service.parseAccessToken("not-a-jwt"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_TOKEN_INVALID);
    }

    @Test
    void parseNonAccessTokenThrowsTokenInvalid() {
        JwtAccessTokenService service = new JwtAccessTokenService(new JwtAccessTokenProperties(SECRET, 3600L));
        String token = buildToken("1", "refresh", Instant.now(), Instant.now().plusSeconds(3600));

        assertThatThrownBy(() -> service.parseAccessToken(token))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_TOKEN_INVALID);
    }

    private Claims parseClaims(String token) {
        SecretKey key = Keys.hmacShaKeyFor(SECRET.getBytes(StandardCharsets.UTF_8));
        return Jwts.parser()
            .verifyWith(key)
            .build()
            .parseSignedClaims(token)
            .getPayload();
    }

    private String buildToken(String subject, String type, Instant issuedAt, Instant expiration) {
        return Jwts.builder()
            .subject(subject)
            .claim("type", type)
            .issuedAt(Date.from(issuedAt))
            .expiration(Date.from(expiration))
            .signWith(Keys.hmacShaKeyFor(SECRET.getBytes(StandardCharsets.UTF_8)))
            .compact();
    }

    private UserAccount activeUser() {
        UserAccount userAccount = new UserAccount();
        userAccount.setId(1L);
        userAccount.setEmail("demo@example.com");
        userAccount.setStatus("ACTIVE");
        return userAccount;
    }
}
