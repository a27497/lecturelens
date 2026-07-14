package com.example.courselingo.learning;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.example.courselingo.ai.llm.LlmMessage;
import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.llm.LlmResponseFormat;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResult;
import com.example.courselingo.ai.llm.LlmRole;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.learning.domain.LearningPackage;
import com.example.courselingo.learning.dto.LearningPackageView;
import com.example.courselingo.learning.mapper.LearningPackageMapper;
import com.example.courselingo.learning.service.GenerateLearningPackageCommand;
import com.example.courselingo.learning.service.LearningPackageProperties;
import com.example.courselingo.learning.service.LearningPackageQueryServiceImpl;
import com.example.courselingo.learning.service.LearningPackageResponseParser;
import com.example.courselingo.learning.service.LearningPackageServiceImpl;
import com.example.courselingo.modelrouting.AiModelProfile;
import com.example.courselingo.modelrouting.AiModelRoutedLlmRequestFactory;
import com.example.courselingo.modelrouting.AiModelRouter;
import com.example.courselingo.modelrouting.AiModelRoutingProperties;
import com.example.courselingo.modelrouting.AiModelStage;
import com.example.courselingo.modelrouting.ModelCapability;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.EnumSet;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.slf4j.LoggerFactory;
import org.springframework.transaction.annotation.Transactional;

