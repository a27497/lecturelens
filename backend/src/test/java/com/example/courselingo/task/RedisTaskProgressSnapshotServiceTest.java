package com.example.courselingo.task;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.task.progress.RedisTaskProgressSnapshotService;
import com.example.courselingo.task.progress.TaskProgressProperties;
import com.example.courselingo.task.progress.TaskProgressSnapshot;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

class RedisTaskProgressSnapshotServiceTest {

    private static final Instant UPDATED_AT = Instant.parse("2026-06-27T10:00:00Z");

    @Mock
    private StringRedisTemplate redisTemplate;

    @Mock
    private ValueOperations<String, String> valueOperations;

    private RedisTaskProgressSnapshotService service;
    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() {
        MockitoAnnotations.openMocks(this);
        objectMapper = JsonMapper.builder()
            .findAndAddModules()
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();
        service = new RedisTaskProgressSnapshotService(
            redisTemplate,
            objectMapper,
            new TaskProgressProperties(86400)
        );
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
    }

    @Test
    void saveWritesJsonToFixedKeyAndSetsTtl() throws Exception {
        TaskProgressSnapshot snapshot = snapshot("RUNNING", 35, "ASR", null, null);

        service.save(snapshot);

        ArgumentCaptor<String> jsonCaptor = ArgumentCaptor.forClass(String.class);
        verify(valueOperations).set(eq("cl:t:progress:task_abc123"), jsonCaptor.capture(), eq(Duration.ofSeconds(86400)));
        JsonNode json = objectMapper.readTree(jsonCaptor.getValue());
        assertThat(json.get("taskId").asText()).isEqualTo("task_abc123");
        assertThat(json.get("status").asText()).isEqualTo("RUNNING");
        assertThat(json.get("progressPercent").asInt()).isEqualTo(35);
        assertThat(json.get("currentStage").asText()).isEqualTo("ASR");
        assertThat(json.get("updatedAt").asText()).isEqualTo("2026-06-27T10:00:00Z");
        assertThat(json.has("errorCode")).isTrue();
        assertThat(json.get("errorCode").isNull()).isTrue();
        assertThat(json.has("errorMessage")).isTrue();
        assertThat(json.get("errorMessage").isNull()).isTrue();
        assertThat(json.has("userId")).isFalse();
        assertThat(json.toString()).doesNotContain("objectKey");
        assertThat(json.toString()).doesNotContain("C:\\");
        assertThat(json.toString()).doesNotContain("token");
        assertThat(json.toString()).doesNotContain("secret");
        assertThat(json.toString()).doesNotContain("api key");
    }

    @Test
    void saveSanitizesAndLimitsErrorMessage() throws Exception {
        String longMessage = "access token abc secret key xyz api key pqr C:\\Users\\demo\\video.mp4 /home/demo/file "
            + "x".repeat(1200);
        TaskProgressSnapshot snapshot = snapshot("FAILED", 30, "FAILED", "api key failed", longMessage);

        service.save(snapshot);

        ArgumentCaptor<String> jsonCaptor = ArgumentCaptor.forClass(String.class);
        verify(valueOperations).set(eq("cl:t:progress:task_abc123"), jsonCaptor.capture(), eq(Duration.ofSeconds(86400)));
        JsonNode json = objectMapper.readTree(jsonCaptor.getValue());
        String errorCode = json.get("errorCode").asText();
        String errorMessage = json.get("errorMessage").asText();
        assertThat(errorCode).doesNotContainIgnoringCase("api key");
        assertThat(errorMessage).doesNotContainIgnoringCase("token");
        assertThat(errorMessage).doesNotContainIgnoringCase("secret");
        assertThat(errorMessage).doesNotContainIgnoringCase("api key");
        assertThat(errorMessage).doesNotContain("C:\\");
        assertThat(errorMessage).doesNotContain("/home/");
        assertThat(errorMessage.length()).isLessThanOrEqualTo(1024);
    }

    @Test
    void saveWritesChunkProgressFields() throws Exception {
        TaskProgressSnapshot snapshot = new TaskProgressSnapshot(
            "task_abc123",
            "RUNNING",
            51,
            "ASR",
            null,
            null,
            UPDATED_AT,
            7,
            12,
            8,
            "语音转文字中：已完成 7 / 12 段"
        );

        service.save(snapshot);

        ArgumentCaptor<String> jsonCaptor = ArgumentCaptor.forClass(String.class);
        verify(valueOperations).set(eq("cl:t:progress:task_abc123"), jsonCaptor.capture(), eq(Duration.ofSeconds(86400)));
        JsonNode json = objectMapper.readTree(jsonCaptor.getValue());
        assertThat(json.get("completedChunks").asInt()).isEqualTo(7);
        assertThat(json.get("totalChunks").asInt()).isEqualTo(12);
        assertThat(json.get("currentChunkIndex").asInt()).isEqualTo(8);
        assertThat(json.get("stepDetail").asText()).contains("7 / 12");
    }

    @Test
    void saveSwallowsRedisWriteFailure() {
        doThrow(new IllegalStateException("redis unavailable"))
            .when(valueOperations).set(eq("cl:t:progress:task_abc123"), org.mockito.ArgumentMatchers.anyString(), eq(Duration.ofSeconds(86400)));

        service.save(snapshot("RUNNING", 35, "ASR", null, null));
    }

    @Test
    void findReturnsSnapshotWhenJsonExists() {
        when(valueOperations.get("cl:t:progress:task_abc123"))
            .thenReturn("""
                {"taskId":"task_abc123","status":"SUCCEEDED","progressPercent":100,"currentStage":"DONE","errorCode":null,"errorMessage":null,"updatedAt":"2026-06-27T10:00:00Z"}
                """);

        Optional<TaskProgressSnapshot> result = service.find("task_abc123");

        assertThat(result).isPresent();
        assertThat(result.get().taskId()).isEqualTo("task_abc123");
        assertThat(result.get().status()).isEqualTo("SUCCEEDED");
        assertThat(result.get().progressPercent()).isEqualTo(100);
        assertThat(result.get().currentStage()).isEqualTo("DONE");
    }

    @Test
    void findReturnsEmptyWhenKeyDoesNotExistOrReadFails() {
        when(valueOperations.get("cl:t:progress:task_abc123")).thenReturn(null);
        assertThat(service.find("task_abc123")).isEmpty();

        when(valueOperations.get("cl:t:progress:task_abc123")).thenThrow(new IllegalStateException("redis unavailable"));
        assertThat(service.find("task_abc123")).isEmpty();
    }

    @Test
    void deleteUsesFixedKeyAndSwallowsFailure() {
        service.delete("task_abc123");
        verify(redisTemplate).delete("cl:t:progress:task_abc123");

        doThrow(new IllegalStateException("redis unavailable")).when(redisTemplate).delete("cl:t:progress:task_broken");
        service.delete("task_broken");
    }

    private static TaskProgressSnapshot snapshot(
        String status,
        int progressPercent,
        String currentStage,
        String errorCode,
        String errorMessage
    ) {
        return new TaskProgressSnapshot(
            "task_abc123",
            status,
            progressPercent,
            currentStage,
            errorCode,
            errorMessage,
            UPDATED_AT
        );
    }
}
