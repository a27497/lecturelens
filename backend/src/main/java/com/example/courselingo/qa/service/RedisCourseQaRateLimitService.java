package com.example.courselingo.qa.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

public class RedisCourseQaRateLimitService implements CourseQaRateLimitService {

    private static final Logger log = LoggerFactory.getLogger(RedisCourseQaRateLimitService.class);
    private static final String KEY_PREFIX = "cl:rate:qa:";

    private final StringRedisTemplate redisTemplate;
    private final CourseQaProperties properties;

    public RedisCourseQaRateLimitService(StringRedisTemplate redisTemplate, CourseQaProperties properties) {
        this.redisTemplate = redisTemplate;
        this.properties = properties == null ? new CourseQaProperties() : properties;
    }

    @Override
    public CourseQaRateLimitResult checkAndConsume(Long userId) {
        if (userId == null || userId <= 0) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Invalid userId");
        }
        String key = KEY_PREFIX + userId;
        try {
            Long count = redisTemplate.opsForValue().increment(key);
            if (count == null) {
                return failOpen();
            }
            if (count == 1L) {
                redisTemplate.expire(key, Duration.ofMinutes(1));
            }
            if (count > properties.getRateLimitPerMinute()) {
                Long ttl = redisTemplate.getExpire(key, TimeUnit.SECONDS);
                return CourseQaRateLimitResult.blocked(
                    properties.getRateLimitPerMinute(),
                    ttl == null || ttl <= 0 ? 60 : ttl
                );
            }
            return CourseQaRateLimitResult.allowed(
                properties.getRateLimitPerMinute(),
                properties.getRateLimitPerMinute() - count.intValue()
            );
        } catch (RuntimeException exception) {
            log.warn("QA rate limit Redis operation failed; using fail-open strategy, reason={}", safe(exception.getMessage()));
            return failOpen();
        }
    }

    private CourseQaRateLimitResult failOpen() {
        return CourseQaRateLimitResult.allowed(properties.getRateLimitPerMinute(), properties.getRateLimitPerMinute());
    }

    private static String safe(String message) {
        if (message == null) {
            return "";
        }
        return message.replaceAll("(?i)(token|secret|api\\s*key|password)\\s*[:=]?\\s*\\S+", "[redacted]");
    }
}
