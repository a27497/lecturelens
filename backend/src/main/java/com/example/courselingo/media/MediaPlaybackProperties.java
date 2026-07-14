package com.example.courselingo.media;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.media.playback")
public record MediaPlaybackProperties(
    long tokenTtlMinutes
) {
}
