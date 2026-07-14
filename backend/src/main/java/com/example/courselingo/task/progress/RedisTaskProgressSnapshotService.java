package com.example.courselingo.task.progress;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Optional;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

public class RedisTaskProgressSnapshotService implements TaskProgressSnapshotService {

    private static final Logger log = LoggerFactory.getLogger(RedisTaskProgressSnapshotService.class);
    private static final String KEY_PREFIX = "cl:t:progress:";
    private static final int ERROR_MESSAGE_LIMIT = 1024;
    private static final Pattern SENSITIVE_WORDS = Pattern.compile(
        "(?i)access\\s*token|refresh\\s*token|api\\s*key|secret\\s*key|token|secret"
    );
    private static final Pattern WINDOWS_PATH = Pattern.compile("[A-Za-z]:\\\\\\S*");
    private static final Pattern UNIX_HOME_PATH = Pattern.compile("/(?:home|Users)/\\S*");

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final TaskProgressProperties properties;

    public RedisTaskProgressSnapshotService(
        StringRedisTemplate redisTemplate,
        ObjectMapper objectMapper,
        TaskProgressProperties properties
    ) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    @Override
    public void save(TaskProgressSnapshot snapshot) {
        try {
            redisTemplate.opsForValue().set(key(snapshot.taskId()), toJson(sanitize(snapshot)), properties.redisKeyTtl());
        } catch (RuntimeException exception) {
            log.warn("Task progress snapshot write failed for taskId={}", snapshot == null ? null : snapshot.taskId(), exception);
        }
    }

    @Override
    public Optional<TaskProgressSnapshot> find(String taskId) {
        try {
            String json = redisTemplate.opsForValue().get(key(taskId));
            if (json == null || json.isBlank()) {
                return Optional.empty();
            }
            return Optional.of(objectMapper.readValue(json, TaskProgressSnapshot.class));
        } catch (RuntimeException | JsonProcessingException exception) {
            log.warn("Task progress snapshot read failed for taskId={}", taskId, exception);
            return Optional.empty();
        }
    }

    @Override
    public void delete(String taskId) {
        try {
            redisTemplate.delete(key(taskId));
        } catch (RuntimeException exception) {
            log.warn("Task progress snapshot delete failed for taskId={}", taskId, exception);
        }
    }

    private String key(String taskId) {
        return KEY_PREFIX + taskId;
    }

    private TaskProgressSnapshot sanitize(TaskProgressSnapshot snapshot) {
        return new TaskProgressSnapshot(
            snapshot.taskId(),
                snapshot.status(),
                snapshot.progressPercent(),
                snapshot.currentStage(),
                sanitizeAndLimit(snapshot.errorCode(), 64),
                sanitizeAndLimit(snapshot.errorMessage(), ERROR_MESSAGE_LIMIT),
                snapshot.updatedAt(),
                snapshot.completedChunks(),
                snapshot.totalChunks(),
                snapshot.currentChunkIndex(),
                sanitizeAndLimit(snapshot.stepDetail(), 255)
            );
    }

    private String toJson(TaskProgressSnapshot snapshot) {
        try {
            return objectMapper.writeValueAsString(snapshot);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Task progress snapshot JSON serialization failed", exception);
        }
    }

    private String sanitizeAndLimit(String value, int limit) {
        if (value == null) {
            return null;
        }
        String sanitized = SENSITIVE_WORDS.matcher(value).replaceAll("[redacted]");
        sanitized = WINDOWS_PATH.matcher(sanitized).replaceAll("[path]");
        sanitized = UNIX_HOME_PATH.matcher(sanitized).replaceAll("[path]");
        return limit(sanitized, limit);
    }

    private String limit(String value, int limit) {
        if (value == null || value.length() <= limit) {
            return value;
        }
        return value.substring(0, limit);
    }
}
