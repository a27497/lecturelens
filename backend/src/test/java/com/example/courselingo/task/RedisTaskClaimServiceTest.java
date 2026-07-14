package com.example.courselingo.task;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.claim.RedisTaskClaimProperties;
import com.example.courselingo.task.claim.RedisTaskClaimService;
import com.example.courselingo.task.claim.TaskClaimResult;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.data.redis.core.script.RedisScript;

class RedisTaskClaimServiceTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(
        Instant.parse("2026-06-27T10:00:00Z"),
        ZoneOffset.UTC
    );

    @Mock
    private StringRedisTemplate redisTemplate;

    @Mock
    private ValueOperations<String, String> valueOperations;

    private ObjectMapper objectMapper;
    private RedisTaskClaimService service;

    @BeforeEach
    void setUp() {
        MockitoAnnotations.openMocks(this);
        objectMapper = JsonMapper.builder()
            .findAndAddModules()
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();
        service = new RedisTaskClaimService(
            redisTemplate,
            objectMapper,
            new RedisTaskClaimProperties(900),
            FIXED_CLOCK
        );
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
    }

    @Test
    void acquireUsesFixedKeyJsonNxAndTtl() throws Exception {
        when(valueOperations.setIfAbsent(
            eq("cl:t:claim:task_abc123"),
            any(String.class),
            eq(Duration.ofSeconds(900))
        )).thenReturn(true);

        TaskClaimResult result = service.tryAcquire("task_abc123", "req_abc123");

        assertThat(result.acquired()).isTrue();
        ArgumentCaptor<String> jsonCaptor = ArgumentCaptor.forClass(String.class);
        verify(valueOperations).setIfAbsent(
            eq("cl:t:claim:task_abc123"),
            jsonCaptor.capture(),
            eq(Duration.ofSeconds(900))
        );
        JsonNode json = objectMapper.readTree(jsonCaptor.getValue());
        assertThat(json.get("taskId").asText()).isEqualTo("task_abc123");
        assertThat(json.get("requestId").asText()).isEqualTo("req_abc123");
        assertThat(json.get("claimedAt").asText()).isEqualTo("2026-06-27T10:00:00Z");
        assertThat(json.get("expiresAt").asText()).isEqualTo("2026-06-27T10:15:00Z");
        assertThat(json.has("userId")).isFalse();
        assertThat(json.toString()).doesNotContain("objectKey");
        assertThat(json.toString()).doesNotContain("localPath");
        assertThat(json.toString()).doesNotContain("token");
        assertThat(json.toString()).doesNotContain("secret");
        assertThat(json.toString()).doesNotContain("api key");
    }

    @Test
    void acquireReturnsRejectedWhenClaimExists() {
        when(valueOperations.setIfAbsent(
            eq("cl:t:claim:task_abc123"),
            any(String.class),
            eq(Duration.ofSeconds(900))
        )).thenReturn(false);

        TaskClaimResult result = service.tryAcquire("task_abc123", "req_abc123");

        assertThat(result.acquired()).isFalse();
    }

    @Test
    void acquireConvertsRedisFailureToProjectException() {
        when(valueOperations.setIfAbsent(
            eq("cl:t:claim:task_abc123"),
            any(String.class),
            eq(Duration.ofSeconds(900))
        )).thenThrow(new IllegalStateException("redis unavailable secret raw-secret"));

        assertThatThrownBy(() -> service.tryAcquire("task_abc123", "req_abc123"))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                BusinessException exception = (BusinessException) error;
                assertThat(exception.errorCode()).isEqualTo(ErrorCode.TASK_CLAIM_UNAVAILABLE);
                assertThat(exception.getMessage()).doesNotContainIgnoringCase("secret");
            });
    }

    @Test
    @SuppressWarnings("unchecked")
    void releaseDeletesOnlyWhenRequestIdMatches() {
        when(redisTemplate.execute(any(RedisScript.class), anyList(), eq("req_abc123"))).thenReturn(1L);

        service.release("task_abc123", "req_abc123");

        ArgumentCaptor<List<String>> keysCaptor = ArgumentCaptor.forClass(List.class);
        verify(redisTemplate).execute(any(RedisScript.class), keysCaptor.capture(), eq("req_abc123"));
        assertThat(keysCaptor.getValue()).containsExactly("cl:t:claim:task_abc123");
    }

    @Test
    @SuppressWarnings("unchecked")
    void releaseIgnoresMismatchedRequestIdAndRedisFailure() {
        when(redisTemplate.execute(any(RedisScript.class), anyList(), eq("other_req"))).thenReturn(0L);
        service.release("task_abc123", "other_req");

        doThrow(new IllegalStateException("redis unavailable secret raw-secret"))
            .when(redisTemplate).execute(any(RedisScript.class), anyList(), eq("req_abc123"));
        service.release("task_abc123", "req_abc123");
    }

    @Test
    @SuppressWarnings("unchecked")
    void refreshExtendsOnlyMatchingRequestIdAndUpdatesExpiresAt() {
        when(redisTemplate.execute(
            any(RedisScript.class),
            anyList(),
            eq("req_abc123"),
            eq("2026-06-27T10:15:00Z"),
            eq("900000")
        )).thenReturn(1L);

        boolean refreshed = service.refresh("task_abc123", "req_abc123");

        assertThat(refreshed).isTrue();
        ArgumentCaptor<List<String>> keysCaptor = ArgumentCaptor.forClass(List.class);
        verify(redisTemplate).execute(
            any(RedisScript.class),
            keysCaptor.capture(),
            eq("req_abc123"),
            eq("2026-06-27T10:15:00Z"),
            eq("900000")
        );
        assertThat(keysCaptor.getValue()).containsExactly("cl:t:claim:task_abc123");
    }

    @Test
    @SuppressWarnings("unchecked")
    void refreshReturnsFalseForMismatchedRequestIdOrRedisFailure() {
        when(redisTemplate.execute(
            any(RedisScript.class),
            anyList(),
            eq("other_req"),
            eq("2026-06-27T10:15:00Z"),
            eq("900000")
        )).thenReturn(0L);

        assertThat(service.refresh("task_abc123", "other_req")).isFalse();

        doThrow(new IllegalStateException("redis unavailable secret raw-secret"))
            .when(redisTemplate).execute(
                any(RedisScript.class),
                anyList(),
                eq("req_abc123"),
                eq("2026-06-27T10:15:00Z"),
                eq("900000")
            );
        assertThat(service.refresh("task_abc123", "req_abc123")).isFalse();
    }
}
