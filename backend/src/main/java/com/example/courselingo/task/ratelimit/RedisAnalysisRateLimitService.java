package com.example.courselingo.task.ratelimit;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

public class RedisAnalysisRateLimitService implements AnalysisRateLimitService {

    private static final Logger log = LoggerFactory.getLogger(RedisAnalysisRateLimitService.class);
    private static final String KEY_PREFIX = "cl:rate:analysis:";
    private static final Pattern SENSITIVE_WORDS = Pattern.compile(
        "(?i)(access\\s*token|refresh\\s*token|api\\s*key|secret\\s*key|token|secret)(\\s*[:=]?\\s*\\S+)?"
    );

    private final StringRedisTemplate redisTemplate;
    private final AnalysisRateLimitProperties properties;

    public RedisAnalysisRateLimitService(
        StringRedisTemplate redisTemplate,
        AnalysisRateLimitProperties properties
    ) {
        this.redisTemplate = redisTemplate;
        this.properties = properties;
    }

    @Override
    public AnalysisRateLimitResult checkAndConsume(Long userId) {
        validateUserId(userId);
        String key = key(userId);
        try {
            Long count = redisTemplate.opsForValue().increment(key);
            if (count == null) {
                return failOpen();
            }
            if (count == 1L) {
                redisTemplate.expire(key, properties.window());
            }
            if (count > properties.maxRequests()) {
                return AnalysisRateLimitResult.blocked(properties.maxRequests(), retryAfterSeconds(key));
            }
            return AnalysisRateLimitResult.allowed(properties.maxRequests(), properties.maxRequests() - count.intValue());
        } catch (RuntimeException exception) {
            log.warn(
                "Analysis rate limit Redis operation failed; using fail-open strategy, reason={}",
                sanitize(exception.getMessage())
            );
            return failOpen();
        }
    }

    private void validateUserId(Long userId) {
        if (userId == null || userId <= 0) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Invalid userId");
        }
    }

    private long retryAfterSeconds(String key) {
        Long ttlSeconds = redisTemplate.getExpire(key, TimeUnit.SECONDS);
        if (ttlSeconds == null || ttlSeconds <= 0) {
            return properties.windowSeconds();
        }
        return ttlSeconds;
    }

    private AnalysisRateLimitResult failOpen() {
        return AnalysisRateLimitResult.allowed(properties.maxRequests(), properties.maxRequests());
    }

    private String key(Long userId) {
        return KEY_PREFIX + userId;
    }

    private String sanitize(String message) {
        if (message == null) {
            return null;
        }
        return SENSITIVE_WORDS.matcher(message).replaceAll("[redacted]");
    }
}
