package com.example.courselingo.media;

import java.time.Instant;

public record MediaPlaybackToken(String token, Instant expiresAt) {
}
