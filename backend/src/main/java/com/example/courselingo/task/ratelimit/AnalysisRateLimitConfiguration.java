package com.example.courselingo.task.ratelimit;

import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
@EnableConfigurationProperties(AnalysisRateLimitProperties.class)
public class AnalysisRateLimitConfiguration {

    @Configuration
    @ConditionalOnProperty(prefix = "courselingo.redis", name = "enabled", havingValue = "true")
    static class RedisEnabledConfiguration {

        @Bean
        @ConditionalOnProperty(
            prefix = "courselingo.task.rate-limit.analysis",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
        )
        RedisAnalysisRateLimitService redisAnalysisRateLimitService(
            StringRedisTemplate redisTemplate,
            AnalysisRateLimitProperties properties
        ) {
            return new RedisAnalysisRateLimitService(redisTemplate, properties);
        }
    }

    @Bean
    @ConditionalOnMissingBean(AnalysisRateLimitService.class)
    NoopAnalysisRateLimitService noopAnalysisRateLimitService() {
        return new NoopAnalysisRateLimitService();
    }
}
