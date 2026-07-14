package com.example.courselingo.upload.service;

import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;
import org.springframework.data.redis.core.StringRedisTemplate;

public class RedisUploadChunkStateService implements UploadChunkStateService {

    private static final String KEY_PREFIX = "cl:u:chunks:";

    private final StringRedisTemplate redisTemplate;
    private final UploadChunkStateProperties properties;

    public RedisUploadChunkStateService(
        StringRedisTemplate redisTemplate,
        UploadChunkStateProperties properties
    ) {
        this.redisTemplate = redisTemplate;
        this.properties = properties;
    }

    @Override
    public void markUploaded(String uploadId, int chunkIndex) {
        String key = key(uploadId);
        redisTemplate.opsForSet().add(key, String.valueOf(chunkIndex));
        redisTemplate.expire(key, properties.redisKeyTtl());
    }

    @Override
    public Optional<List<Integer>> findUploadedChunks(String uploadId, int totalChunks) {
        String key = key(uploadId);
        if (!Boolean.TRUE.equals(redisTemplate.hasKey(key))) {
            return Optional.empty();
        }
        Set<String> members = redisTemplate.opsForSet().members(key);
        if (members == null) {
            return Optional.of(List.of());
        }
        TreeSet<Integer> uploaded = new TreeSet<>();
        for (String member : members) {
            Integer chunkIndex = parseChunkIndex(member);
            if (chunkIndex != null && chunkIndex >= 0 && chunkIndex < totalChunks) {
                uploaded.add(chunkIndex);
            }
        }
        return Optional.of(List.copyOf(uploaded));
    }

    @Override
    public void clear(String uploadId) {
        redisTemplate.delete(key(uploadId));
    }

    private String key(String uploadId) {
        return KEY_PREFIX + uploadId;
    }

    private Integer parseChunkIndex(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return Integer.valueOf(value);
        } catch (NumberFormatException exception) {
            return null;
        }
    }
}
