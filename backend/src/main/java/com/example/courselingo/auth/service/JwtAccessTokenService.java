package com.example.courselingo.auth.service;

import com.example.courselingo.auth.entity.UserAccount;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.infrastructure.JwtAccessTokenProperties;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.ExpiredJwtException;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import javax.crypto.SecretKey;
import org.springframework.stereotype.Service;

@Service
public class JwtAccessTokenService {

    private static final String ACCESS_TOKEN_TYPE = "access";

    private final JwtAccessTokenProperties properties;

    public JwtAccessTokenService(JwtAccessTokenProperties properties) {
        this.properties = properties;
    }

    public String generate(UserAccount userAccount) {
        try {
            Instant issuedAt = Instant.now();
            Instant expiresAt = issuedAt.plusSeconds(properties.accessExpireSeconds());
            return Jwts.builder()
                .subject(String.valueOf(userAccount.getId()))
                .claim("email", userAccount.getEmail())
                .claim("status", userAccount.getStatus())
                .claim("type", ACCESS_TOKEN_TYPE)
                .issuedAt(Date.from(issuedAt))
                .expiration(Date.from(expiresAt))
                .signWith(signingKey())
                .compact();
        } catch (RuntimeException exception) {
            throw new BusinessException(ErrorCode.AUTH_TOKEN_SIGN_FAILED, exception);
        }
    }

    public AccessTokenClaims parseAccessToken(String token) {
        try {
            Claims claims = Jwts.parser()
                .verifyWith(signingKey())
                .build()
                .parseSignedClaims(token)
                .getPayload();
            if (!ACCESS_TOKEN_TYPE.equals(claims.get("type", String.class))) {
                throw new BusinessException(ErrorCode.AUTH_TOKEN_INVALID);
            }
            return new AccessTokenClaims(parseUserId(claims.getSubject()));
        } catch (ExpiredJwtException exception) {
            throw new BusinessException(ErrorCode.AUTH_TOKEN_EXPIRED);
        } catch (BusinessException exception) {
            throw exception;
        } catch (JwtException | IllegalArgumentException exception) {
            throw new BusinessException(ErrorCode.AUTH_TOKEN_INVALID);
        }
    }

    public long expiresIn() {
        return properties.accessExpireSeconds();
    }

    private SecretKey signingKey() {
        return Keys.hmacShaKeyFor(properties.accessSecret().getBytes(StandardCharsets.UTF_8));
    }

    private Long parseUserId(String subject) {
        try {
            return Long.valueOf(subject);
        } catch (NumberFormatException exception) {
            throw new BusinessException(ErrorCode.AUTH_TOKEN_INVALID);
        }
    }
}
