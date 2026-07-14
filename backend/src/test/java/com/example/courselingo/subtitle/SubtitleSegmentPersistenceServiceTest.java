package com.example.courselingo.subtitle;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.asr.SpeechToTextResult;
import com.example.courselingo.ai.asr.TranscribedSegment;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.dto.SubtitleSegmentView;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.service.SaveTranscriptionSegmentsCommand;
import com.example.courselingo.subtitle.service.SubtitleSegmentPersistenceServiceImpl;
import com.example.courselingo.subtitle.service.SubtitleSegmentQueryServiceImpl;
import java.io.IOException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.annotation.Transactional;

@ExtendWith(MockitoExtension.class)
class SubtitleSegmentPersistenceServiceTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(
        Instant.parse("2026-06-28T10:00:00Z"),
        ZoneOffset.UTC
    );

    @Mock
    private SubtitleSegmentMapper mapper;

    private SubtitleSegmentPersistenceServiceImpl persistenceService;
    private SubtitleSegmentQueryServiceImpl queryService;

    @BeforeEach
    void setUp() {
        persistenceService = new SubtitleSegmentPersistenceServiceImpl(mapper, FIXED_CLOCK);
        queryService = new SubtitleSegmentQueryServiceImpl(mapper);
    }

    @Test
    void saveTranscriptionResultDeletesOldOwnerScopedRowsAndInsertsNewSegments() {
        SpeechToTextResult result = result(
            "mock",
            "en",
            List.of(
                new TranscribedSegment(0, 0, 900, "hello"),
                new TranscribedSegment(1, 1000, 1800, "world")
            )
        );
        when(mapper.insert(any(SubtitleSegment.class))).thenReturn(1);

        int saved = persistenceService.saveTranscriptionResult(
            new SaveTranscriptionSegmentsCommand("task_1", 42L, result)
        );

        assertThat(saved).isEqualTo(2);
        verify(mapper).deleteByTaskIdAndUserId("task_1", 42L);
        List<SubtitleSegment> inserted = captureInsertedSegments();
        assertThat(inserted).hasSize(2);
        assertThat(inserted).extracting(SubtitleSegment::getTaskId).containsOnly("task_1");
        assertThat(inserted).extracting(SubtitleSegment::getUserId).containsOnly(42L);
        assertThat(inserted).extracting(SubtitleSegment::getSegmentIndex).containsExactly(0, 1);
        assertThat(inserted).extracting(SubtitleSegment::getStartMillis).containsExactly(0L, 1000L);
        assertThat(inserted).extracting(SubtitleSegment::getEndMillis).containsExactly(900L, 1800L);
        assertThat(inserted).extracting(SubtitleSegment::getLanguage).containsOnly("en");
        assertThat(inserted).extracting(SubtitleSegment::getText).containsExactly("hello", "world");
        assertThat(inserted).extracting(SubtitleSegment::getProvider).containsOnly("mock");
        assertThat(inserted).extracting(SubtitleSegment::getCreatedAt).containsOnly(now());
        assertThat(inserted).extracting(SubtitleSegment::getUpdatedAt).containsOnly(now());
    }

    @Test
    void saveTranscriptionResultRequiresTransactionOnDeleteAndInsert() throws NoSuchMethodException {
        Transactional annotation = SubtitleSegmentPersistenceServiceImpl.class
            .getMethod("saveTranscriptionResult", SaveTranscriptionSegmentsCommand.class)
            .getAnnotation(Transactional.class);

        assertThat(annotation).isNotNull();
    }

    @Test
    void saveTranscriptionResultRejectsEmptySegmentsAndDoesNotDeleteOldRows() {
        SpeechToTextResult result = result("mock", "en", List.of());

        assertValidationFailure(() -> persistenceService.saveTranscriptionResult(
            new SaveTranscriptionSegmentsCommand("task_1", 42L, result)
        ));

        verify(mapper, never()).deleteByTaskIdAndUserId(any(), any());
        verify(mapper, never()).insert(any(SubtitleSegment.class));
    }

    @Test
    void saveTranscriptionResultRejectsInvalidCommandFields() {
        SpeechToTextResult result = result("mock", "en", List.of(new TranscribedSegment(0, 0, 1, "text")));

        assertValidationFailure(() -> persistenceService.saveTranscriptionResult(null));
        assertValidationFailure(() -> persistenceService.saveTranscriptionResult(
            new SaveTranscriptionSegmentsCommand("", 42L, result)
        ));
        assertValidationFailure(() -> persistenceService.saveTranscriptionResult(
            new SaveTranscriptionSegmentsCommand("task_1", null, result)
        ));
        assertValidationFailure(() -> persistenceService.saveTranscriptionResult(
            new SaveTranscriptionSegmentsCommand("task_1", 42L, null)
        ));
        assertValidationFailure(() -> persistenceService.saveTranscriptionResult(
            new SaveTranscriptionSegmentsCommand("task_1", 42L, result("mock", "", result.segments()))
        ));
        assertValidationFailure(() -> persistenceService.saveTranscriptionResult(
            new SaveTranscriptionSegmentsCommand("task_1", 42L, result("mock", "x".repeat(33), result.segments()))
        ));
        assertValidationFailure(() -> persistenceService.saveTranscriptionResult(
            new SaveTranscriptionSegmentsCommand("task_1", 42L, result("x".repeat(65), "en", result.segments()))
        ));

        verify(mapper, never()).deleteByTaskIdAndUserId(any(), any());
        verify(mapper, never()).insert(any(SubtitleSegment.class));
    }

    @Test
    void saveTranscriptionResultRejectsUnsafeProviderNameWithoutLeakingSensitiveValues() {
        SpeechToTextResult result = result(
            "Authorization: Bearer token secret api key C:\\Users\\demo\\file.wav /home/demo/file",
            "en",
            List.of(new TranscribedSegment(0, 0, 1, "text"))
        );

        assertThatThrownBy(() -> persistenceService.saveTranscriptionResult(
            new SaveTranscriptionSegmentsCommand("task_1", 42L, result)
        ))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                BusinessException exception = (BusinessException) error;
                assertThat(exception.errorCode()).isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
                assertThat(exception.getMessage()).doesNotContainIgnoringCase("token");
                assertThat(exception.getMessage()).doesNotContainIgnoringCase("secret");
                assertThat(exception.getMessage()).doesNotContainIgnoringCase("api key");
                assertThat(exception.getMessage()).doesNotContainIgnoringCase("authorization");
                assertThat(exception.getMessage()).doesNotContain("C:\\");
                assertThat(exception.getMessage()).doesNotContain("/home/");
            });

        verify(mapper, never()).deleteByTaskIdAndUserId(any(), any());
        verify(mapper, never()).insert(any(SubtitleSegment.class));
    }

    @Test
    void saveTranscriptionResultFailsIfBatchInsertDoesNotInsertEverySegment() {
        SpeechToTextResult result = result(
            "mock",
            "en",
            List.of(new TranscribedSegment(0, 0, 900, "hello"))
        );
        when(mapper.insert(any(SubtitleSegment.class))).thenReturn(0);

        assertThatThrownBy(() -> persistenceService.saveTranscriptionResult(
            new SaveTranscriptionSegmentsCommand("task_1", 42L, result)
        ))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_INTERNAL_ERROR);
    }

    @Test
    void listByTaskIdReturnsCurrentUsersSegmentsOnlyWithoutUserId() {
        when(mapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            storedSegment("task_1", 42L, 0, "hello"),
            storedSegment("task_1", 42L, 1, "world")
        ));

        List<SubtitleSegmentView> views = queryService.listByTaskId("task_1", 42L);

        assertThat(views).extracting(SubtitleSegmentView::segmentIndex).containsExactly(0, 1);
        assertThat(views).extracting(SubtitleSegmentView::text).containsExactly("hello", "world");
        assertThat(views).extracting(SubtitleSegmentView::language).containsOnly("en");
        assertThat(views).extracting(SubtitleSegmentView::provider).containsOnly("mock");
        verify(mapper).selectByTaskIdAndUserId("task_1", 42L);
    }

    @Test
    void deleteAndCountAreOwnerScoped() {
        when(mapper.deleteByTaskIdAndUserId("task_1", 42L)).thenReturn(3);
        when(mapper.countByTaskIdAndUserId("task_1", 42L)).thenReturn(2L);

        assertThat(persistenceService.deleteByTaskId("task_1", 42L)).isEqualTo(3);
        assertThat(queryService.countByTaskId("task_1", 42L)).isEqualTo(2L);

        verify(mapper).deleteByTaskIdAndUserId("task_1", 42L);
        verify(mapper).countByTaskIdAndUserId("task_1", 42L);
    }

    @Test
    void boundariesDoNotCallForbiddenPipelineIntegrations() throws IOException {
        List<java.nio.file.Path> subtitleFiles = java.nio.file.Files.walk(
                java.nio.file.Path.of("src", "main", "java", "com", "example", "courselingo", "subtitle")
            )
            .filter(java.nio.file.Files::isRegularFile)
            .toList();

        for (java.nio.file.Path path : subtitleFiles) {
            String source = java.nio.file.Files.readString(path);
            assertThat(source).doesNotContain("Ffmpeg");
            assertThat(source).doesNotContain("SpeechToTextProvider");
            assertThat(source).doesNotContain("SiliconFlow");
            assertThat(source).doesNotContain("MockAsr");
            assertThat(source).doesNotContain("LangChain4j");
            assertThat(source).doesNotContain("OpenAiCompatible");
            assertThat(source).doesNotContain("AnalysisTaskRunner");
            assertThat(source).doesNotContain("RocketMQ");
            assertThat(source).doesNotContain("Artifact");
        }
    }

    private List<SubtitleSegment> captureInsertedSegments() {
        ArgumentCaptor<SubtitleSegment> captor = ArgumentCaptor.forClass(SubtitleSegment.class);
        verify(mapper, org.mockito.Mockito.times(2)).insert(captor.capture());
        return captor.getAllValues();
    }

    private static SpeechToTextResult result(String provider, String language, List<TranscribedSegment> segments) {
        return new SpeechToTextResult(
            provider,
            language,
            "full text",
            segments,
            Duration.ofMillis(200),
            2000,
            Map.of("safe", "value")
        );
    }

    private static SubtitleSegment storedSegment(String taskId, Long userId, int index, String text) {
        SubtitleSegment segment = new SubtitleSegment();
        segment.setId((long) index + 1);
        segment.setTaskId(taskId);
        segment.setUserId(userId);
        segment.setSegmentIndex(index);
        segment.setStartMillis(index * 1000L);
        segment.setEndMillis(index * 1000L + 900L);
        segment.setLanguage("en");
        segment.setText(text);
        segment.setProvider("mock");
        segment.setCreatedAt(now());
        segment.setUpdatedAt(now());
        return segment;
    }

    private static void assertValidationFailure(ThrowingCallable callable) {
        assertThatThrownBy(callable::call)
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
    }

    private static LocalDateTime now() {
        return LocalDateTime.ofInstant(FIXED_CLOCK.instant(), FIXED_CLOCK.getZone());
    }

    @FunctionalInterface
    private interface ThrowingCallable {
        void call();
    }
}
