package com.example.courselingo.media;

import java.time.Instant;

public record MediaPlaybackTokenClaims(Long userId, String uploadId, Instant expiresAt) {
}
