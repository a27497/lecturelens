package com.example.courselingo.upload;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.upload.service.RedisUploadChunkStateService;
import com.example.courselingo.upload.service.UploadChunkStateProperties;
import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

class RedisUploadChunkStateServiceTest {

    @Mock
    private StringRedisTemplate redisTemplate;

    @Mock
    private SetOperations<String, String> setOperations;

    private RedisUploadChunkStateService service;

    @BeforeEach
    void setUp() {
        MockitoAnnotations.openMocks(this);
        service = new RedisUploadChunkStateService(
            redisTemplate,
            new UploadChunkStateProperties(86400)
        );
        when(redisTemplate.opsForSet()).thenReturn(setOperations);
    }

    @Test
    void markUploadedUsesFixedKeyAndSavesChunkIndexInRedisSetWithTtl() {
        service.markUploaded("up_abc123", 2);

        verify(setOperations).add("cl:u:chunks:up_abc123", "2");
        verify(redisTemplate).expire("cl:u:chunks:up_abc123", Duration.ofSeconds(86400));
    }

    @Test
    void findUploadedChunksReturnsEmptyWhenKeyDoesNotExist() {
        when(redisTemplate.hasKey("cl:u:chunks:up_abc123")).thenReturn(false);

        Optional<List<Integer>> uploaded = service.findUploadedChunks("up_abc123", 5);

        assertThat(uploaded).isEmpty();
    }

    @Test
    void findUploadedChunksFiltersInvalidValuesAndReturnsAscendingIndexes() {
        when(redisTemplate.hasKey("cl:u:chunks:up_abc123")).thenReturn(true);
        when(setOperations.members("cl:u:chunks:up_abc123"))
            .thenReturn(Set.of("2", "0", "abc", "-1", "5", "1"));

        Optional<List<Integer>> uploaded = service.findUploadedChunks("up_abc123", 5);

        assertThat(uploaded).hasValue(List.of(0, 1, 2));
    }

    @Test
    void clearDeletesFixedRedisKey() {
        service.clear("up_abc123");

        verify(redisTemplate).delete("cl:u:chunks:up_abc123");
    }
}
