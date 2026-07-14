package com.example.courselingo.task;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.ratelimit.AnalysisRateLimitProperties;
import com.example.courselingo.task.ratelimit.AnalysisRateLimitResult;
import com.example.courselingo.task.ratelimit.NoopAnalysisRateLimitService;
import com.example.courselingo.task.ratelimit.RedisAnalysisRateLimitService;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

class RedisAnalysisRateLimitServiceTest {

    @Mock
    private StringRedisTemplate redisTemplate;

    @Mock
    private ValueOperations<String, String> valueOperations;

    private RedisAnalysisRateLimitService service;

    @BeforeEach
    void setUp() {
        MockitoAnnotations.openMocks(this);
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
        service = new RedisAnalysisRateLimitService(
            redisTemplate,
            new AnalysisRateLimitProperties(true, 3, 60)
        );
    }

    @Test
    void firstRequestUsesFixedKeyIncrementsSetsTtlAndReturnsAllowed() {
        when(valueOperations.increment("cl:rate:analysis:7")).thenReturn(1L);

        AnalysisRateLimitResult result = service.checkAndConsume(7L);

        assertThat(result.allowed()).isTrue();
        assertThat(result.limit()).isEqualTo(3);
        assertThat(result.remaining()).isEqualTo(2);
        assertThat(result.retryAfterSeconds()).isZero();
        assertThat(result.toString()).doesNotContain("cl:rate:analysis");
        assertThat(result.toString()).doesNotContain("userId");
        verify(valueOperations).increment("cl:rate:analysis:7");
        verify(redisTemplate).expire("cl:rate:analysis:7", Duration.ofSeconds(60));
    }

    @Test
    void existingWindowDoesNotResetTtlWhenAllowed() {
        when(valueOperations.increment("cl:rate:analysis:7")).thenReturn(2L);

        AnalysisRateLimitResult result = service.checkAndConsume(7L);

        assertThat(result.allowed()).isTrue();
        assertThat(result.remaining()).isEqualTo(1);
        verify(redisTemplate, never()).expire(eq("cl:rate:analysis:7"), eq(Duration.ofSeconds(60)));
    }

    @Test
    void blocksWhenCountExceedsLimitAndReturnsRetryAfter() {
        when(valueOperations.increment("cl:rate:analysis:7")).thenReturn(4L);
        when(redisTemplate.getExpire("cl:rate:analysis:7", TimeUnit.SECONDS)).thenReturn(42L);

        AnalysisRateLimitResult result = service.checkAndConsume(7L);

        assertThat(result.allowed()).isFalse();
        assertThat(result.limit()).isEqualTo(3);
        assertThat(result.remaining()).isZero();
        assertThat(result.retryAfterSeconds()).isEqualTo(42);
    }

    @Test
    void usesWindowSecondsAsRetryAfterWhenRedisTtlIsUnavailable() {
        when(valueOperations.increment("cl:rate:analysis:7")).thenReturn(4L);
        when(redisTemplate.getExpire("cl:rate:analysis:7", TimeUnit.SECONDS)).thenReturn(-1L);

        AnalysisRateLimitResult result = service.checkAndConsume(7L);

        assertThat(result.allowed()).isFalse();
        assertThat(result.retryAfterSeconds()).isEqualTo(60);
    }

    @Test
    void rejectsInvalidUserId() {
        assertThatThrownBy(() -> service.checkAndConsume(null))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);

        assertThatThrownBy(() -> service.checkAndConsume(0L))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
    }

    @Test
    void validatesConfigurationValues() {
        assertThatThrownBy(() -> new AnalysisRateLimitProperties(true, 0, 60))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AnalysisRateLimitProperties(true, 10, 0))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void redisFailureFailsOpenWithoutLeakingSensitiveMessage() {
        when(valueOperations.increment("cl:rate:analysis:7"))
            .thenThrow(new IllegalStateException("redis unavailable secret raw-secret api key raw-key"));

        AnalysisRateLimitResult result = service.checkAndConsume(7L);

        assertThat(result.allowed()).isTrue();
        assertThat(result.limit()).isEqualTo(3);
        assertThat(result.remaining()).isEqualTo(3);
        assertThat(result.retryAfterSeconds()).isZero();
        assertThat(result.toString()).doesNotContainIgnoringCase("secret");
        assertThat(result.toString()).doesNotContainIgnoringCase("api key");
    }

    @Test
    void ttlFailureAlsoFailsOpen() {
        when(valueOperations.increment("cl:rate:analysis:7")).thenReturn(1L);
        doThrow(new IllegalStateException("redis unavailable"))
            .when(redisTemplate).expire("cl:rate:analysis:7", Duration.ofSeconds(60));

        AnalysisRateLimitResult result = service.checkAndConsume(7L);

        assertThat(result.allowed()).isTrue();
        assertThat(result.remaining()).isEqualTo(3);
    }

    @Test
    void noopImplementationAlwaysAllowsWithoutRedisKeyOrUserId() {
        AnalysisRateLimitResult result = new NoopAnalysisRateLimitService().checkAndConsume(7L);

        assertThat(result.allowed()).isTrue();
        assertThat(result.limit()).isZero();
        assertThat(result.remaining()).isZero();
        assertThat(result.retryAfterSeconds()).isZero();
        assertThat(result.toString()).doesNotContain("cl:rate:analysis");
        assertThat(result.toString()).doesNotContain("userId");
    }
}
