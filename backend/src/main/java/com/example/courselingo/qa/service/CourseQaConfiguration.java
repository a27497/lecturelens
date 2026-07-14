package com.example.courselingo.qa.service;

import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
@EnableConfigurationProperties(CourseQaProperties.class)
public class CourseQaConfiguration {

    @Configuration
    @ConditionalOnProperty(prefix = "courselingo.redis", name = "enabled", havingValue = "true")
    static class RedisEnabledConfiguration {

        @Bean
        @ConditionalOnProperty(prefix = "courselingo.qa", name = "rate-limit-enabled", havingValue = "true", matchIfMissing = true)
        RedisCourseQaRateLimitService redisCourseQaRateLimitService(
            StringRedisTemplate redisTemplate,
            CourseQaProperties properties
        ) {
            return new RedisCourseQaRateLimitService(redisTemplate, properties);
        }
    }

    @Bean
    @ConditionalOnMissingBean(CourseQaRateLimitService.class)
    NoopCourseQaRateLimitService noopCourseQaRateLimitService() {
        return new NoopCourseQaRateLimitService();
    }
}
