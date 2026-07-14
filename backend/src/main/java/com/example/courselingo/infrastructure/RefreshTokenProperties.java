package com.example.courselingo.infrastructure;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.security.jwt")
public record RefreshTokenProperties(
    long refreshExpireSeconds
) {
}
