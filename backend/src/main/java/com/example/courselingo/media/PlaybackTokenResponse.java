package com.example.courselingo.media;

import java.time.Instant;

public record PlaybackTokenResponse(String token, Instant expiresAt, String playbackUrl) {
}
