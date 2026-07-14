package com.example.courselingo.infrastructure;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
@EnableConfigurationProperties(RedisProperties.class)
public class RedisConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "courselingo.redis", name = "enabled", havingValue = "true")
    LettuceConnectionFactory redisConnectionFactory(RedisProperties properties) {
        RedisStandaloneConfiguration configuration = new RedisStandaloneConfiguration(properties.host(), properties.port());
        configuration.setDatabase(properties.database());
        if (properties.password() != null && !properties.password().isBlank()) {
            configuration.setPassword(properties.password());
        }
        LettuceClientConfiguration clientConfiguration = LettuceClientConfiguration.builder()
            .commandTimeout(properties.timeoutMs())
            .build();
        return new LettuceConnectionFactory(configuration, clientConfiguration);
    }

    @Bean
    @ConditionalOnProperty(prefix = "courselingo.redis", name = "enabled", havingValue = "true")
    StringRedisTemplate stringRedisTemplate(LettuceConnectionFactory connectionFactory) {
        return new StringRedisTemplate(connectionFactory);
    }
}
