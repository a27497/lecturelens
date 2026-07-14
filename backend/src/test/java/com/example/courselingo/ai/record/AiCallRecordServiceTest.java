package com.example.courselingo.ai.record;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.CALLS_REAL_METHODS;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.example.courselingo.ai.record.domain.AiCallRecord;
import com.example.courselingo.ai.record.domain.AiCallRecordStatus;
import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.ai.record.dto.AiCallRecordView;
import com.example.courselingo.ai.record.dto.CompleteAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.FailAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.StartAiCallRecordCommand;
import com.example.courselingo.ai.record.mapper.AiCallRecordMapper;
import com.example.courselingo.ai.record.service.AiCallRecordSanitizer;
import com.example.courselingo.ai.record.service.AiCallRecordServiceImpl;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.lang.reflect.RecordComponent;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.annotation.Transactional;

@ExtendWith(MockitoExtension.class)
class AiCallRecordServiceTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(
        Instant.parse("2026-06-28T10:00:00Z"),
        ZoneOffset.UTC
    );

    @Mock
    private AiCallRecordMapper mapper;

    private AiCallRecordServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new AiCallRecordServiceImpl(mapper, FIXED_CLOCK, new AiCallRecordSanitizer());
    }

    @Test
    void startCallCreatesStartedRecordAndReturnsViewWithoutUserId() {
        when(mapper.insert(any(AiCallRecord.class))).thenAnswer(invocation -> {
            AiCallRecord record = invocation.getArgument(0);
            record.setId(100L);
            return 1;
        });

        AiCallRecordView view = service.startCall(startCommand());

        AiCallRecord inserted = captureInserted();
        assertThat(inserted.getTaskId()).isEqualTo("task_1");
        assertThat(inserted.getUserId()).isEqualTo(42L);
        assertThat(inserted.getCallType()).isEqualTo("LLM");
        assertThat(inserted.getStage()).isEqualTo("TRANSLATION");
        assertThat(inserted.getProvider()).isEqualTo("openai-compatible");
        assertThat(inserted.getModel()).isEqualTo("course-model");
        assertThat(inserted.getStatus()).isEqualTo("STARTED");
        assertThat(inserted.getStartedAt()).isEqualTo(now());
        assertThat(inserted.getFinishedAt()).isNull();
        assertThat(inserted.getInputUnits()).isEqualTo(128);
        assertThat(inserted.getRequestFingerprint()).isEqualTo("f".repeat(64));
        assertThat(inserted.getCreatedAt()).isEqualTo(now());
        assertThat(inserted.getUpdatedAt()).isEqualTo(now());
        assertThat(view.id()).isEqualTo(100L);
        assertThat(view.status()).isEqualTo(AiCallRecordStatus.STARTED);
        assertThat(view.getClass().getRecordComponents())
            .extracting(RecordComponent::getName)
            .doesNotContain("userId");
    }

    @Test
    void completeCallUpdatesOnlyCurrentOwnerRecord() {
        AiCallRecord existing = record(100L, "task_1", 42L, AiCallRecordStatus.STARTED);
        when(mapper.selectByIdTaskIdAndUserId(100L, "task_1", 42L)).thenReturn(existing);
        when(mapper.updateByIdTaskIdAndUserId(any(AiCallRecord.class), org.mockito.Mockito.eq(100L), org.mockito.Mockito.eq("task_1"), org.mockito.Mockito.eq(42L)))
            .thenReturn(1);

        AiCallRecordView view = service.completeCall(completeCommand());

        AiCallRecord updated = captureUpdated();
        assertThat(updated.getStatus()).isEqualTo("SUCCEEDED");
        assertThat(updated.getFinishedAt()).isEqualTo(now());
        assertThat(updated.getDurationMillis()).isEqualTo(2500L);
        assertThat(updated.getPromptTokens()).isEqualTo(10);
        assertThat(updated.getCompletionTokens()).isEqualTo(20);
        assertThat(updated.getTotalTokens()).isEqualTo(30);
        assertThat(updated.getInputUnits()).isEqualTo(128);
        assertThat(updated.getOutputUnits()).isEqualTo(64);
        assertThat(updated.getRequestFingerprint()).isEqualTo("a".repeat(64));
        assertThat(updated.getResponseFingerprint()).isEqualTo("b".repeat(64));
        assertThat(view.status()).isEqualTo(AiCallRecordStatus.SUCCEEDED);
        verify(mapper).selectByIdTaskIdAndUserId(100L, "task_1", 42L);
        verify(mapper, never()).selectByIdTaskIdAndUserId(100L, "task_1", 43L);
    }

    @Test
    void failCallUpdatesOnlyCurrentOwnerRecordAndSanitizesErrorMessage() {
        AiCallRecord existing = record(100L, "task_1", 42L, AiCallRecordStatus.STARTED);
        when(mapper.selectByIdTaskIdAndUserId(100L, "task_1", 42L)).thenReturn(existing);
        when(mapper.updateByIdTaskIdAndUserId(any(AiCallRecord.class), org.mockito.Mockito.eq(100L), org.mockito.Mockito.eq("task_1"), org.mockito.Mockito.eq(42L)))
            .thenReturn(1);

        String unsafe = "Authorization: Bearer abc token secret api key C:\\Users\\demo\\audio.wav objectKey=/a/b "
            + "x".repeat(700);
        AiCallRecordView view = service.failCall(new FailAiCallRecordCommand(
            100L,
            "task_1",
            42L,
            3000L,
            "AI_PROVIDER_FAILED",
            unsafe,
            true,
            "a".repeat(64),
            "b".repeat(64)
        ));

        AiCallRecord updated = captureUpdated();
        assertThat(updated.getStatus()).isEqualTo("FAILED");
        assertThat(updated.getFinishedAt()).isEqualTo(now());
        assertThat(updated.getDurationMillis()).isEqualTo(3000L);
        assertThat(updated.getErrorCode()).isEqualTo("AI_PROVIDER_FAILED");
        assertThat(updated.getErrorMessage()).hasSizeLessThanOrEqualTo(512);
        assertSafe(updated.getErrorMessage());
        assertThat(updated.getRetryable()).isTrue();
        assertThat(view.status()).isEqualTo(AiCallRecordStatus.FAILED);
        assertSafe(view.errorMessage());
    }

    @Test
    void listByTaskReturnsOnlyTaskAndOwnerRecordsInStableOrder() {
        when(mapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            record(100L, "task_1", 42L, AiCallRecordStatus.STARTED),
            record(101L, "task_1", 42L, AiCallRecordStatus.SUCCEEDED)
        ));

        List<AiCallRecordView> views = service.listByTask("task_1", 42L);

        assertThat(views).extracting(AiCallRecordView::id).containsExactly(100L, 101L);
        assertThat(views).extracting(AiCallRecordView::taskId).containsOnly("task_1");
        assertThat(views.getFirst().getClass().getRecordComponents())
            .extracting(RecordComponent::getName)
            .doesNotContain("userId");
        verify(mapper).selectByTaskIdAndUserId("task_1", 42L);
    }

    @Test
    void nonOwnerCompleteAndFailCannotUpdateRecords() {
        when(mapper.selectByIdTaskIdAndUserId(100L, "task_1", 43L)).thenReturn(null);

        assertThatThrownBy(() -> service.completeCall(new CompleteAiCallRecordCommand(
            100L,
            "task_1",
            43L,
            1L,
            null,
            null,
            null,
            null,
            null,
            null,
            null
        )))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_NOT_FOUND);

        assertThatThrownBy(() -> service.failCall(new FailAiCallRecordCommand(
            100L,
            "task_1",
            43L,
            1L,
            "AI_PROVIDER_FAILED",
            "failed",
            false,
            null,
            null
        )))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_NOT_FOUND);

        verify(mapper, never()).updateByIdTaskIdAndUserId(any(), any(), any(), any());
    }

    @Test
    void validationRejectsInvalidStartCompleteAndFailCommands() {
        assertValidationFailure(() -> service.startCall(null));
        assertValidationFailure(() -> service.startCall(new StartAiCallRecordCommand("", 42L, AiCallType.LLM, AiCallStage.TRANSLATION, "provider", "model", null, null)));
        assertValidationFailure(() -> service.startCall(new StartAiCallRecordCommand("x".repeat(65), 42L, AiCallType.LLM, AiCallStage.TRANSLATION, "provider", "model", null, null)));
        assertValidationFailure(() -> service.startCall(new StartAiCallRecordCommand("task_1", null, AiCallType.LLM, AiCallStage.TRANSLATION, "provider", "model", null, null)));
        assertValidationFailure(() -> service.startCall(new StartAiCallRecordCommand("task_1", 42L, null, AiCallStage.TRANSLATION, "provider", "model", null, null)));
        assertValidationFailure(() -> service.startCall(new StartAiCallRecordCommand("task_1", 42L, AiCallType.LLM, null, "provider", "model", null, null)));
        assertValidationFailure(() -> service.startCall(new StartAiCallRecordCommand("task_1", 42L, AiCallType.LLM, AiCallStage.TRANSLATION, " ", "model", null, null)));
        assertValidationFailure(() -> service.startCall(new StartAiCallRecordCommand("task_1", 42L, AiCallType.LLM, AiCallStage.TRANSLATION, "x".repeat(65), "model", null, null)));
        assertValidationFailure(() -> service.startCall(new StartAiCallRecordCommand("task_1", 42L, AiCallType.LLM, AiCallStage.TRANSLATION, "provider", "x".repeat(129), null, null)));
        assertValidationFailure(() -> service.startCall(new StartAiCallRecordCommand("task_1", 42L, AiCallType.LLM, AiCallStage.TRANSLATION, "provider", "model", "x".repeat(129), null)));
        assertValidationFailure(() -> service.startCall(new StartAiCallRecordCommand("task_1", 42L, AiCallType.LLM, AiCallStage.TRANSLATION, "provider", "model", null, -1)));

        assertValidationFailure(() -> service.completeCall(new CompleteAiCallRecordCommand(100L, "task_1", 42L, -1L, null, null, null, null, null, null, null)));
        assertValidationFailure(() -> service.completeCall(new CompleteAiCallRecordCommand(100L, "task_1", 42L, 1L, -1, null, null, null, null, null, null)));
        assertValidationFailure(() -> service.completeCall(new CompleteAiCallRecordCommand(100L, "task_1", 42L, 1L, null, -1, null, null, null, null, null)));
        assertValidationFailure(() -> service.completeCall(new CompleteAiCallRecordCommand(100L, "task_1", 42L, 1L, null, null, -1, null, null, null, null)));
        assertValidationFailure(() -> service.completeCall(new CompleteAiCallRecordCommand(100L, "task_1", 42L, 1L, null, null, null, -1, null, null, null)));
        assertValidationFailure(() -> service.completeCall(new CompleteAiCallRecordCommand(100L, "task_1", 42L, 1L, null, null, null, null, -1, null, null)));
        assertValidationFailure(() -> service.completeCall(new CompleteAiCallRecordCommand(100L, "task_1", 42L, 1L, null, null, null, null, null, "x".repeat(129), null)));

        assertValidationFailure(() -> service.failCall(new FailAiCallRecordCommand(100L, "task_1", 42L, -1L, "ERR", "failed", false, null, null)));

        verify(mapper, never()).insert(any(AiCallRecord.class));
        verify(mapper, never()).updateByIdTaskIdAndUserId(any(), any(), any(), any());
    }

    @Test
    void commandAndViewTypesDoNotAcceptOrExposeRawSensitiveFields() {
        assertThat(recordComponentNames(StartAiCallRecordCommand.class))
            .doesNotContain("rawPrompt", "rawResponse", "completion", "audioPath", "objectKey", "localPath",
                "authorization", "token", "secret", "apiKey", "userIdInView");
        assertThat(recordComponentNames(CompleteAiCallRecordCommand.class))
            .doesNotContain("rawPrompt", "rawResponse", "completion", "audioPath", "objectKey", "localPath",
                "authorization", "token", "secret", "apiKey");
        assertThat(recordComponentNames(FailAiCallRecordCommand.class))
            .doesNotContain("rawPrompt", "rawResponse", "completion", "audioPath", "objectKey", "localPath",
                "authorization", "token", "secret", "apiKey");
        assertThat(recordComponentNames(AiCallRecordView.class))
            .doesNotContain("userId", "rawPrompt", "rawResponse", "completion", "audioPath", "objectKey",
                "localPath", "authorization", "token", "secret", "apiKey");
    }

    @Test
    void mapperQueriesAreScopedByTaskAndUserInStableOrder() {
        AiCallRecordMapper scopedMapper = mock(AiCallRecordMapper.class, CALLS_REAL_METHODS);
        when(scopedMapper.selectList(any(Wrapper.class)))
            .thenReturn(List.of(
                record(100L, "task_1", 42L, AiCallRecordStatus.STARTED),
                record(101L, "task_1", 42L, AiCallRecordStatus.SUCCEEDED)
            ))
            .thenReturn(List.of(record(100L, "task_1", 42L, AiCallRecordStatus.STARTED)));
        when(scopedMapper.update(any(AiCallRecord.class), any(Wrapper.class))).thenReturn(1);

        assertThat(scopedMapper.selectByTaskIdAndUserId("task_1", 42L)).hasSize(2);
        assertThat(scopedMapper.selectByIdTaskIdAndUserId(100L, "task_1", 42L).getId()).isEqualTo(100L);
        assertThat(scopedMapper.updateByIdTaskIdAndUserId(record(100L, "task_1", 42L, AiCallRecordStatus.SUCCEEDED), 100L, "task_1", 42L))
            .isEqualTo(1);

        verify(scopedMapper, org.mockito.Mockito.times(2)).selectList(any(Wrapper.class));
        verify(scopedMapper).update(any(AiCallRecord.class), any(Wrapper.class));
    }

    @Test
    void aiCallRecordServiceUsesTransactionsButDoesNotCallExternalProvidersRunnerMqOrApi() throws Exception {
        assertThat(AiCallRecordServiceImpl.class.getMethod("startCall", StartAiCallRecordCommand.class)
            .getAnnotation(Transactional.class)).isNotNull();
        assertThat(AiCallRecordServiceImpl.class.getMethod("completeCall", CompleteAiCallRecordCommand.class)
            .getAnnotation(Transactional.class)).isNotNull();
        assertThat(AiCallRecordServiceImpl.class.getMethod("failCall", FailAiCallRecordCommand.class)
            .getAnnotation(Transactional.class)).isNotNull();

        String source = readJavaSources("src/main/java/com/example/courselingo/ai/record");
        assertThat(source)
            .doesNotContain("LlmProvider")
            .doesNotContain("OpenAiCompatible")
            .doesNotContain("LangChain4j")
            .doesNotContain("SpeechToTextProvider")
            .doesNotContain("SiliconFlow")
            .doesNotContain("MockAsr")
            .doesNotContain("Ffmpeg")
            .doesNotContain("AnalysisTaskRunner")
            .doesNotContain("RocketMQ")
            .doesNotContain("@RestController")
            .doesNotContain("@RequestMapping")
            .doesNotContain("api_key")
            .doesNotContain("Authorization");
    }

    private AiCallRecord captureInserted() {
        ArgumentCaptor<AiCallRecord> captor = ArgumentCaptor.forClass(AiCallRecord.class);
        verify(mapper).insert(captor.capture());
        return captor.getValue();
    }

    private AiCallRecord captureUpdated() {
        ArgumentCaptor<AiCallRecord> captor = ArgumentCaptor.forClass(AiCallRecord.class);
        verify(mapper).updateByIdTaskIdAndUserId(captor.capture(), org.mockito.Mockito.eq(100L), org.mockito.Mockito.eq("task_1"), org.mockito.Mockito.eq(42L));
        return captor.getValue();
    }

    private static StartAiCallRecordCommand startCommand() {
        return new StartAiCallRecordCommand(
            "task_1",
            42L,
            AiCallType.LLM,
            AiCallStage.TRANSLATION,
            "openai-compatible",
            "course-model",
            "f".repeat(64),
            128
        );
    }

    private static CompleteAiCallRecordCommand completeCommand() {
        return new CompleteAiCallRecordCommand(
            100L,
            "task_1",
            42L,
            2500L,
            10,
            20,
            30,
            128,
            64,
            "a".repeat(64),
            "b".repeat(64)
        );
    }

    private static AiCallRecord record(Long id, String taskId, Long userId, AiCallRecordStatus status) {
        AiCallRecord record = new AiCallRecord();
        record.setId(id);
        record.setTaskId(taskId);
        record.setUserId(userId);
        record.setCallType(AiCallType.LLM.name());
        record.setStage(AiCallStage.TRANSLATION.name());
        record.setProvider("openai-compatible");
        record.setModel("course-model");
        record.setStatus(status.name());
        record.setStartedAt(now());
        record.setCreatedAt(now());
        record.setUpdatedAt(now());
        return record;
    }

    private static LocalDateTime now() {
        return LocalDateTime.ofInstant(FIXED_CLOCK.instant(), FIXED_CLOCK.getZone());
    }

    private static List<String> recordComponentNames(Class<?> type) {
        return java.util.Arrays.stream(type.getRecordComponents())
            .map(RecordComponent::getName)
            .toList();
    }

    private static void assertValidationFailure(ThrowingCallable callable) {
        assertThatThrownBy(callable::call)
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
    }

    private static void assertSafe(String value) {
        assertThat(value).doesNotContain("C:\\", "/home/", "/Users/", "objectKey");
        assertThat(value.toLowerCase()).doesNotContain("token", "secret", "api key", "authorization", "bearer");
    }

    private static String readJavaSources(String directory) throws java.io.IOException {
        Path root = Path.of(directory);
        StringBuilder source = new StringBuilder();
        try (var paths = Files.walk(root)) {
            for (Path path : paths.filter(path -> path.toString().endsWith(".java")).toList()) {
                source.append(Files.readString(path)).append('\n');
            }
        }
        return source.toString();
    }

    @FunctionalInterface
    private interface ThrowingCallable {
        void call();
    }
}
