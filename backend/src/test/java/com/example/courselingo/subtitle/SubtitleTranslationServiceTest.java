package com.example.courselingo.subtitle;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.llm.LlmMessage;
import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.llm.LlmProviderException;
import com.example.courselingo.ai.llm.LlmResponseFormat;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmRequestValidator;
import com.example.courselingo.ai.llm.LlmResult;
import com.example.courselingo.ai.llm.LlmRole;
import com.example.courselingo.ai.llm.LlmUsage;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.modelrouting.AiModelProfile;
import com.example.courselingo.modelrouting.AiModelRoutedLlmRequestFactory;
import com.example.courselingo.modelrouting.AiModelRouter;
import com.example.courselingo.modelrouting.AiModelRoutingProperties;
import com.example.courselingo.modelrouting.AiModelStage;
import com.example.courselingo.modelrouting.ModelCapability;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.TaskFullTextResult;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.dto.SubtitleTranslationSegmentView;
import com.example.courselingo.subtitle.service.SubtitleTranslationProperties.FullText;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.TaskFullTextResultMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import com.example.courselingo.subtitle.service.SubtitleTranslationProperties;
import com.example.courselingo.subtitle.service.SubtitleTranslationAiCallResult;
import com.example.courselingo.subtitle.service.SubtitleTranslationQueryServiceImpl;
import com.example.courselingo.subtitle.service.SubtitleTranslationResponseParser;
import com.example.courselingo.subtitle.service.SubtitleTranslationServiceImpl;
import com.example.courselingo.subtitle.service.TranslateSubtitleCommand;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.EnumSet;
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
class SubtitleTranslationServiceTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(
        Instant.parse("2026-06-28T10:00:00Z"),
        ZoneOffset.UTC
    );

    @Mock
    private SubtitleSegmentMapper sourceMapper;

    @Mock
    private SubtitleTranslationSegmentMapper translationMapper;

    @Mock
    private TaskFullTextResultMapper fullTextResultMapper;

    private FakeLlmProvider fakeLlmProvider;
    private SubtitleTranslationServiceImpl translationService;
    private SubtitleTranslationQueryServiceImpl queryService;

    @BeforeEach
    void setUp() {
        fakeLlmProvider = new FakeLlmProvider();
        translationService = new SubtitleTranslationServiceImpl(
            sourceMapper,
            translationMapper,
            fakeLlmProvider,
            FIXED_CLOCK,
            new SubtitleTranslationResponseParser()
        );
        queryService = new SubtitleTranslationQueryServiceImpl(translationMapper);
    }

    @Test
    void translateTaskSubtitlesCallsLlmPerSegmentAndSavesOriginalIndexes() {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        fakeLlmProvider.nextContents("translated zero", "translated one");

        int saved = translationService.translateTaskSubtitles(command());

        assertThat(saved).isEqualTo(2);
        verify(sourceMapper).selectByTaskIdAndUserId("task_1", 42L);
        verify(translationMapper).deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN");
        assertThat(fakeLlmProvider.requests).hasSize(2);
        LlmRequest request = fakeLlmProvider.requests.getFirst();
        assertThat(request.requestId()).isEqualTo("req_1");
        assertThat(request.taskId()).isEqualTo("task_1");
        assertThat(request.responseFormat()).isEqualTo(LlmResponseFormat.TEXT);
        assertThat(request.messages()).extracting(LlmMessage::role).containsExactly(LlmRole.SYSTEM, LlmRole.USER);
        assertThat(request.messages().get(0).content())
            .contains("only the translated plain text")
            .contains("Do not return JSON")
            .contains("Do not return Markdown")
            .contains("Do not include explanations")
            .contains("Do not include numbering");
        assertThat(request.messages().get(1).content())
            .contains("Translate this subtitle text")
            .contains("hello")
            .doesNotContain("\"segments\"", "\"index\"");
        assertThat(request.metadata()).containsEntry("sourceLanguage", "en");
        assertThat(request.metadata()).containsEntry("targetLanguage", "zh-CN");
        assertThat(request.metadata()).containsEntry("segmentIndex", 0);

        List<SubtitleTranslationSegment> inserted = captureInsertedSegments(2);
        assertThat(inserted).extracting(SubtitleTranslationSegment::getTaskId).containsOnly("task_1");
        assertThat(inserted).extracting(SubtitleTranslationSegment::getUserId).containsOnly(42L);
        assertThat(inserted).extracting(SubtitleTranslationSegment::getSegmentIndex).containsExactly(0, 1);
        assertThat(inserted).extracting(SubtitleTranslationSegment::getStartMillis).containsExactly(0L, 1000L);
        assertThat(inserted).extracting(SubtitleTranslationSegment::getEndMillis).containsExactly(900L, 1900L);
        assertThat(inserted).extracting(SubtitleTranslationSegment::getSourceLanguage).containsOnly("en");
        assertThat(inserted).extracting(SubtitleTranslationSegment::getTargetLanguage).containsOnly("zh-CN");
        assertThat(inserted).extracting(SubtitleTranslationSegment::getTranslatedText).containsExactly("translated zero", "translated one");
        assertThat(inserted).extracting(SubtitleTranslationSegment::getProvider).containsOnly("fake");
        assertThat(inserted).extracting(SubtitleTranslationSegment::getCreatedAt).containsOnly(now());
        assertThat(inserted).extracting(SubtitleTranslationSegment::getUpdatedAt).containsOnly(now());
    }

    @Test
    void translateTaskSubtitlesAppliesSubtitleTranslationRoute() {
        SubtitleTranslationProperties properties = new SubtitleTranslationProperties();
        FullText fullText = new FullText();
        fullText.setEnabled(false);
        properties.setFullText(fullText);
        translationService = new SubtitleTranslationServiceImpl(
            sourceMapper,
            translationMapper,
            fullTextResultMapper,
            fakeLlmProvider,
            FIXED_CLOCK,
            new SubtitleTranslationResponseParser(),
            properties,
            routedRequestFactory()
        );
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        fakeLlmProvider.nextContents("translated zero", "translated one");

        translationService.translateTaskSubtitles(command());

        assertThat(fakeLlmProvider.requests.getFirst().metadata())
            .containsEntry(AiModelRoutedLlmRequestFactory.METADATA_STAGE, AiModelStage.SUBTITLE_TRANSLATION.name())
            .containsEntry(AiModelRoutedLlmRequestFactory.METADATA_PROFILE_CODE, "deepseek-text");
    }

    @Test
    void fullTextModePersistsAlignedSegmentsAndDerivedFullTextFromOneBatchResponse() {
        translationService = new SubtitleTranslationServiceImpl(
            sourceMapper,
            translationMapper,
            fullTextResultMapper,
            fakeLlmProvider,
            FIXED_CLOCK,
            new SubtitleTranslationResponseParser(),
            new SubtitleTranslationProperties()
        );
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(
            "{\"segments\":[{\"index\":0,\"text\":\"译文零\"},{\"index\":1,\"text\":\"译文一\"}]}"
        );

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(2);
        assertThat(result.inputUnits()).isEqualTo(2);
        assertThat(result.outputUnits()).isEqualTo(2);
        assertThat(fakeLlmProvider.requests).hasSize(1);
        LlmRequest request = fakeLlmProvider.requests.getFirst();
        assertThat(request.metadata()).containsEntry("translationMode", "alignedBatch");
        assertThat(request.messages().get(1).content())
            .contains("\"sourceSegmentIndex\":0")
            .contains("\"sourceSegmentIndex\":1");
        List<SubtitleTranslationSegment> translatedSegments = captureInsertedSegments(2);
        assertThat(translatedSegments).extracting(SubtitleTranslationSegment::getSegmentIndex).containsExactly(0, 1);
        assertThat(translatedSegments).extracting(SubtitleTranslationSegment::getTranslatedText)
            .containsExactly("译文零", "译文一");
        ArgumentCaptor<TaskFullTextResult> captor = ArgumentCaptor.forClass(TaskFullTextResult.class);
        verify(fullTextResultMapper).insert(captor.capture());
        TaskFullTextResult inserted = captor.getValue();
        assertThat(inserted.getSourceFullText()).isEqualTo("hello\n\nworld");
        assertThat(inserted.getTranslatedFullText()).isEqualTo("译文零\n\n译文一");
        verify(translationMapper).deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN");
        verify(fullTextResultMapper).deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN");
    }

    @Test
    void firstEnglishBatchSemanticRetryReturnsChineseAndAggregatesAllUsage() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextOutcomes(
            llmResult(
                alignedJson("ENGLISH_OUTPUT_SENTINEL Spring Boot introduction", "Docker deployment continues"),
                "stop",
                10,
                5,
                7
            ),
            llmResult(alignedJson("这是 Spring Boot 课程介绍", "接下来讲解 Docker 部署"), "stop", 6, 8, 11)
        );

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(fakeLlmProvider.requests).hasSize(2);
        assertThat(fakeLlmProvider.requests.getFirst().metadata())
            .containsEntry("semanticAttempt", 1)
            .containsEntry("semanticRetry", false);
        LlmRequest retry = fakeLlmProvider.requests.get(1);
        assertThat(retry.metadata())
            .containsEntry("semanticAttempt", 2)
            .containsEntry("semanticRetry", true)
            .containsEntry("semanticRetryReason", "TARGET_LANGUAGE_MISMATCH")
            .containsEntry("sourceSegmentCount", 2);
        assertThat(retry.messages()).extracting(LlmMessage::content)
            .anySatisfy(content -> assertThat(content).contains("Simplified Chinese"));
        assertThat(retry.messages()).extracting(LlmMessage::content)
            .allSatisfy(content -> assertThat(content).doesNotContain("ENGLISH_OUTPUT_SENTINEL"));
        assertThat(captureInsertedSegments(2)).extracting(SubtitleTranslationSegment::getTranslatedText)
            .containsExactly("这是 Spring Boot 课程介绍", "接下来讲解 Docker 部署");
        ArgumentCaptor<TaskFullTextResult> fullTextCaptor = ArgumentCaptor.forClass(TaskFullTextResult.class);
        verify(fullTextResultMapper).insert(fullTextCaptor.capture());
        assertThat(fullTextCaptor.getValue().getTranslatedFullText())
            .isEqualTo("这是 Spring Boot 课程介绍\n\n接下来讲解 Docker 部署");
        assertThat(result.duration()).isEqualTo(Duration.ofMillis(18));
        assertThat(result.promptTokens()).isEqualTo(16);
        assertThat(result.completionTokens()).isEqualTo(13);
        assertThat(result.totalTokens()).isEqualTo(29);
        assertThat(result.inputUnits()).isEqualTo(2);
        assertThat(result.outputUnits()).isEqualTo(2);
    }

    @Test
    void identicalEnglishBatchUsesUntranslatedSemanticRetryReason() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 10_000, "This course explains Spring Boot deployment in detail.")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(
            alignedJson("This course explains Spring Boot deployment in detail."),
            alignedJson("本课程详细讲解 Spring Boot 的部署方式。")
        );

        translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(fakeLlmProvider.requests).hasSize(2);
        assertThat(fakeLlmProvider.requests.get(1).metadata())
            .containsEntry("semanticRetryReason", "UNTRANSLATED_TEXT");
    }

    @Test
    void twoSemanticFailuresSplitBatchAndChildrenRestartWithNormalRequests() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(
            alignedJson("English prose remains here", "More English prose remains"),
            alignedJson("English prose still remains", "More English prose still remains"),
            alignedJson("这是第一段译文"),
            alignedJson("这是第二段译文")
        );

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(2);
        assertThat(fakeLlmProvider.requests).hasSize(4);
        assertThat(fakeLlmProvider.requests)
            .extracting(request -> request.metadata().get("sourceSegmentCount"))
            .containsExactly(2, 2, 1, 1);
        assertThat(fakeLlmProvider.requests)
            .extracting(request -> request.metadata().get("semanticAttempt"))
            .containsExactly(1, 2, 1, 1);
        assertThat(fakeLlmProvider.requests)
            .extracting(request -> request.metadata().get("semanticRetry"))
            .containsExactly(false, true, false, false);
        assertThat(captureInsertedSegments(2)).extracting(SubtitleTranslationSegment::getTranslatedText)
            .containsExactly("这是第一段译文", "这是第二段译文");
    }

    @Test
    void shortNaturalLanguageSegmentFailsAfterSemanticRetryWithoutAnyWrites() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 10_000, "This course explains deployment.")
        ));
        fakeLlmProvider.nextContents(
            alignedJson("This course explains deployment."),
            alignedJson("This course still explains deployment.")
        );

        assertThatThrownBy(() -> translationService.translateTaskSubtitlesWithAiCallRecord(command()))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                BusinessException exception = (BusinessException) error;
                assertThat(exception.errorCode()).isEqualTo(ErrorCode.AI_PROVIDER_FAILED);
                assertThat(exception.getMessage()).containsAnyOf(
                    "UNTRANSLATED_TEXT",
                    "TARGET_LANGUAGE_MISMATCH"
                );
                assertSafe(exception.getMessage());
            });
        assertThat(fakeLlmProvider.requests).hasSize(2);
        verify(translationMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(translationMapper, never()).insert(any(SubtitleTranslationSegment.class));
        verify(fullTextResultMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(fullTextResultMapper, never()).insert(any(TaskFullTextResult.class));
    }

    @Test
    void semanticMaxAttemptsOneSkipsCorrectiveRetryForUnsplittableSegment() {
        SubtitleTranslationProperties properties = new SubtitleTranslationProperties();
        FullText fullText = new FullText();
        fullText.setEnabled(true);
        fullText.setSemanticMaxAttempts(1);
        properties.setFullText(fullText);
        translationService = fullTextTranslationService(properties);
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 10_000, "This course explains deployment.")
        ));
        fakeLlmProvider.nextContents(alignedJson("This course explains deployment."));

        assertThatThrownBy(() -> translationService.translateTaskSubtitlesWithAiCallRecord(command()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AI_PROVIDER_FAILED);
        assertThat(fakeLlmProvider.requests).hasSize(1);
        assertThat(fakeLlmProvider.requests.getFirst().metadata())
            .containsEntry("semanticAttempt", 1)
            .containsEntry("semanticRetry", false);
        verify(translationMapper, never()).insert(any(SubtitleTranslationSegment.class));
        verify(fullTextResultMapper, never()).insert(any(TaskFullTextResult.class));
    }

    @Test
    void longSegmentSemanticFailureSplitsIntoIndependentlyValidatedPieces() {
        SubtitleTranslationProperties properties = new SubtitleTranslationProperties();
        FullText fullText = new FullText();
        fullText.setEnabled(true);
        fullText.setSingleSegmentMaxPieceChars(22);
        fullText.setSingleSegmentMinPieceChars(8);
        properties.setFullText(fullText);
        translationService = fullTextTranslationService(properties);
        String sourceText = "First long sentence. Second long sentence.";
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(7, 0, 10_000, sourceText)
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(
            alignedJson(sourceText),
            alignedJson(sourceText),
            alignedJson("第一段中文译文"),
            alignedJson("第二段中文译文")
        );

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(1);
        assertThat(fakeLlmProvider.requests).hasSize(4);
        assertThat(fakeLlmProvider.requests)
            .extracting(request -> request.metadata().get("sourceSegmentCount"))
            .containsExactly(1, 1, 1, 1);
        assertThat(fakeLlmProvider.requests)
            .extracting(request -> request.metadata().get("semanticAttempt"))
            .containsExactly(1, 2, 1, 1);
        assertThat(captureInsertedSegments(1).getFirst().getTranslatedText())
            .isEqualTo("第一段中文译文 第二段中文译文");
    }

    @Test
    void pureTechnicalTermMayRemainEnglishWithoutSemanticRetry() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 1000, "Spring Boot")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJson("Spring Boot"));

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(1);
        assertThat(fakeLlmProvider.requests).hasSize(1);
        assertThat(captureInsertedSegments(1).getFirst().getTranslatedText()).isEqualTo("Spring Boot");
    }

    @Test
    void explicitCodeIdentifiersMayRemainEnglishWithoutSemanticRetry() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 1000, "CourseService"),
            sourceSegment(1, 1000, 2000, "run()"),
            sourceSegment(2, 2000, 3000, "courselingo.subtitle.enabled"),
            sourceSegment(3, 3000, 4000, "@Bean")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJson(
            "CourseService",
            "run()",
            "courselingo.subtitle.enabled",
            "@Bean"
        ));

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(4);
        assertThat(fakeLlmProvider.requests).hasSize(1);
        assertThat(captureInsertedSegments(4)).extracting(SubtitleTranslationSegment::getTranslatedText)
            .containsExactly("CourseService", "run()", "courselingo.subtitle.enabled", "@Bean");
    }

    @Test
    void mixedChineseAndCompleteEnglishProseTriggersSemanticRetry() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 2000, "This is the course introduction."),
            sourceSegment(1, 2000, 5000, "This lesson explains Docker deployment in detail.")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(
            alignedJson("这是课程介绍", "This lesson explains Docker deployment in detail."),
            alignedJson("这是课程介绍", "本节课详细讲解 Docker 部署。")
        );

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(2);
        assertThat(fakeLlmProvider.requests).hasSize(2);
        assertThat(fakeLlmProvider.requests.get(1).metadata())
            .containsEntry("semanticRetry", true)
            .containsEntry("semanticRetryReason", "UNTRANSLATED_TEXT");
        assertThat(captureInsertedSegments(2)).extracting(SubtitleTranslationSegment::getTranslatedText)
            .containsExactly("这是课程介绍", "本节课详细讲解 Docker 部署。");
    }

    @Test
    void punctuationOnlySourceCopyIsUntranslatedForNonChineseTarget() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 2000, "Hello world")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJson("Hello world."), alignedJson("Konnichiwa sekai."));

        translationService.translateTaskSubtitlesWithAiCallRecord(
            command("task_1", 42L, "en", "ja", "req_1")
        );

        assertThat(fakeLlmProvider.requests).hasSize(2);
        assertThat(fakeLlmProvider.requests.get(1).metadata())
            .containsEntry("semanticRetryReason", "UNTRANSLATED_TEXT");
    }

    @Test
    void boundedProductNamesAndPunctuatedTechnicalTermsMayRemainEnglish() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 1000, "Kubernetes"),
            sourceSegment(1, 1000, 2000, "Linux"),
            sourceSegment(2, 2000, 3000, "Git"),
            sourceSegment(3, 3000, 4000, "Spring Boot.")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJson("Kubernetes", "Linux", "Git", "Spring Boot."));

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(4);
        assertThat(fakeLlmProvider.requests).hasSize(1);
    }

    @Test
    void springCloudConfigServerInsideChineseDoesNotRetry() {
        assertChineseTranslationWithProductNameDoesNotRetry(
            "Use Spring Cloud Config Server to manage configuration.",
            "使用 Spring Cloud Config Server 管理配置。"
        );
    }

    @Test
    void springCloudNetflixEurekaInsideChineseDoesNotRetry() {
        assertChineseTranslationWithProductNameDoesNotRetry(
            "This lesson introduces Spring Cloud Netflix Eureka.",
            "本节介绍 Spring Cloud Netflix Eureka。"
        );
    }

    @Test
    void visualStudioCodeInsideChineseDoesNotRetry() {
        assertChineseTranslationWithProductNameDoesNotRetry(
            "Open the project in Visual Studio Code.",
            "请在 Visual Studio Code 中打开项目。"
        );
    }

    @Test
    void openAiChatCompletionsApiInsideChineseDoesNotRetry() {
        assertChineseTranslationWithProductNameDoesNotRetry(
            "Call the OpenAI Chat Completions API.",
            "调用 OpenAI Chat Completions API。"
        );
    }

    @Test
    void multiWordProductNameOnlyMayRemainEnglishWithoutSemanticRetry() {
        assertChineseTranslationWithProductNameDoesNotRetry(
            "Spring Cloud Config Server",
            "Spring Cloud Config Server"
        );
    }

    @Test
    void multiWordProductNameMatchingIgnoresCaseSpacingAndAllowedPunctuation() {
        assertChineseTranslationWithProductNameDoesNotRetry(
            "Use Spring Cloud Config Server to manage configuration.",
            "使用 (spring   cloud config server): 管理配置。"
        );
    }

    @Test
    void remainingApprovedMultiWordProductNamesStayEnglishInsideChinese() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 1000, "Use Config Server."),
            sourceSegment(1, 1000, 2000, "Route through API Gateway."),
            sourceSegment(2, 2000, 3000, "Open Spring Boot Admin Server."),
            sourceSegment(3, 3000, 4000, "Open IntelliJ IDEA."),
            sourceSegment(4, 4000, 5000, "Start with Docker Compose."),
            sourceSegment(5, 5000, 6000, "Call the OpenAI API.")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJson(
            "使用 Config Server 管理配置。",
            "通过 API Gateway 路由请求。",
            "使用 Spring Boot Admin Server 查看服务状态。",
            "请用 IntelliJ IDEA 打开项目。",
            "通过 Docker Compose 启动服务。",
            "调用 OpenAI API。"
        ));

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(6);
        assertThat(fakeLlmProvider.requests).hasSize(1);
    }

    @Test
    void multiWordProductNameDoesNotHideFollowingEnglishProse() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 3000, "Use Spring Cloud Config Server to manage configuration.")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(
            alignedJson("使用 Spring Cloud Config Server provides centralized configuration."),
            alignedJson("使用 Spring Cloud Config Server 管理集中式配置。")
        );

        translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(fakeLlmProvider.requests).hasSize(2);
        assertThat(fakeLlmProvider.requests.get(1).metadata())
            .containsEntry("semanticRetryReason", "TARGET_LANGUAGE_MISMATCH");
    }

    @Test
    void multiWordProductNamesDoNotHideUnlistedEnglishVerbs() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 2000, "Explain the integration."),
            sourceSegment(1, 2000, 4000, "Describe the API behavior.")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(
            alignedJson("这是 Spring Cloud enables Docker.", "这里 OpenAI API supports Redis."),
            alignedJson("Spring Cloud 可启用 Docker。", "OpenAI API 支持 Redis。")
        );

        translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(fakeLlmProvider.requests).hasSize(2);
        assertThat(fakeLlmProvider.requests.get(1).metadata())
            .containsEntry("semanticRetryReason", "TARGET_LANGUAGE_MISMATCH");
    }

    @Test
    void multiWordProductNameDoesNotHideSingleEnglishPredicate() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 4000, "Explain the integration.")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(
            alignedJson("这是 Spring Cloud works."),
            alignedJson("这是 Spring Cloud 的集成方式。")
        );

        translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(fakeLlmProvider.requests).hasSize(2);
        assertThat(fakeLlmProvider.requests.get(1).metadata())
            .containsEntry("semanticRetryReason", "TARGET_LANGUAGE_MISMATCH");
    }

    @Test
    void multiWordProductNameWithAnnotationIdentifierDoesNotRetry() {
        assertChineseTranslationWithProductNameDoesNotRetry(
            "Configure the annotation.",
            "使用 Config Server @Bean 配置。"
        );
    }

    @Test
    void multiWordProductNameWithMethodIdentifierDoesNotRetry() {
        assertChineseTranslationWithProductNameDoesNotRetry(
            "Call the health check.",
            "调用 OpenAI API healthCheck()。"
        );
    }

    @Test
    void technicalTermMixedWithCompleteEnglishSentenceIsNotExempt() {
        translationService = fullTextTranslationService();
        String sourceText = "Spring Boot. This course explains deployment.";
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 5000, sourceText)
        ));
        fakeLlmProvider.nextContents(alignedJson(sourceText), alignedJson(sourceText));

        assertThatThrownBy(() -> translationService.translateTaskSubtitlesWithAiCallRecord(command()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AI_PROVIDER_FAILED);
        assertThat(fakeLlmProvider.requests).hasSize(2);
        verify(translationMapper, never()).insert(any(SubtitleTranslationSegment.class));
        verify(fullTextResultMapper, never()).insert(any(TaskFullTextResult.class));
    }

    @Test
    void nonChineseTargetDoesNotApplyChineseCjkValidation() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 5000, "This course explains deployment.")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJson("Kono course wa deployment wo setsumei shimasu."));

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(
            command("task_1", 42L, "en", "ja", "req_1")
        );

        assertThat(result.savedCount()).isEqualTo(1);
        assertThat(fakeLlmProvider.requests).hasSize(1);
    }

    @Test
    void alignedModeAcceptsCompleteOriginalIndexSchemeAndPersistsInSourceOrder() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(18, 1000, 1900, "world"),
            sourceSegment(12, 0, 900, "hello")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJsonWithIndexes(
            new int[] {12, 18},
            "\u8bd1\u6587\u5341\u4e8c",
            "\u8bd1\u6587\u5341\u516b"
        ));

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(2);
        List<SubtitleTranslationSegment> inserted = captureInsertedSegments(2);
        assertThat(inserted).extracting(SubtitleTranslationSegment::getSegmentIndex).containsExactly(12, 18);
        assertThat(inserted).extracting(SubtitleTranslationSegment::getStartMillis).containsExactly(0L, 1000L);
    }

    @Test
    void alignedModeRejectsMixedLocalAndOriginalIndexesWithoutWrites() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(10, 0, 900, "zero"),
            sourceSegment(11, 1000, 1900, "one"),
            sourceSegment(12, 2000, 2900, "two")
        ));
        fakeLlmProvider.nextContents(alignedJsonWithIndexes(
            new int[] {0, 11, 2},
            "\u8bd1\u96f6",
            "\u8bd1\u4e00",
            "\u8bd1\u4e8c"
        ));

        assertThatThrownBy(() -> translationService.translateTaskSubtitlesWithAiCallRecord(command()))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                assertThat(((BusinessException) error).errorCode()).isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
                assertThat(error.getMessage()).contains("INCONSISTENT_INDEX");
            });
        assertThat(fakeLlmProvider.requests).hasSize(1);
        verify(translationMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(fullTextResultMapper, never()).insert(any(TaskFullTextResult.class));
    }

    @Test
    void missingSegmentResponseSplitsBatchAndPersistsCompleteCoverage() {
        translationService = fullTextTranslationService();
        List<SubtitleSegment> sources = List.of(
            sourceSegment(0, 0, 900, "zero"),
            sourceSegment(1, 1000, 1900, "one"),
            sourceSegment(2, 2000, 2900, "two"),
            sourceSegment(3, 3000, 3900, "three")
        );
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sources);
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(
            alignedJson("\u8bd1\u96f6", "\u8bd1\u4e00"),
            alignedJson("\u8bd1\u96f6", "\u8bd1\u4e00"),
            alignedJson("\u8bd1\u4e8c", "\u8bd1\u4e09")
        );

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(4);
        assertThat(fakeLlmProvider.requests).extracting(request -> request.metadata().get("sourceSegmentCount"))
            .containsExactly(4, 2, 2);
        assertThat(captureInsertedSegments(4)).extracting(SubtitleTranslationSegment::getSegmentIndex)
            .containsExactly(0, 1, 2, 3);
    }

    @Test
    void duplicateIndexResponseSplitsBatchAndPersistsCompleteCoverage() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(
            alignedJsonWithIndexes(new int[] {0, 0}, "\u91cd\u590d\u96f6", "\u91cd\u590d\u96f6"),
            alignedJson("\u8bd1\u96f6"),
            alignedJson("\u8bd1\u4e00")
        );

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(2);
        assertThat(fakeLlmProvider.requests).hasSize(3);
        assertThat(captureInsertedSegments(2)).extracting(SubtitleTranslationSegment::getTranslatedText)
            .containsExactly("\u8bd1\u96f6", "\u8bd1\u4e00");
    }

    @Test
    void incompleteJsonSplitsBatchAndPersistsCompleteCoverage() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(
            "{\"segments\":[{\"index\":0,\"text\":\"\u8bd1\u96f6\"}",
            alignedJson("\u8bd1\u96f6"),
            alignedJson("\u8bd1\u4e00")
        );

        assertThat(translationService.translateTaskSubtitlesWithAiCallRecord(command()).savedCount()).isEqualTo(2);
        assertThat(fakeLlmProvider.requests).hasSize(3);
    }

    @Test
    void invalidJsonFailsWithoutBlindRetryOrWrites() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        fakeLlmProvider.nextContents("{not-json}");

        assertThatThrownBy(() -> translationService.translateTaskSubtitlesWithAiCallRecord(command()))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> assertThat(error.getMessage()).contains("JSON_PARSE_ERROR"));
        assertThat(fakeLlmProvider.requests).hasSize(1);
        verify(translationMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
    }

    @Test
    void truncatedSingleLongSegmentSplitsNaturalPiecesAndPersistsOneSegment() {
        SubtitleTranslationProperties properties = new SubtitleTranslationProperties();
        FullText fullText = new FullText();
        fullText.setEnabled(true);
        fullText.setSingleSegmentMaxPieceChars(12);
        fullText.setSingleSegmentMinPieceChars(5);
        properties.setFullText(fullText);
        translationService = fullTextTranslationService(properties);
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(7, 0, 2900, "first part. second part. third part.")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextOutcomes(
            llmResult("", "length", 10, 5, 2),
            llmResult(alignedJson("\u7b2c\u4e00\u6bb5"), "stop", 2, 1, 2),
            llmResult(alignedJson("\u7b2c\u4e8c\u6bb5"), "stop", 2, 1, 1),
            llmResult(alignedJson("\u7b2c\u4e09\u6bb5"), "stop", 2, 1, 1)
        );

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(1);
        assertThat(fakeLlmProvider.requests).hasSize(4);
        SubtitleTranslationSegment inserted = captureInsertedSegments(1).getFirst();
        assertThat(inserted.getSegmentIndex()).isEqualTo(7);
        assertThat(inserted.getTranslatedText()).isEqualTo("\u7b2c\u4e00\u6bb5 \u7b2c\u4e8c\u6bb5 \u7b2c\u4e09\u6bb5");
    }

    @Test
    void unauthorizedProviderFailureDoesNotSplitOrWrite() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        fakeLlmProvider.nextOutcomes(new LlmProviderException("401 unauthorized"));

        assertThatThrownBy(() -> translationService.translateTaskSubtitlesWithAiCallRecord(command()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AI_PROVIDER_FAILED);
        assertThat(fakeLlmProvider.requests).hasSize(1);
        verify(translationMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(fullTextResultMapper, never()).insert(any(TaskFullTextResult.class));
    }

    @Test
    void chineseSourceSkipPersistsAlignedSegmentsAndDerivedFullTextWithoutLlm() {
        translationService = fullTextTranslationService();
        List<SubtitleSegment> sources = List.of(
            sourceSegment(0, 0, 900, "\u4e2d\u6587\u8bfe\u7a0b\u5185\u5bb9".repeat(10)),
            sourceSegment(1, 1000, 1900, "\u4e2d\u6587\u5b57\u5e55\u5185\u5bb9".repeat(10))
        );
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sources);
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(
            command("task_1", 42L, "zh-CN", "zh-CN", "req_1")
        );

        assertThat(result.savedCount()).isEqualTo(2);
        assertThat(result.inputUnits()).isEqualTo(2);
        assertThat(result.outputUnits()).isEqualTo(2);
        assertThat(result.provider()).isEqualTo("source");
        assertThat(fakeLlmProvider.requests).isEmpty();
        assertThat(captureInsertedSegments(2)).extracting(SubtitleTranslationSegment::getTranslatedText)
            .containsExactly(sources.get(0).getText(), sources.get(1).getText());
        verify(fullTextResultMapper).insert(any(TaskFullTextResult.class));
    }

    @Test
    void chineseSourceTargetingEnglishStillCallsProvider() {
        translationService = fullTextTranslationService();
        List<SubtitleSegment> sources = List.of(
            sourceSegment(0, 0, 900, "\u4e2d\u6587\u8bfe\u7a0b\u5185\u5bb9".repeat(10)),
            sourceSegment(1, 1000, 1900, "\u4e2d\u6587\u5b57\u5e55\u5185\u5bb9".repeat(10))
        );
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sources);
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJson("translated course content", "translated subtitle content"));

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(
            command("task_1", 42L, "zh-CN", "en", "req_1")
        );

        assertThat(result.savedCount()).isEqualTo(2);
        assertThat(result.provider()).isEqualTo("fake");
        assertThat(fakeLlmProvider.requests).hasSize(1);
        assertThat(captureInsertedSegments(2)).extracting(SubtitleTranslationSegment::getTranslatedText)
            .containsExactly("translated course content", "translated subtitle content");
    }

    @Test
    void chineseLookingTextWithNonChineseSourceLanguageStillCallsProvider() {
        translationService = fullTextTranslationService();
        List<SubtitleSegment> sources = List.of(
            sourceSegment(0, 0, 900, "\u4e2d\u6587\u8bfe\u7a0b\u5185\u5bb9".repeat(10)),
            sourceSegment(1, 1000, 1900, "\u4e2d\u6587\u5b57\u5e55\u5185\u5bb9".repeat(10))
        );
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sources);
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJson("\u8bd1\u6587\u5185\u5bb9\u4e00", "\u8bd1\u6587\u5185\u5bb9\u4e8c"));

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(2);
        assertThat(result.provider()).isEqualTo("fake");
        assertThat(fakeLlmProvider.requests).hasSize(1);
    }

    @Test
    void providerOriginalIndexOrderIsRestoredBeforePersistenceAndFullTextDerivation() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(18, 1000, 1900, "world"),
            sourceSegment(12, 0, 900, "hello")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJsonWithIndexes(
            new int[] {18, 12},
            "\u8bd1\u6587\u5341\u516b",
            "\u8bd1\u6587\u5341\u4e8c"
        ));

        translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(captureInsertedSegments(2))
            .extracting(SubtitleTranslationSegment::getSegmentIndex, SubtitleTranslationSegment::getTranslatedText)
            .containsExactly(
                org.assertj.core.groups.Tuple.tuple(12, "\u8bd1\u6587\u5341\u4e8c"),
                org.assertj.core.groups.Tuple.tuple(18, "\u8bd1\u6587\u5341\u516b")
            );
        ArgumentCaptor<TaskFullTextResult> fullTextCaptor = ArgumentCaptor.forClass(TaskFullTextResult.class);
        verify(fullTextResultMapper).insert(fullTextCaptor.capture());
        assertThat(fullTextCaptor.getValue().getTranslatedFullText())
            .isEqualTo("\u8bd1\u6587\u5341\u4e8c\n\n\u8bd1\u6587\u5341\u516b");
    }

    @Test
    void providerFailureInMiddleBatchLeavesExistingTranslationOutputsUntouched() {
        SubtitleTranslationProperties properties = new SubtitleTranslationProperties();
        FullText fullText = new FullText();
        fullText.setEnabled(true);
        fullText.setBatchMaxSegments(1);
        properties.setFullText(fullText);
        translationService = fullTextTranslationService(properties);
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 900, "zero"),
            sourceSegment(1, 1000, 1900, "one"),
            sourceSegment(2, 2000, 2900, "two")
        ));
        fakeLlmProvider.nextOutcomes(
            llmResult(alignedJson("\u8bd1\u96f6"), "stop", 3, 2, 1),
            new LlmProviderException("provider unavailable")
        );

        assertThatThrownBy(() -> translationService.translateTaskSubtitlesWithAiCallRecord(command()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AI_PROVIDER_FAILED);

        assertThat(fakeLlmProvider.requests).hasSize(2);
        verify(translationMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(translationMapper, never()).insert(any(SubtitleTranslationSegment.class));
        verify(fullTextResultMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(fullTextResultMapper, never()).insert(any(TaskFullTextResult.class));
    }

    @Test
    void repeatedFullTextTranslationReplacesScopedOutputsDeterministically() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(
            alignedJson("\u8bd1\u6587\u96f6", "\u8bd1\u6587\u4e00"),
            alignedJson("\u8bd1\u6587\u96f6", "\u8bd1\u6587\u4e00")
        );

        SubtitleTranslationAiCallResult first = translationService.translateTaskSubtitlesWithAiCallRecord(command());
        SubtitleTranslationAiCallResult second = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(first.savedCount()).isEqualTo(2);
        assertThat(second.savedCount()).isEqualTo(2);
        verify(translationMapper, org.mockito.Mockito.times(2))
            .deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN");
        verify(fullTextResultMapper, org.mockito.Mockito.times(2))
            .deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN");
        assertThat(captureInsertedSegments(4)).extracting(SubtitleTranslationSegment::getSegmentIndex)
            .containsExactly(0, 1, 0, 1);
    }

    @Test
    void aiUsageAggregatesEveryProviderBatchIncludingSplitTriggerResponse() {
        translationService = fullTextTranslationService();
        List<SubtitleSegment> sources = List.of(
            sourceSegment(0, 0, 900, "zero"),
            sourceSegment(1, 1000, 1900, "one"),
            sourceSegment(2, 2000, 2900, "two"),
            sourceSegment(3, 3000, 3900, "three")
        );
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sources);
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextOutcomes(
            llmResult(alignedJson("\u8bd1\u96f6"), "stop", 10, 5, 2),
            llmResult(alignedJson("\u8bd1\u96f6", "\u8bd1\u4e00"), "stop", 3, 2, 4),
            llmResult(alignedJson("\u8bd1\u4e8c", "\u8bd1\u4e09"), "stop", 3, 2, 6)
        );

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.duration()).isEqualTo(Duration.ofMillis(12));
        assertThat(result.promptTokens()).isEqualTo(16);
        assertThat(result.completionTokens()).isEqualTo(9);
        assertThat(result.totalTokens()).isEqualTo(25);
        assertThat(fakeLlmProvider.requests).hasSize(3);
    }

    @Test
    void alignedParserRejectsIncompleteUnknownExtraMixedInvalidAndSensitiveOutputs() {
        SubtitleTranslationResponseParser parser = new SubtitleTranslationResponseParser();
        List<SubtitleSegment> twoSources = List.of(
            sourceSegment(10, 0, 900, "zero"),
            sourceSegment(11, 1000, 1900, "one")
        );
        List<String> invalidResponses = List.of(
            "{\"segments\":[{\"index\":0,\"text\":\"zero\"}]}",
            "{\"segments\":[{\"index\":0,\"text\":\"zero\"},{\"index\":999,\"text\":\"unknown\"}]}",
            "{\"segments\":[{\"index\":0,\"text\":\"zero\"},{\"index\":1,\"text\":\"one\"},{\"index\":2,\"text\":\"extra\"}]}",
            "{\"segments\":[{\"index\":0,\"text\":\"zero\"},{\"index\":0,\"text\":\"duplicate\"}]}",
            "{\"segments\":[{\"index\":0,\"text\":\" \"},{\"index\":1,\"text\":\"one\"}]}",
            "{\"segments\":[{\"index\":0,\"text\":42},{\"index\":1,\"text\":\"one\"}]}",
            "{\"segments\":[{\"index\":0},{\"index\":1,\"text\":\"one\"}]}",
            "{\"segments\":[{\"index\":0,\"text\":\"Authorization: Bearer secret\"},{\"index\":1,\"text\":\"one\"}]}",
            "{not-json}"
        );
        for (String response : invalidResponses) {
            assertThatThrownBy(() -> parser.parse(response, twoSources))
                .isInstanceOf(BusinessException.class)
                .extracting("errorCode")
                .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        List<SubtitleSegment> threeSources = List.of(
            sourceSegment(10, 0, 900, "zero"),
            sourceSegment(11, 1000, 1900, "one"),
            sourceSegment(12, 2000, 2900, "two")
        );
        assertThatThrownBy(() -> parser.parse(
            alignedJsonWithIndexes(new int[] {0, 11, 2}, "zero", "one", "two"),
            threeSources
        )).isInstanceOf(BusinessException.class)
            .satisfies(error -> assertThat(error.getMessage()).contains("INCONSISTENT_INDEX"));
    }

    @Test
    void nonStringTextResponseSplitsBatchAndRecoversCompleteCoverage() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(
            "{\"segments\":[{\"index\":0,\"text\":42},{\"index\":1,\"text\":\"one\"}]}",
            alignedJson("\u8bd1\u96f6"),
            alignedJson("\u8bd1\u4e00")
        );

        assertThat(translationService.translateTaskSubtitlesWithAiCallRecord(command()).savedCount()).isEqualTo(2);
        assertThat(fakeLlmProvider.requests).hasSize(3);
        assertThat(captureInsertedSegments(2)).extracting(SubtitleTranslationSegment::getSegmentIndex)
            .containsExactly(0, 1);
    }

    @Test
    void splitDepthExhaustionFailsWithoutDeletingOrPersistingPartialOutputs() {
        SubtitleTranslationProperties properties = new SubtitleTranslationProperties();
        FullText fullText = new FullText();
        fullText.setEnabled(true);
        fullText.setSingleSegmentMaxPieceChars(12);
        fullText.setSingleSegmentMinPieceChars(5);
        fullText.setSingleSegmentMaxDepth(1);
        properties.setFullText(fullText);
        translationService = fullTextTranslationService(properties);
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(7, 0, 2900, "first part. second part. third part.")
        ));
        fakeLlmProvider.nextOutcomes(
            llmResult("", "length", 10, 5, 2),
            llmResult("", "length", 6, 3, 4)
        );

        assertThatThrownBy(() -> translationService.translateTaskSubtitlesWithAiCallRecord(command()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AI_PROVIDER_FAILED);
        assertThat(fakeLlmProvider.requests).hasSize(2);
        verify(translationMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(translationMapper, never()).insert(any(SubtitleTranslationSegment.class));
        verify(fullTextResultMapper, never()).insert(any(TaskFullTextResult.class));
    }

    @Test
    void fullTextModeAppliesFullTextTranslationRoute() {
        SubtitleTranslationProperties properties = new SubtitleTranslationProperties();
        FullText fullText = new FullText();
        fullText.setEnabled(true);
        properties.setFullText(fullText);
        translationService = new SubtitleTranslationServiceImpl(
            sourceMapper,
            translationMapper,
            fullTextResultMapper,
            fakeLlmProvider,
            FIXED_CLOCK,
            new SubtitleTranslationResponseParser(),
            properties,
            routedRequestFactory()
        );
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJson("译文零", "译文一"));

        translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(fakeLlmProvider.requests.getFirst().metadata())
            .containsEntry(AiModelRoutedLlmRequestFactory.METADATA_STAGE, AiModelStage.TRANSLATION_FULL_TEXT.name())
            .containsEntry(AiModelRoutedLlmRequestFactory.METADATA_PROFILE_CODE, "deepseek-text");
    }

    @Test
    void fullTextModeRejectsNonChineseAlignedOutputWithoutPartialPersistence() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 10_000, "Spring Boot course introduction")
        ));
        fakeLlmProvider.nextContents(
            alignedJson("Spring Boot course introduction"),
            alignedJson("Spring Boot course introduction")
        );

        assertThatThrownBy(() -> translationService.translateTaskSubtitlesWithAiCallRecord(command()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AI_PROVIDER_FAILED);
        assertThat(fakeLlmProvider.requests).hasSize(2);
        verify(translationMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(fullTextResultMapper, never()).insert(any(TaskFullTextResult.class));
    }

    @Test
    void fullTextModeAcceptsChineseTranslationThatKeepsTechnicalTermsInEnglish() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 10_000, "Spring Boot and Docker deployment")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJson(
            "\u672c\u8bfe\u7a0b\u4ecb\u7ecd Spring Boot \u548c Docker \u90e8\u7f72\uff0c\u5e76\u8bf4\u660e API Gateway \u7684\u7528\u6cd5\u3002"
        ));

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(1);
        verify(fullTextResultMapper).insert(any(TaskFullTextResult.class));
    }

    @Test
    void fullTextModeUsesConfiguredTimeoutMaxTokensAndSingleRequestFor53322Chars() {
        SubtitleTranslationProperties properties = new SubtitleTranslationProperties();
        FullText fullText = new FullText();
        fullText.setEnabled(true);
        fullText.setRequestTimeout(Duration.ofSeconds(900));
        fullText.setMaxTokens(32_768);
        properties.setFullText(fullText);
        translationService = fullTextTranslationService(properties);
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 10_000, "a".repeat(53_322))
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJson(
            "\u8fd9\u662f\u4e00\u6bb5\u5b8c\u6574\u7684\u4e2d\u6587\u8bd1\u6587\uff0c\u7528\u4e8e\u9a8c\u8bc1\u957f\u6587\u672c\u5355\u6b21\u8bf7\u6c42\u3002"
        ));

        translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(fakeLlmProvider.requests).hasSize(1);
        LlmRequest request = fakeLlmProvider.requests.getFirst();
        assertThat(request.timeout()).isEqualTo(Duration.ofSeconds(900));
        assertThat(request.maxTokens()).isEqualTo(32_768);
        assertThat(request.temperature()).isEqualTo(0.1);
        assertThat(request.metadata()).containsEntry("translationMode", "alignedBatch");
        assertThat(request.metadata()).containsEntry("sourceSegmentCount", 1);
        assertThat(promptChars(request)).isGreaterThan(53_322);
    }

    @Test
    void fullTextModeBuildsDeterministicBatchesFromSegmentAndInputLimits() {
        SubtitleTranslationProperties properties = new SubtitleTranslationProperties();
        FullText fullText = new FullText();
        fullText.setEnabled(true);
        fullText.setBatchMaxSegments(2);
        fullText.setBatchMaxInputChars(10);
        properties.setFullText(fullText);
        translationService = fullTextTranslationService(properties);
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 900, "aaaaaa"),
            sourceSegment(1, 1000, 1900, "bbbbbb"),
            sourceSegment(2, 2000, 2900, "cccccc")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(
            alignedJson("\u7b2c\u4e00\u6bb5\u8bd1\u6587"),
            alignedJson("\u7b2c\u4e8c\u6bb5\u8bd1\u6587"),
            alignedJson("\u7b2c\u4e09\u6bb5\u8bd1\u6587")
        );

        translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(fakeLlmProvider.requests).hasSize(3);
        assertThat(fakeLlmProvider.requests)
            .extracting(request -> request.metadata().get("sourceSegmentCount"))
            .containsExactly(1, 1, 1);
    }

    @Test
    void fullTextModeUsesSafeDefaultsForInvalidConfigValues() {
        SubtitleTranslationProperties properties = new SubtitleTranslationProperties();
        FullText fullText = new FullText();
        fullText.setEnabled(true);
        fullText.setRequestTimeout(Duration.ZERO);
        fullText.setMaxTokens(-1);
        fullText.setBatchMaxSegments(-1);
        fullText.setBatchMaxInputChars(-1);
        properties.setFullText(fullText);
        translationService = fullTextTranslationService(properties);
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 10_000, "a".repeat(53_322))
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJson(
            "\u8fd9\u662f\u4e00\u6bb5\u6709\u6548\u7684\u4e2d\u6587\u8bd1\u6587\uff0c\u7528\u4e8e\u9a8c\u8bc1\u975e\u6cd5\u914d\u7f6e\u7684\u5b89\u5168\u9ed8\u8ba4\u503c\u3002"
        ));

        translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(fakeLlmProvider.requests).hasSize(1);
        LlmRequest request = fakeLlmProvider.requests.getFirst();
        assertThat(request.timeout()).isEqualTo(Duration.ofSeconds(900));
        assertThat(request.maxTokens()).isEqualTo(32_768);
        assertThat(request.metadata()).containsEntry("sourceSegmentCount", 1);
    }

    @Test
    void fullTextModeCapsConfiguredMaxTokensAtProviderValidatorLimit() {
        SubtitleTranslationProperties properties = new SubtitleTranslationProperties();
        FullText fullText = new FullText();
        fullText.setEnabled(true);
        fullText.setMaxTokens(99_999);
        properties.setFullText(fullText);
        translationService = fullTextTranslationService(properties);
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 10_000, "Spring Boot and Docker deployment")
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJson(
            "\u672c\u8bfe\u7a0b\u4ecb\u7ecd Spring Boot \u548c Docker \u90e8\u7f72\u3002"
        ));

        translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(fakeLlmProvider.requests.getFirst().maxTokens()).isEqualTo(LlmRequestValidator.MAX_TOKENS);
    }

    @Test
    void normalSubtitleBatchTranslationKeepsLegacyRequestSettingsWhenFullTextDisabled() {
        SubtitleTranslationProperties properties = new SubtitleTranslationProperties();
        FullText fullText = new FullText();
        fullText.setEnabled(false);
        fullText.setRequestTimeout(Duration.ofSeconds(900));
        fullText.setMaxTokens(32_768);
        properties.setFullText(fullText);
        translationService = fullTextTranslationService(properties);
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        fakeLlmProvider.nextContents("translated zero", "translated one");

        translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(fakeLlmProvider.requests).hasSize(2);
        assertThat(fakeLlmProvider.requests)
            .extracting(LlmRequest::timeout)
            .containsOnly(Duration.ofSeconds(60));
        assertThat(fakeLlmProvider.requests)
            .extracting(LlmRequest::maxTokens)
            .containsOnly(4096);
    }

    @Test
    void fullTextModeFailsNonChineseSemanticValidationWithoutSavingEitherOutput() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 10_000, "Spring Boot course introduction")
        ));
        fakeLlmProvider.nextContents(
            alignedJson("Spring Boot course introduction"),
            alignedJson("Spring Boot course introduction")
        );

        assertThatThrownBy(() -> translationService.translateTaskSubtitlesWithAiCallRecord(command()))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                BusinessException exception = (BusinessException) error;
                assertThat(exception.errorCode()).isEqualTo(ErrorCode.AI_PROVIDER_FAILED);
                assertThat(exception.getMessage()).contains("untranslated text");
            });
        assertThat(fakeLlmProvider.requests).hasSize(2);
        verify(translationMapper, never()).insert(any(SubtitleTranslationSegment.class));
        verify(fullTextResultMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(fullTextResultMapper, never()).insert(any(TaskFullTextResult.class));
    }

    @Test
    void fullTextModeFailsWhenTranslatedFullTextIsHighlySimilarToSource() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 10_000, "Spring Boot course introduction")
        ));
        fakeLlmProvider.nextContents(
            alignedJson("Spring Boot course introduction"),
            alignedJson("Spring Boot course introduction")
        );

        assertThatThrownBy(() -> translationService.translateTaskSubtitlesWithAiCallRecord(command()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AI_PROVIDER_FAILED);
        verify(fullTextResultMapper, never()).insert(any(TaskFullTextResult.class));
    }

    @Test
    void singleSegmentPlainTextSavesOriginalIndex() {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(sourceSegment(7, 2000, 2900, "hello")));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        fakeLlmProvider.nextContents("translated text");

        int saved = translationService.translateTaskSubtitles(command());

        assertThat(saved).isEqualTo(1);
        List<SubtitleTranslationSegment> inserted = captureInsertedSegments(1);
        assertThat(inserted.getFirst().getSegmentIndex()).isEqualTo(7);
        assertThat(inserted.getFirst().getTranslatedText()).isEqualTo("translated text");
    }

    @Test
    void plainTextWithWhitespaceIsTrimmedBeforeSave() {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(sourceSegment(0, 0, 900, "hello")));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        fakeLlmProvider.nextContents("  translated text  \n");

        int saved = translationService.translateTaskSubtitles(command());

        assertThat(saved).isEqualTo(1);
        assertThat(captureInsertedSegments(1).getFirst().getTranslatedText()).isEqualTo("translated text");
    }

    @Test
    void markdownFenceIsRemovedBeforeSave() {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(sourceSegment(0, 0, 900, "hello")));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        fakeLlmProvider.nextContents("""
            ```text
            translated text
            ```
            """);

        int saved = translationService.translateTaskSubtitles(command());

        assertThat(saved).isEqualTo(1);
        assertThat(captureInsertedSegments(1).getFirst().getTranslatedText()).isEqualTo("translated text");
    }

    @Test
    void blankPlainTextResponseFailsAsEmptyResponseWithoutSave() {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(sourceSegment(0, 0, 900, "hello")));
        fakeLlmProvider.nextContents("   \n");

        assertThatThrownBy(() -> translationService.translateTaskSubtitles(command()))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                assertThat(((BusinessException) error).errorCode()).isEqualTo(ErrorCode.AI_PROVIDER_FAILED);
                assertThat(error.getMessage()).contains("EMPTY_RESPONSE");
            });
        verify(translationMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(translationMapper, never()).insert(any(SubtitleTranslationSegment.class));
    }

    @Test
    void providerOrchestrationStaysOutsideTransactionAndFinalWritesUseDedicatedTransactions() throws Exception {
        Transactional annotation = SubtitleTranslationServiceImpl.class
            .getMethod("translateTaskSubtitles", TranslateSubtitleCommand.class)
            .getAnnotation(Transactional.class);
        Transactional resultAnnotation = SubtitleTranslationServiceImpl.class
            .getMethod("translateTaskSubtitlesWithAiCallRecord", TranslateSubtitleCommand.class)
            .getAnnotation(Transactional.class);
        Class<?> persistenceType = Class.forName(
            "com.example.courselingo.subtitle.service.SubtitleTranslationPersistenceService"
        );
        Transactional segmentWrite = persistenceType
            .getDeclaredMethod("replaceSegmentTranslations", String.class, Long.class, String.class, List.class)
            .getAnnotation(Transactional.class);
        Transactional dualWrite = persistenceType
            .getDeclaredMethod(
                "replaceDualOutput",
                String.class,
                Long.class,
                String.class,
                List.class,
                TaskFullTextResult.class
            )
            .getAnnotation(Transactional.class);

        assertThat(annotation).isNull();
        assertThat(resultAnnotation).isNull();
        assertThat(segmentWrite).isNotNull();
        assertThat(dualWrite).isNotNull();
    }

    @Test
    void queryReturnsOwnerScopedTranslationsWithoutUserIdAndInMapperOrder() {
        when(translationMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN")).thenReturn(List.of(
            translation("task_1", 42L, "zh-CN", 0, "你好"),
            translation("task_1", 42L, "zh-CN", 1, "世界")
        ));
        when(translationMapper.countByTaskIdAndLanguage("task_1", 42L, "zh-CN")).thenReturn(2L);

        List<SubtitleTranslationSegmentView> views = queryService.listTranslations("task_1", 42L, "zh-CN");

        assertThat(views).extracting(SubtitleTranslationSegmentView::segmentIndex).containsExactly(0, 1);
        assertThat(views).extracting(SubtitleTranslationSegmentView::translatedText).containsExactly("你好", "世界");
        assertThat(views).extracting(SubtitleTranslationSegmentView::sourceLanguage).containsOnly("en");
        assertThat(views).extracting(SubtitleTranslationSegmentView::targetLanguage).containsOnly("zh-CN");
        assertThat(views).extracting(SubtitleTranslationSegmentView::provider).containsOnly("fake");
        assertThat(queryService.countByTaskIdAndLanguage("task_1", 42L, "zh-CN")).isEqualTo(2L);
    }

    @Test
    void deleteTranslationsIsScopedByTaskUserAndTargetLanguage() {
        when(translationMapper.deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN")).thenReturn(2);

        int deleted = translationService.deleteTranslations("task_1", 42L, "zh-CN");

        assertThat(deleted).isEqualTo(2);
        verify(translationMapper).deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN");
    }

    @Test
    void overwriteDoesNotDeleteOtherUsersOrOtherTargetLanguages() {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        fakeLlmProvider.nextContents("translated zero", "translated one");

        translationService.translateTaskSubtitles(command());

        verify(translationMapper).deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN");
        verify(translationMapper, never()).deleteByTaskIdUserIdAndTargetLanguage("task_1", 43L, "zh-CN");
        verify(translationMapper, never()).deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "ja-JP");
    }

    @Test
    void sameSourceAndTargetLanguageIsAllowedForProviderNormalization() {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        fakeLlmProvider.nextContents("hello", "world");

        int saved = translationService.translateTaskSubtitles(command("task_1", 42L, "en", "en", "req_1"));

        assertThat(saved).isEqualTo(2);
        verify(translationMapper).deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "en");
    }

    @Test
    void invalidCommandAndMissingSourceFailBeforeLlmAndDelete() {
        assertValidationFailure(() -> translationService.translateTaskSubtitles(null));
        assertValidationFailure(() -> translationService.translateTaskSubtitles(command("", 42L, "en", "zh-CN", "req_1")));
        assertValidationFailure(() -> translationService.translateTaskSubtitles(command("task_1", null, "en", "zh-CN", "req_1")));
        assertValidationFailure(() -> translationService.translateTaskSubtitles(command("task_1", 42L, " ", "zh-CN", "req_1")));
        assertValidationFailure(() -> translationService.translateTaskSubtitles(command("task_1", 42L, "en", " ", "req_1")));
        assertValidationFailure(() -> translationService.translateTaskSubtitles(command("task_1", 42L, "en", "zh-CN", " ")));
        assertValidationFailure(() -> translationService.translateTaskSubtitles(command("task_1", 42L, "x".repeat(33), "zh-CN", "req_1")));
        assertValidationFailure(() -> translationService.translateTaskSubtitles(command("task_1", 42L, "en", "x".repeat(33), "req_1")));
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        assertValidationFailure(() -> translationService.translateTaskSubtitles(command()));

        assertThat(fakeLlmProvider.requests).isEmpty();
        verify(translationMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(translationMapper, never()).insert(any(SubtitleTranslationSegment.class));
    }

    @Test
    void invalidSourceSegmentsProviderAndLlmResponsesFailWithoutPartialSave() {
        assertValidationFailure(() -> translateWithSources(List.of(sourceSegment(-1, 0, 1, "text")), okJson()));
        assertValidationFailure(() -> translateWithSources(List.of(sourceSegment(0, -1, 1, "text")), okJson()));
        assertValidationFailure(() -> translateWithSources(List.of(sourceSegment(0, 2, 1, "text")), okJson()));
        assertValidationFailure(() -> translateWithSources(List.of(sourceSegment(0, 0, 1, " ")), okJson()));
        fakeLlmProvider.providerName = "x".repeat(65);
        assertValidationFailure(() -> translateWithSources(sourceSegments(), okJson()));
        fakeLlmProvider.providerName = "fake";
        assertProviderFailure(() -> translateWithSources(sourceSegments(), "ok", " "));
        verify(translationMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(translationMapper, never()).insert(any(SubtitleTranslationSegment.class));
    }

    @Test
    void batchInsertFailureRaisesInternalErrorSoTransactionCanRollback() {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1, 0);
        fakeLlmProvider.nextContents("translated zero", "translated one");

        assertThatThrownBy(() -> translationService.translateTaskSubtitles(command()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_INTERNAL_ERROR);
    }

    @Test
    void fullTextInsertFailureRaisesInternalErrorAfterSegmentWritesSoTransactionRollsBackBothOutputs() {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments());
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(0);
        fakeLlmProvider.nextContents(alignedJson("\u8bd1\u96f6", "\u8bd1\u4e00"));

        assertThatThrownBy(() -> translationService.translateTaskSubtitlesWithAiCallRecord(command()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_INTERNAL_ERROR);

        verify(translationMapper, org.mockito.Mockito.times(2)).insert(any(SubtitleTranslationSegment.class));
        verify(fullTextResultMapper).insert(any(TaskFullTextResult.class));
    }

    @Test
    void sensitiveProviderAndParserFailuresDoNotLeakSecrets() {
        fakeLlmProvider.providerName = "Authorization: Bearer token secret api key C:\\Users\\demo\\key.txt /home/demo/key";

        assertThatThrownBy(() -> translateWithSources(sourceSegments(), okJson()))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                assertThat(((BusinessException) error).errorCode()).isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
                assertSafe(error.getMessage());
        });
    }

    @Test
    void legacyProviderFailureUsesSafeBusinessMessage() {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(sourceSegment(0, 0, 900, "hello")));
        fakeLlmProvider.nextOutcomes(new LlmProviderException(
            "Authorization: Bearer token at C:\\Users\\demo\\secret.txt"
        ));

        assertThatThrownBy(() -> translationService.translateTaskSubtitles(command()))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                assertThat(((BusinessException) error).errorCode()).isEqualTo(ErrorCode.AI_PROVIDER_FAILED);
                assertSafe(error.getMessage());
                assertThat(error.getMessage()).isEqualTo("Subtitle translation provider failed");
            });
        verify(translationMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
    }

    @Test
    void boundariesDoNotCallExternalProvidersRunnerMqArtifactsOrFrontend() throws Exception {
        String source = readJavaSources("src/main/java/com/example/courselingo/subtitle");

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

    private void assertChineseTranslationWithProductNameDoesNotRetry(String sourceText, String translatedText) {
        translationService = fullTextTranslationService();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            sourceSegment(0, 0, 3000, sourceText)
        ));
        when(translationMapper.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(fullTextResultMapper.insert(any(TaskFullTextResult.class))).thenReturn(1);
        fakeLlmProvider.nextContents(alignedJson(translatedText));

        SubtitleTranslationAiCallResult result = translationService.translateTaskSubtitlesWithAiCallRecord(command());

        assertThat(result.savedCount()).isEqualTo(1);
        assertThat(fakeLlmProvider.requests).hasSize(1);
        assertThat(captureInsertedSegments(1).getFirst().getTranslatedText()).isEqualTo(translatedText);
    }

    private void translateWithSources(List<SubtitleSegment> sourceSegments, String... contents) {
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(sourceSegments);
        fakeLlmProvider.nextContents(contents);
        translationService.translateTaskSubtitles(command());
    }

    private List<SubtitleTranslationSegment> captureInsertedSegments(int count) {
        ArgumentCaptor<SubtitleTranslationSegment> captor = ArgumentCaptor.forClass(SubtitleTranslationSegment.class);
        verify(translationMapper, org.mockito.Mockito.times(count)).insert(captor.capture());
        return captor.getAllValues();
    }

    private static TranslateSubtitleCommand command() {
        return command("task_1", 42L, "en", "zh-CN", "req_1");
    }

    private static TranslateSubtitleCommand command(
        String taskId,
        Long userId,
        String sourceLanguage,
        String targetLanguage,
        String requestId
    ) {
        return new TranslateSubtitleCommand(taskId, userId, sourceLanguage, targetLanguage, requestId);
    }

    private static List<SubtitleSegment> sourceSegments() {
        return List.of(
            sourceSegment(0, 0, 900, "hello"),
            sourceSegment(1, 1000, 1900, "world")
        );
    }

    private SubtitleTranslationServiceImpl fullTextTranslationService() {
        SubtitleTranslationProperties properties = new SubtitleTranslationProperties();
        FullText fullText = new FullText();
        fullText.setEnabled(true);
        properties.setFullText(fullText);
        return fullTextTranslationService(properties);
    }

    private SubtitleTranslationServiceImpl fullTextTranslationService(SubtitleTranslationProperties properties) {
        return new SubtitleTranslationServiceImpl(
            sourceMapper,
            translationMapper,
            fullTextResultMapper,
            fakeLlmProvider,
            FIXED_CLOCK,
            new SubtitleTranslationResponseParser(),
            properties
        );
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

    private static int promptChars(LlmRequest request) {
        return request.messages().stream()
            .mapToInt(message -> message.content().length())
            .sum();
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

    private static SubtitleTranslationSegment translation(
        String taskId,
        Long userId,
        String targetLanguage,
        int index,
        String text
    ) {
        SubtitleTranslationSegment segment = new SubtitleTranslationSegment();
        segment.setTaskId(taskId);
        segment.setUserId(userId);
        segment.setSegmentIndex(index);
        segment.setStartMillis(index * 1000L);
        segment.setEndMillis(index * 1000L + 900L);
        segment.setSourceLanguage("en");
        segment.setTargetLanguage(targetLanguage);
        segment.setTranslatedText(text);
        segment.setProvider("fake");
        segment.setCreatedAt(now());
        segment.setUpdatedAt(now());
        return segment;
    }

    private static String okJson() {
        return "{\"segments\":[{\"index\":0,\"text\":\"你好\"},{\"index\":1,\"text\":\"世界\"}]}";
    }

    private static String alignedJson(String... texts) {
        int[] indexes = java.util.stream.IntStream.range(0, texts.length).toArray();
        return alignedJsonWithIndexes(indexes, texts);
    }

    private static String alignedJsonWithIndexes(int[] indexes, String... texts) {
        assertThat(indexes).hasSameSizeAs(texts);
        StringBuilder json = new StringBuilder("{\"segments\":[");
        for (int index = 0; index < texts.length; index++) {
            if (index > 0) {
                json.append(',');
            }
            json.append("{\"index\":")
                .append(indexes[index])
                .append(",\"text\":\"")
                .append(texts[index].replace("\\", "\\\\").replace("\"", "\\\""))
                .append("\"}");
        }
        return json.append("]}").toString();
    }

    private static LlmResult llmResult(
        String content,
        String finishReason,
        int promptTokens,
        int completionTokens,
        int durationMillis
    ) {
        return new LlmResult(
            "fake",
            "fake-model",
            content,
            finishReason,
            new LlmUsage(promptTokens, completionTokens, promptTokens + completionTokens),
            Duration.ofMillis(durationMillis),
            Map.of()
        );
    }

    private static void assertValidationFailure(ThrowingCallable callable) {
        assertThatThrownBy(callable::call)
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
    }

    private static void assertProviderFailure(ThrowingCallable callable) {
        assertThatThrownBy(callable::call)
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AI_PROVIDER_FAILED);
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

    @FunctionalInterface
    private interface ThrowingCallable {
        void call();
    }

    private static final class FakeLlmProvider implements LlmProvider {

        private final List<LlmRequest> requests = new ArrayList<>();
        private final List<String> queuedContents = new ArrayList<>();
        private final List<Object> queuedOutcomes = new ArrayList<>();
        private String nextContent = okJson();
        private String providerName = "fake";

        private void nextContents(String... contents) {
            queuedContents.clear();
            queuedOutcomes.clear();
            queuedContents.addAll(List.of(contents));
        }

        private void nextOutcomes(Object... outcomes) {
            queuedContents.clear();
            queuedOutcomes.clear();
            queuedOutcomes.addAll(List.of(outcomes));
        }

        @Override
        public LlmResult generate(LlmRequest request) {
            requests.add(request);
            if (!queuedOutcomes.isEmpty()) {
                Object outcome = queuedOutcomes.removeFirst();
                if (outcome instanceof RuntimeException exception) {
                    throw exception;
                }
                return (LlmResult) outcome;
            }
            String content = queuedContents.isEmpty()
                ? nextContent
                : queuedContents.removeFirst();
            return new LlmResult(providerName, "fake-model", content, "stop", null, Duration.ofMillis(1), Map.of());
        }

        @Override
        public String providerName() {
            return providerName;
        }
    }
}
