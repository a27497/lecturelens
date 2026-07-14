package com.example.courselingo.infrastructure;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties({JwtAccessTokenProperties.class, RefreshTokenProperties.class})
public class JwtAccessTokenConfig {
}