@ExtendWith(MockitoExtension.class)
class LearningPackageServiceTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(
        Instant.parse("2026-06-28T10:00:00Z"),
        ZoneOffset.UTC
    );

    @Mock
    private SubtitleSegmentMapper sourceMapper;

    @Mock
    private SubtitleTranslationSegmentMapper translationMapper;

    @Mock
    private LearningPackageMapper learningPackageMapper;

    private FakeLlmProvider fakeLlmProvider;
    private LearningPackageServiceImpl learningPackageService;
    private LearningPackageQueryServiceImpl queryService;

    @BeforeEach
    void setUp() {
        fakeLlmProvider = new FakeLlmProvider();
        learningPackageService = new LearningPackageServiceImpl(
            sourceMapper,
            translationMapper,
            learningPackageMapper,
            fakeLlmProvider,
            FIXED_CLOCK,
            new LearningPackageResponseParser()
        );
        queryService = new LearningPackageQueryServiceImpl(learningPackageMapper);
    }

    @Test
    void generateReadsD7AndD8SubtitlesCallsFakeLlmAndSavesLearningPackage() {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(translationSegments());
        when(learningPackageMapper.insert(any(LearningPackage.class))).thenReturn(1);
        fakeLlmProvider.nextContent = okJson();

        int saved = learningPackageService.generateLearningPackage(command());

        assertThat(saved).isEqualTo(1);
        verify(sourceMapper).selectByTaskIdAndUserId("task_1", 42L);
        verify(translationMapper).selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN");
        verify(learningPackageMapper).deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN");
        assertThat(fakeLlmProvider.requests).hasSize(1);
        LlmRequest request = fakeLlmProvider.requests.getFirst();
        assertThat(request.requestId()).isEqualTo("req_1");
        assertThat(request.taskId()).isEqualTo("task_1");
        assertThat(request.timeout()).isEqualTo(Duration.ofSeconds(180));
        assertThat(request.responseFormat()).isEqualTo(LlmResponseFormat.JSON_OBJECT);
        assertThat(request.messages()).extracting(LlmMessage::role).containsExactly(LlmRole.SYSTEM, LlmRole.USER);
        assertThat(request.messages().getFirst().content())
            .contains(
                "Return only a valid JSON object",
                "Do not return Markdown",
                "Do not wrap the output in ```json fences",
                "Do not include explanations before or after JSON",
                "summary",
                "keyPoints",
                "glossary",
                "qa"
            );
        assertThat(request.messages().get(1).content())
            .contains("\"sourceText\":\"hello\"", "\"translatedText\":\"你好\"", "\"index\":1");
        assertThat(request.metadata()).containsEntry("sourceLanguage", "en");
        assertThat(request.metadata()).containsEntry("targetLanguage", "zh-CN");

        LearningPackage inserted = captureInserted();
        assertThat(inserted.getTaskId()).isEqualTo("task_1");
        assertThat(inserted.getUserId()).isEqualTo(42L);
        assertThat(inserted.getSourceLanguage()).isEqualTo("en");
        assertThat(inserted.getTargetLanguage()).isEqualTo("zh-CN");
        assertThat(inserted.getTitle()).isEqualTo("Course Title");
        assertThat(inserted.getSummary()).isEqualTo("Course summary");
        assertThat(inserted.getKeyPointsJson()).isEqualTo("[{\"index\":1,\"text\":\"Point\"}]");
        assertThat(inserted.getGlossaryJson()).isEqualTo("[{\"term\":\"Term\",\"definition\":\"Definition\",\"translation\":\"术语\"}]");
        assertThat(inserted.getQaJson()).isEqualTo("[{\"question\":\"Question\",\"answer\":\"Answer\"}]");
        assertThat(inserted.getProvider()).isEqualTo("fake");
        assertThat(inserted.getSchemaVersion()).isEqualTo("learning-package.v1");
        assertThat(inserted.getCreatedAt()).isEqualTo(now());
        assertThat(inserted.getUpdatedAt()).isEqualTo(now());
    }

    @Test
    void generateAppliesLearningPackageRoute() {
        learningPackageService = new LearningPackageServiceImpl(
            sourceMapper,
            translationMapper,
            learningPackageMapper,
            fakeLlmProvider,
            FIXED_CLOCK,
            new LearningPackageResponseParser(),
            new LearningPackageProperties(),
            routedRequestFactory()
        );
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(translationSegments());
        when(learningPackageMapper.insert(any(LearningPackage.class))).thenReturn(1);
        fakeLlmProvider.nextContent = okJson();

        learningPackageService.generateLearningPackage(command());

        assertThat(fakeLlmProvider.requests.getFirst().metadata())
            .containsEntry(AiModelRoutedLlmRequestFactory.METADATA_STAGE, AiModelStage.LEARNING_PACKAGE.name())
            .containsEntry(AiModelRoutedLlmRequestFactory.METADATA_PROFILE_CODE, "deepseek-text");
    }

    @Test
    void generateLearningPackageRequiresTransactionOnReadLlmParseDeleteAndInsert() throws NoSuchMethodException {
        Transactional annotation = LearningPackageServiceImpl.class
            .getMethod("generateLearningPackage", GenerateLearningPackageCommand.class)
            .getAnnotation(Transactional.class);

        assertThat(annotation).isNotNull();
    }

    @Test
    void generateUsesConfiguredLearningPackageLlmTimeout() {
        learningPackageService = new LearningPackageServiceImpl(
            sourceMapper,
            translationMapper,
            learningPackageMapper,
            fakeLlmProvider,
            FIXED_CLOCK,
            new LearningPackageResponseParser(),
            new LearningPackageProperties(Duration.ofSeconds(240))
        );
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(translationSegments());
        when(learningPackageMapper.insert(any(LearningPackage.class))).thenReturn(1);

        learningPackageService.generateLearningPackage(command());

        assertThat(fakeLlmProvider.requests).hasSize(1);
        assertThat(fakeLlmProvider.requests.getFirst().timeout()).isEqualTo(Duration.ofSeconds(240));
        assertThat(fakeLlmProvider.requests.getFirst().responseFormat()).isEqualTo(LlmResponseFormat.JSON_OBJECT);
    }

    @Test
    void queryReturnsOwnerScopedPackageWithoutUserId() {
        when(learningPackageMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(learningPackage("task_1", 42L, "zh-CN", "Course Title"));

        Optional<LearningPackageView> view = queryService.getByTaskAndLanguage("task_1", 42L, "zh-CN");

        assertThat(view).isPresent();
        assertThat(view.get().taskId()).isEqualTo("task_1");
        assertThat(view.get().sourceLanguage()).isEqualTo("en");
        assertThat(view.get().targetLanguage()).isEqualTo("zh-CN");
        assertThat(view.get().title()).isEqualTo("Course Title");
        assertThat(view.get().keyPointsJson()).contains("Point");
        assertThat(view.get().provider()).isEqualTo("fake");
    }

    @Test
    void overwriteDeleteAndCountAreScopedByTaskUserAndTargetLanguage() {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(translationSegments());
        when(learningPackageMapper.insert(any(LearningPackage.class))).thenReturn(1);
        when(learningPackageMapper.deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN")).thenReturn(1);
        when(learningPackageMapper.countByTaskIdAndLanguage("task_1", 42L, "zh-CN")).thenReturn(1L);

        int saved = learningPackageService.generateLearningPackage(command());
        int deleted = learningPackageService.deleteLearningPackage("task_1", 42L, "zh-CN");
        long count = queryService.countByTaskIdAndLanguage("task_1", 42L, "zh-CN");

        assertThat(saved).isEqualTo(1);
        assertThat(deleted).isEqualTo(1);
        assertThat(count).isEqualTo(1L);
        verify(learningPackageMapper, org.mockito.Mockito.times(2))
            .deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN");
        verify(learningPackageMapper, never()).deleteByTaskIdUserIdAndTargetLanguage("task_1", 43L, "zh-CN");
        verify(learningPackageMapper, never()).deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "ja-JP");
    }

    @Test
    void invalidCommandMissingSubtitlesAndProviderFailuresDoNotSave() {
        assertValidationFailure(() -> learningPackageService.generateLearningPackage(null));
        assertValidationFailure(() -> learningPackageService.generateLearningPackage(command("", 42L, "en", "zh-CN", "req_1")));
        assertValidationFailure(() -> learningPackageService.generateLearningPackage(command("task_1", null, "en", "zh-CN", "req_1")));
        assertValidationFailure(() -> learningPackageService.generateLearningPackage(command("task_1", 42L, " ", "zh-CN", "req_1")));
        assertValidationFailure(() -> learningPackageService.generateLearningPackage(command("task_1", 42L, "en", " ", "req_1")));
        assertValidationFailure(() -> learningPackageService.generateLearningPackage(command("task_1", 42L, "en", "zh-CN", " ")));
        assertValidationFailure(() -> learningPackageService.generateLearningPackage(command("task_1", 42L, "x".repeat(33), "zh-CN", "req_1")));
        assertValidationFailure(() -> learningPackageService.generateLearningPackage(command("task_1", 42L, "en", "x".repeat(33), "req_1")));
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(java.util.List.of());
        assertValidationFailure(() -> learningPackageService.generateLearningPackage(command()));
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(java.util.List.of());
        assertValidationFailure(() -> learningPackageService.generateLearningPackage(command()));

        assertThat(fakeLlmProvider.requests).isEmpty();
        verify(learningPackageMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(learningPackageMapper, never()).insert(any(LearningPackage.class));
    }

    @Test
    void invalidSubtitleRowsParserJsonAndUnsafeProviderFailWithoutPartialSave() {
        assertValidationFailure(() -> generateWith(sourceSegments(sourceSegment(0, 0, 900, " ")), translationSegments(), okJson()));
        assertValidationFailure(() -> generateWith(sourceSegments(), translationSegments(translationSegment(0, 0, 900, " ")), okJson()));
        assertValidationFailure(() -> generateWith(sourceSegments(sourceSegment(0, 0, 900, "hello")), translationSegments(), okJson()));
        fakeLlmProvider.providerName = "x".repeat(65);
        assertValidationFailure(() -> generateWith(sourceSegments(), translationSegments(), okJson()));
        fakeLlmProvider.providerName = "fake";

        verify(learningPackageMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(learningPackageMapper, never()).insert(any(LearningPackage.class));
    }

    @Test
    void firstJsonParseFailureLogsPreviewAndRetriesWithCompactPrompt() {
        Logger logger = (Logger) LoggerFactory.getLogger(LearningPackageServiceImpl.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
            when(translationMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
                .thenReturn(translationSegments());
            when(learningPackageMapper.insert(any(LearningPackage.class))).thenReturn(1);
            String unsafeContent = "Explanation Authorization: Bearer raw-token password=raw-secret "
                + "C:\\Users\\demo\\key.txt " + "x".repeat(1200);
            fakeLlmProvider.enqueueContent(unsafeContent, """
                {"summary":"Retry summary","keyPoints":["Retry point"],"glossary":[],"qa":[]}
                """);

            int saved = learningPackageService.generateLearningPackage(command());

            assertThat(saved).isEqualTo(1);
            assertThat(fakeLlmProvider.requests).hasSize(2);
            LlmRequest retryRequest = fakeLlmProvider.requests.get(1);
            assertThat(retryRequest.responseFormat()).isEqualTo(LlmResponseFormat.JSON_OBJECT);
            assertThat(retryRequest.messages().getFirst().content())
                .contains(
                    "minimal learning package",
                    "Do not use nested arrays",
                    "Do not repeat text",
                    "Do not return Markdown",
                    "Do not wrap the output in ```json fences"
                );
            LearningPackage inserted = captureInserted();
            assertThat(inserted.getSummary()).isEqualTo("Retry summary");
            assertThat(inserted.getKeyPointsJson()).isEqualTo("[{\"index\":1,\"text\":\"Retry point\"}]");
            assertThat(appender.list)
                .extracting(ILoggingEvent::getFormattedMessage)
                .anySatisfy(message -> {
                    assertThat(message).contains("event=learning_package_parse_failed");
                    assertThat(message).contains("retry=start");
                    assertThat(message).contains("rawContentPreview=");
                    assertThat(message).contains("[redacted]");
                    assertThat(message).doesNotContain("raw-token", "raw-secret", "C:\\Users\\demo");
                    assertThat(message).doesNotContain("x".repeat(1001));
                });
        } finally {
            logger.detachAppender(appender);
        }
    }

    @Test
    void retryJsonParseFailureUsesDeterministicFallbackAndSavesDegradedPackage() {
        Logger logger = (Logger) LoggerFactory.getLogger(LearningPackageServiceImpl.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
            when(translationMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
                .thenReturn(translationSegments(
                    translationSegment(0, 0, 900, "Spring Boot builds web APIs. It simplifies configuration."),
                    translationSegment(1, 1000, 1900, "AI helps summarize lessons.")
                ));
            when(learningPackageMapper.insert(any(LearningPackage.class))).thenReturn(1);
            fakeLlmProvider.enqueueContent("{not-json", "{\"summary\":\"broken\",\"qa\":[[{\"question\":\"bad\"");

            int saved = learningPackageService.generateLearningPackage(command());

            assertThat(saved).isEqualTo(1);
            assertThat(fakeLlmProvider.requests).hasSize(2);
            assertThat(fakeLlmProvider.requests).allSatisfy(request ->
                assertThat(request.responseFormat()).isEqualTo(LlmResponseFormat.JSON_OBJECT)
            );
            LearningPackage inserted = captureInserted();
            assertThat(inserted.getSummary()).isEqualTo("Spring Boot builds web APIs. It simplifies configuration.");
            assertThat(inserted.getKeyPointsJson())
                .isEqualTo("[{\"index\":1,\"text\":\"Spring Boot builds web APIs\"},{\"index\":2,\"text\":\"It simplifies configuration\"},{\"index\":3,\"text\":\"AI helps summarize lessons\"}]");
            assertThat(inserted.getGlossaryJson()).isEqualTo("[]");
            assertThat(inserted.getQaJson()).isEqualTo("[]");
            assertThat(appender.list)
                .extracting(ILoggingEvent::getFormattedMessage)
                .anySatisfy(message -> assertThat(message).contains("event=learning_package_fallback_used"));
        } finally {
            logger.detachAppender(appender);
        }
    }

    @Test
    void glossaryItemWithBlankDefinitionIsSanitizedAndSavedWithoutFailure() {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(translationSegments());
        when(learningPackageMapper.insert(any(LearningPackage.class))).thenReturn(1);
        fakeLlmProvider.nextContent = """
            {"summary":"Summary","keyPoints":["Point"],"glossary":[{"term":"Spring Boot","definition":""}],"qa":[]}
            """;

        int saved = learningPackageService.generateLearningPackage(command());

        assertThat(saved).isEqualTo(1);
        LearningPackage inserted = captureInserted();
        assertThat(inserted.getGlossaryJson())
            .isEqualTo("[{\"term\":\"Spring Boot\",\"definition\":\"\",\"translation\":\"\"}]");
    }

    @Test
    void contentValidationFailureUsesDeterministicFallbackAndDoesNotFailPipeline() {
        Logger logger = (Logger) LoggerFactory.getLogger(LearningPackageServiceImpl.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            LearningPackageResponseParser failingParser = new LearningPackageResponseParser() {
                @Override
                public ParsedLearningPackage parse(String content) {
                    throw new BusinessException(
                        ErrorCode.COMMON_VALIDATION_FAILED,
                        "Learning package glossary item is invalid"
                    );
                }
            };
            learningPackageService = new LearningPackageServiceImpl(
                sourceMapper,
                translationMapper,
                learningPackageMapper,
                fakeLlmProvider,
                FIXED_CLOCK,
                failingParser
            );
            when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
            when(translationMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
                .thenReturn(translationSegments(
                    translationSegment(0, 0, 900, "Spring Boot builds web APIs."),
                    translationSegment(1, 1000, 1900, "AI helps summarize lessons.")
                ));
            when(learningPackageMapper.insert(any(LearningPackage.class))).thenReturn(1);

            int saved = learningPackageService.generateLearningPackage(command());

            assertThat(saved).isEqualTo(1);
            assertThat(fakeLlmProvider.requests).hasSize(2);
            assertThat(fakeLlmProvider.requests).allSatisfy(request ->
                assertThat(request.responseFormat()).isEqualTo(LlmResponseFormat.JSON_OBJECT)
            );
            LearningPackage inserted = captureInserted();
            assertThat(inserted.getSummary()).isEqualTo("Spring Boot builds web APIs. AI helps summarize lessons.");
            assertThat(inserted.getKeyPointsJson())
                .isEqualTo("[{\"index\":1,\"text\":\"Spring Boot builds web APIs\"},{\"index\":2,\"text\":\"AI helps summarize lessons\"}]");
            assertThat(inserted.getGlossaryJson()).isEqualTo("[]");
            assertThat(inserted.getQaJson()).isEqualTo("[]");
            assertThat(appender.list)
                .extracting(ILoggingEvent::getFormattedMessage)
                .anySatisfy(message -> {
                    assertThat(message).contains("event=learning_package_fallback_used");
                    assertThat(message).contains("reason=validation_failed");
                });
        } finally {
            logger.detachAppender(appender);
        }
    }

    @Test
    void insertFailureRaisesInternalErrorSoTransactionCanRollback() {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(translationSegments());
        when(learningPackageMapper.insert(any(LearningPackage.class))).thenReturn(0);

        assertThatThrownBy(() -> learningPackageService.generateLearningPackage(command()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_INTERNAL_ERROR);
    }

    @Test
    void errorsDoNotLeakSecretsAuthorizationHeadersOrLocalPaths() {
        fakeLlmProvider.providerName = "Authorization: Bearer token secret api key C:\\Users\\demo\\key.txt /home/demo/key";

        assertThatThrownBy(() -> generateWith(sourceSegments(), translationSegments(), okJson()))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                assertThat(((BusinessException) error).errorCode()).isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
                assertSafe(error.getMessage());
            });
    }

    @Test
    void boundariesDoNotCallExternalProvidersRunnerMqArtifactsOrFrontend() throws Exception {
        String source = readJavaSources("src/main/java/com/example/courselingo/learning");

        assertThat(source)
            .contains("LlmProvider")
            .doesNotContain("OpenAiCompatible")
            .doesNotContain("LangChain4j")
            .doesNotContain("Ffmpeg")
            .doesNotContain("SpeechToTextProvider")
            .doesNotContain("SiliconFlow")
            .doesNotContain("MockAsr")
            .doesNotContain("AnalysisTaskRunner")
            .doesNotContain("RocketMQ")
            .doesNotContain("ArtifactFile")
            .doesNotContain("ai_call_record");
    }

    private void generateWith(
        java.util.List<SubtitleSegment> sourceSegments,
        java.util.List<SubtitleTranslationSegment> translationSegments,
        String json
    ) {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments);
        when(translationMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(translationSegments);
        fakeLlmProvider.nextContent = json;
        learningPackageService.generateLearningPackage(command());
    }

    private LearningPackage captureInserted() {
        ArgumentCaptor<LearningPackage> captor = ArgumentCaptor.forClass(LearningPackage.class);
        verify(learningPackageMapper).insert(captor.capture());
        return captor.getValue();
    }

    private static GenerateLearningPackageCommand command() {
        return command("task_1", 42L, "en", "zh-CN", "req_1");
    }

    private static GenerateLearningPackageCommand command(
        String taskId,
        Long userId,
        String sourceLanguage,
        String targetLanguage,
        String requestId
    ) {
        return new GenerateLearningPackageCommand(taskId, userId, sourceLanguage, targetLanguage, requestId);
    }

    private static java.util.List<SubtitleSegment> sourceSegments(SubtitleSegment... segments) {
        if (segments.length > 0) {
            return java.util.List.of(segments);
        }
        return java.util.List.of(
            sourceSegment(0, 0, 900, "hello"),
            sourceSegment(1, 1000, 1900, "world")
        );
    }

    private static SubtitleSegment sourceSegment(int index, long startMillis, long endMillis, String text) {
        SubtitleSegment segment = new SubtitleSegment();
        segment.setTaskId("task_1");
        segment.setUserId(42L);
        segment.setSegmentIndex(index);
        segment.setStartMillis(startMillis);
        segment.setEndMillis(endMillis);
        segment.setLanguage("en");
        segment.setText(text);
        segment.setProvider("mock");
        segment.setCreatedAt(now());
        segment.setUpdatedAt(now());
        return segment;
    }

    private static java.util.List<SubtitleTranslationSegment> translationSegments(SubtitleTranslationSegment... segments) {
        if (segments.length > 0) {
            return java.util.List.of(segments);
        }
        return java.util.List.of(
            translationSegment(0, 0, 900, "你好"),
            translationSegment(1, 1000, 1900, "世界")
        );
    }

    private static SubtitleTranslationSegment translationSegment(int index, long startMillis, long endMillis, String text) {
        SubtitleTranslationSegment segment = new SubtitleTranslationSegment();
        segment.setTaskId("task_1");
        segment.setUserId(42L);
        segment.setSegmentIndex(index);
        segment.setStartMillis(startMillis);
        segment.setEndMillis(endMillis);
        segment.setSourceLanguage("en");
        segment.setTargetLanguage("zh-CN");
        segment.setTranslatedText(text);
        segment.setProvider("fake");
        segment.setCreatedAt(now());
        segment.setUpdatedAt(now());
        return segment;
    }

    private static LearningPackage learningPackage(String taskId, Long userId, String targetLanguage, String title) {
        LearningPackage entity = new LearningPackage();
        entity.setTaskId(taskId);
        entity.setUserId(userId);
        entity.setSourceLanguage("en");
        entity.setTargetLanguage(targetLanguage);
        entity.setTitle(title);
        entity.setSummary("Summary");
        entity.setKeyPointsJson("[{\"index\":1,\"text\":\"Point\"}]");
        entity.setGlossaryJson("[]");
        entity.setQaJson("[]");
        entity.setProvider("fake");
        entity.setSchemaVersion("learning-package.v1");
        entity.setCreatedAt(now());
        entity.setUpdatedAt(now());
        return entity;
    }

    private static String okJson() {
        return """
            {"title":"Course Title","summary":"Course summary","keyPoints":[{"index":1,"text":"Point"}],"glossary":[{"term":"Term","definition":"Definition","translation":"术语"}],"qa":[{"question":"Question","answer":"Answer"}]}
            """;
    }

    private static void assertValidationFailure(ThrowingCallable callable) {
        assertThatThrownBy(callable::call)
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
    }

    private static void assertSafe(String message) {
        assertThat(message).doesNotContain("C:\\", "/home/");
        assertThat(message.toLowerCase()).doesNotContain("token", "secret", "api key", "authorization");
    }

    private static LocalDateTime now() {
        return LocalDateTime.ofInstant(FIXED_CLOCK.instant(), FIXED_CLOCK.getZone());
    }

    private static String readJavaSources(String directory) throws java.io.IOException {
        java.nio.file.Path root = java.nio.file.Path.of(directory);
        StringBuilder source = new StringBuilder();
        try (var paths = java.nio.file.Files.walk(root)) {
            for (java.nio.file.Path path : paths.filter(path -> path.toString().endsWith(".java")).toList()) {
                source.append(java.nio.file.Files.readString(path)).append('\n');
            }
        }
        return source.toString();
    }

    private static AiModelRoutedLlmRequestFactory routedRequestFactory() {
        AiModelRoutingProperties properties = new AiModelRoutingProperties();
        properties.setRoutes(Map.of(
            AiModelStage.TRANSLATION_FULL_TEXT, "deepseek-text",
            AiModelStage.SUBTITLE_TRANSLATION, "deepseek-text",
            AiModelStage.LEARNING_PACKAGE, "deepseek-text",
            AiModelStage.COURSE_QA, "deepseek-text",
            AiModelStage.COURSE_CHAPTER, "deepseek-text"
        ));
        AiModelProfile profile = new AiModelProfile();
        profile.setDisplayName("DeepSeek Text");
        profile.setProviderType("openai-compatible");
        profile.setBaseUrl("https://api.siliconflow.cn/v1");
        profile.setModelName("deepseek-ai/DeepSeek-V4-Pro");
        profile.setApiKeyEnvName("OPENAI_COMPATIBLE_API_KEY");
        profile.setCapabilities(EnumSet.of(ModelCapability.TEXT_CHAT, ModelCapability.JSON_OUTPUT));
        profile.setTemperature(0.0d);
        profile.setMaxTokens(32768);
        profile.setTimeout(Duration.ofSeconds(900));
        profile.setMaxAttempts(1);
        properties.setProfiles(Map.of("deepseek-text", profile));
        return new AiModelRoutedLlmRequestFactory(new AiModelRouter(properties));
    }

    @FunctionalInterface
    private interface ThrowingCallable {
        void call();
    }

    private static final class FakeLlmProvider implements LlmProvider {

        private final java.util.List<LlmRequest> requests = new ArrayList<>();
        private final Deque<String> queuedContents = new ArrayDeque<>();
        private String nextContent = okJson();
        private String providerName = "fake";

        void enqueueContent(String... contents) {
            queuedContents.addAll(java.util.List.of(contents));
        }

        @Override
        public LlmResult generate(LlmRequest request) {
            requests.add(request);
            String content = queuedContents.isEmpty() ? nextContent : queuedContents.removeFirst();
            return new LlmResult(providerName, "fake-model", content, "stop", null, Duration.ofMillis(1), Map.of());
        }

        @Override
        public String providerName() {
            return providerName;
        }
    }
}
