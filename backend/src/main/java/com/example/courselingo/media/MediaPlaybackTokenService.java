package com.example.courselingo.media;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.infrastructure.JwtAccessTokenProperties;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class MediaPlaybackTokenService {

    private static final String HMAC_ALGORITHM = "HmacSHA256";

    private final MediaPlaybackProperties properties;
    private final JwtAccessTokenProperties jwtProperties;
    private final Clock clock;

    @Autowired
    public MediaPlaybackTokenService(MediaPlaybackProperties properties, JwtAccessTokenProperties jwtProperties) {
        this(properties, jwtProperties, Clock.systemUTC());
    }

    public MediaPlaybackTokenService(
        MediaPlaybackProperties properties,
        JwtAccessTokenProperties jwtProperties,
        Clock clock
    ) {
        this.properties = properties;
        this.jwtProperties = jwtProperties;
        this.clock = clock;
    }

    public MediaPlaybackToken issue(Long userId, String uploadId) {
        validateIssueInput(userId, uploadId);
        Instant expiresAt = clock.instant().plusSeconds(ttlSeconds());
        String payload = userId + ":" + uploadId + ":" + expiresAt.getEpochSecond();
        String encodedPayload = encode(payload.getBytes(StandardCharsets.UTF_8));
        String encodedSignature = encode(sign(encodedPayload));
        return new MediaPlaybackToken(encodedPayload + "." + encodedSignature, expiresAt);
    }

    public MediaPlaybackTokenClaims verify(String token) {
        if (token == null || token.isBlank()) {
            throw new BusinessException(ErrorCode.MEDIA_PLAYBACK_TOKEN_INVALID);
        }
        String[] parts = token.split("\\.", -1);
        if (parts.length != 2 || parts[0].isBlank() || parts[1].isBlank()) {
            throw new BusinessException(ErrorCode.MEDIA_PLAYBACK_TOKEN_INVALID);
        }
        byte[] expectedSignature = sign(parts[0]);
        byte[] actualSignature = decode(parts[1]);
        if (!MessageDigest.isEqual(expectedSignature, actualSignature)) {
            throw new BusinessException(ErrorCode.MEDIA_PLAYBACK_TOKEN_INVALID);
        }
        String payload = new String(decode(parts[0]), StandardCharsets.UTF_8);
        String[] payloadParts = payload.split(":", -1);
        if (payloadParts.length != 3) {
            throw new BusinessException(ErrorCode.MEDIA_PLAYBACK_TOKEN_INVALID);
        }
        try {
            Long userId = Long.valueOf(payloadParts[0]);
            String uploadId = payloadParts[1];
            Instant expiresAt = Instant.ofEpochSecond(Long.parseLong(payloadParts[2]));
            if (!expiresAt.isAfter(clock.instant())) {
                throw new BusinessException(ErrorCode.MEDIA_PLAYBACK_TOKEN_EXPIRED);
            }
            return new MediaPlaybackTokenClaims(userId, uploadId, expiresAt);
        } catch (BusinessException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new BusinessException(ErrorCode.MEDIA_PLAYBACK_TOKEN_INVALID);
        }
    }

    private long ttlSeconds() {
        long minutes = properties == null ? 15L : properties.tokenTtlMinutes();
        return Math.max(minutes, 1L) * 60L;
    }

    private void validateIssueInput(Long userId, String uploadId) {
        if (userId == null || uploadId == null || uploadId.isBlank()) {
            throw new BusinessException(ErrorCode.MEDIA_PLAYBACK_TOKEN_INVALID);
        }
    }

    private byte[] sign(String encodedPayload) {
        try {
            Mac mac = Mac.getInstance(HMAC_ALGORITHM);
            mac.init(new SecretKeySpec(signingSecret(), HMAC_ALGORITHM));
            return mac.doFinal(encodedPayload.getBytes(StandardCharsets.UTF_8));
        } catch (Exception exception) {
            throw new BusinessException(ErrorCode.MEDIA_PLAYBACK_TOKEN_INVALID, exception);
        }
    }

    private byte[] signingSecret() {
        String secret = jwtProperties == null ? null : jwtProperties.accessSecret();
        if (secret == null || secret.isBlank()) {
            throw new BusinessException(ErrorCode.MEDIA_PLAYBACK_TOKEN_INVALID);
        }
        return ("courselingo-media-playback:" + secret).getBytes(StandardCharsets.UTF_8);
    }

    private static String encode(byte[] value) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value);
    }

    private static byte[] decode(String value) {
        try {
            return Base64.getUrlDecoder().decode(value);
        } catch (IllegalArgumentException exception) {
            throw new BusinessException(ErrorCode.MEDIA_PLAYBACK_TOKEN_INVALID);
        }
    }
}
