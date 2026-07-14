package com.example.courselingo.task.claim;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;

public class RedisTaskClaimService implements TaskClaimService {

    private static final Logger log = LoggerFactory.getLogger(RedisTaskClaimService.class);
    private static final String KEY_PREFIX = "cl:t:claim:";
    private static final RedisScript<Long> RELEASE_SCRIPT = RedisScript.of("""
        local value = redis.call('GET', KEYS[1])
        if not value then
          return 0
        end
        local ok, claim = pcall(cjson.decode, value)
        if ok and claim['requestId'] == ARGV[1] then
          return redis.call('DEL', KEYS[1])
        end
        return 0
        """, Long.class);
    private static final RedisScript<Long> REFRESH_SCRIPT = RedisScript.of("""
        local value = redis.call('GET', KEYS[1])
        if not value then
          return 0
        end
        local ok, claim = pcall(cjson.decode, value)
        if not ok or claim['requestId'] ~= ARGV[1] then
          return 0
        end
        claim['expiresAt'] = ARGV[2]
        redis.call('SET', KEYS[1], cjson.encode(claim), 'PX', ARGV[3])
        return 1
        """, Long.class);
    private static final Pattern SENSITIVE_WORDS = Pattern.compile(
        "(?i)access\\s*token|refresh\\s*token|api\\s*key|secret\\s*key|token|secret"
    );

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final RedisTaskClaimProperties properties;
    private final Clock clock;

    public RedisTaskClaimService(
        StringRedisTemplate redisTemplate,
        ObjectMapper objectMapper,
        RedisTaskClaimProperties properties,
        Clock clock
    ) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
        this.properties = properties;
        this.clock = clock;
    }

    @Override
    public TaskClaimResult tryAcquire(String taskId, String requestId) {
        try {
            Boolean acquired = redisTemplate.opsForValue()
                .setIfAbsent(key(taskId), toJson(newClaim(taskId, requestId)), properties.redisKeyTtl());
            return Boolean.TRUE.equals(acquired) ? TaskClaimResult.acquiredResult() : TaskClaimResult.rejectedResult();
        } catch (RuntimeException exception) {
            throw new BusinessException(
                ErrorCode.TASK_CLAIM_UNAVAILABLE,
                "Task claim is temporarily unavailable",
                exception
            );
        }
    }

    @Override
    public void release(String taskId, String requestId) {
        try {
            redisTemplate.execute(RELEASE_SCRIPT, List.of(key(taskId)), requestId);
        } catch (RuntimeException exception) {
            log.warn("Task claim release failed for taskId={}, reason={}", taskId, sanitize(exception.getMessage()));
        }
    }

    @Override
    public boolean refresh(String taskId, String requestId) {
        try {
            Instant expiresAt = clock.instant().plus(properties.redisKeyTtl());
            Long refreshed = redisTemplate.execute(
                REFRESH_SCRIPT,
                List.of(key(taskId)),
                requestId,
                expiresAt.toString(),
                String.valueOf(properties.redisKeyTtl().toMillis())
            );
            return Long.valueOf(1L).equals(refreshed);
        } catch (RuntimeException exception) {
            log.warn("Task claim refresh failed for taskId={}, reason={}", taskId, sanitize(exception.getMessage()));
            return false;
        }
    }

    private TaskClaim newClaim(String taskId, String requestId) {
        Instant claimedAt = clock.instant();
        return new TaskClaim(taskId, requestId, claimedAt, claimedAt.plus(properties.redisKeyTtl()));
    }

    private String key(String taskId) {
        return KEY_PREFIX + taskId;
    }

    private String toJson(TaskClaim claim) {
        try {
            return objectMapper.writeValueAsString(claim);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Task claim JSON serialization failed", exception);
        }
    }

    private String sanitize(String message) {
        if (message == null) {
            return null;
        }
        return SENSITIVE_WORDS.matcher(message).replaceAll("[redacted]");
    }
}
