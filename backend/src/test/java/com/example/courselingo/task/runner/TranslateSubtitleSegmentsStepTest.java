package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.ai.asr.SpeechToTextResult;
import com.example.courselingo.ai.asr.TranscribedSegment;
import com.example.courselingo.ai.llm.LlmProviderFailureType;
import com.example.courselingo.ai.llm.OpenAiCompatibleLlmException;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.subtitle.service.SubtitleTranslationAiCallResult;
import com.example.courselingo.subtitle.service.SubtitleTranslationService;
import com.example.courselingo.subtitle.service.TranslateSubtitleCommand;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class TranslateSubtitleSegmentsStepTest {

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private SubtitleTranslationService subtitleTranslationService;

    private TranslateSubtitleSegmentsStep step;

    @BeforeEach
    void setUp() {
        step = new TranslateSubtitleSegmentsStep(analysisTaskMapper, subtitleTranslationService);
    }

    @Test
    void translateSubtitleSegmentsUsesOwnerScopedTaskAndAsrLanguage() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        when(subtitleTranslationService.translateTaskSubtitlesWithAiCallRecord(any(TranslateSubtitleCommand.class)))
            .thenReturn(new SubtitleTranslationAiCallResult(
                2,
                "fake-llm",
                "fake-translate-model",
                Duration.ofMillis(15),
                11,
                13,
                24,
                2,
                2,
                null,
                null
            ));

        step.execute(contextWithAsrResult(7L));

        ArgumentCaptor<TranslateSubtitleCommand> captor = ArgumentCaptor.forClass(TranslateSubtitleCommand.class);
        verify(subtitleTranslationService).translateTaskSubtitlesWithAiCallRecord(captor.capture());
        TranslateSubtitleCommand command = captor.getValue();
        assertThat(command.taskId()).isEqualTo("task_1");
        assertThat(command.userId()).isEqualTo(7L);
        assertThat(command.sourceLanguage()).isEqualTo("en");
        assertThat(command.targetLanguage()).isEqualTo("zh-CN");
        assertThat(command.requestId()).isEqualTo("req_1");
        assertThat(contextWithAsrResult(7L).pendingAiCallRecords()).isEmpty();
    }

    @Test
    void translateSubtitleSegmentsAddsSafeLlmCallSummary() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        when(subtitleTranslationService.translateTaskSubtitlesWithAiCallRecord(any(TranslateSubtitleCommand.class)))
            .thenReturn(new SubtitleTranslationAiCallResult(
                2,
                "fake-llm",
                "fake-translate-model",
                Duration.ofMillis(15),
                11,
                13,
                24,
                2,
                2,
                null,
                null
            ));
        PipelineAnalysisTaskStepContext context = contextWithAsrResult(7L);

        step.execute(context);

        assertThat(context.pendingAiCallRecords()).singleElement().satisfies(record -> {
            assertThat(record.callType()).isEqualTo(AiCallType.LLM);
            assertThat(record.stage()).isEqualTo(AiCallStage.TRANSLATION);
            assertThat(record.provider()).isEqualTo("fake-llm");
            assertThat(record.model()).isEqualTo("fake-translate-model");
            assertThat(record.durationMillis()).isEqualTo(15L);
            assertThat(record.promptTokens()).isEqualTo(11);
            assertThat(record.completionTokens()).isEqualTo(13);
            assertThat(record.totalTokens()).isEqualTo(24);
            assertThat(record.inputUnits()).isEqualTo(2);
            assertThat(record.outputUnits()).isEqualTo(2);
            assertThat(record.toString()).doesNotContain("hello world");
        });
    }

    @Test
    void translateSubtitleSegmentsRecordsOneSafeFailureAndStopsOnFinalSemanticMismatch() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        when(subtitleTranslationService.translateTaskSubtitlesWithAiCallRecord(any(TranslateSubtitleCommand.class)))
            .thenThrow(new BusinessException(
                ErrorCode.AI_PROVIDER_FAILED,
                "TARGET_LANGUAGE_MISMATCH Subtitle translation provider returned non-Chinese text"
            ));
        PipelineAnalysisTaskStepContext context = contextWithAsrResult(7L);

        assertThatThrownBy(() -> step.execute(context))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AI_PROVIDER_FAILED);

        assertThat(context.pendingAiCallRecords()).singleElement().satisfies(record -> {
            assertThat(record.stage()).isEqualTo(AiCallStage.TRANSLATION);
            assertThat(record.success()).isFalse();
            assertThat(record.errorCode()).isEqualTo("AI_PROVIDER_FAILED");
            assertThat(record.errorMessage()).contains("TARGET_LANGUAGE_MISMATCH");
            assertThat(record.errorMessage()).doesNotContainIgnoringCase("prompt", "response", "token");
        });
    }

    @Test
    void translateSubtitleSegmentsAddsSanitizedFailureRecordWhenLlmServiceFails() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        when(subtitleTranslationService.translateTaskSubtitlesWithAiCallRecord(any(TranslateSubtitleCommand.class)))
            .thenThrow(new IllegalStateException("raw prompt token at C:\\secret\\prompt.txt"));
        PipelineAnalysisTaskStepContext context = contextWithAsrResult(7L);

        assertThatThrownBy(() -> step.execute(context))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("raw prompt token");

        assertThat(context.pendingAiCallRecords()).singleElement().satisfies(record -> {
            assertThat(record.callType()).isEqualTo(AiCallType.LLM);
            assertThat(record.stage()).isEqualTo(AiCallStage.TRANSLATION);
            assertThat(record.provider()).isEqualTo("subtitle-translation-service");
            assertThat(record.errorCode()).isEqualTo("AI_PROVIDER_FAILED");
            assertThat(record.errorMessage()).doesNotContainIgnoringCase("token");
            assertThat(record.errorMessage()).doesNotContain("C:\\secret");
        });
    }

    @Test
    void translateSubtitleSegmentsPreservesTypedProviderFailureInAiCallRecord() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        OpenAiCompatibleLlmException cause = new OpenAiCompatibleLlmException(
            "OpenAI-compatible LLM request failed type=PROVIDER_RATE_LIMIT taskId=task_1 httpStatus=429",
            LlmProviderFailureType.PROVIDER_RATE_LIMIT,
            true,
            429,
            null,
            "openai-compatible",
            "Qwen/Qwen3-8B",
            "https://api.siliconflow.cn/v1/chat/completions",
            123L,
            "trace-1",
            "{\"error\":\"rate limited\"}",
            null,
            null
        );
        when(subtitleTranslationService.translateTaskSubtitlesWithAiCallRecord(any(TranslateSubtitleCommand.class)))
            .thenThrow(new BusinessException(ErrorCode.AI_PROVIDER_FAILED, cause.getMessage(), cause));
        PipelineAnalysisTaskStepContext context = contextWithAsrResult(7L);

        assertThatThrownBy(() -> step.execute(context))
            .isInstanceOf(BusinessException.class);

        assertThat(context.pendingAiCallRecords()).singleElement().satisfies(record -> {
            assertThat(record.provider()).isEqualTo("openai-compatible");
            assertThat(record.model()).isEqualTo("Qwen/Qwen3-8B");
            assertThat(record.errorCode()).isEqualTo("PROVIDER_RATE_LIMIT");
            assertThat(record.retryable()).isTrue();
            assertThat(record.errorMessage()).contains("uploadId=up_1");
            assertThat(record.errorMessage()).contains("httpStatus=429");
        });
    }

    @Test
    void translateSubtitleSegmentsRejectsOwnerMismatchBeforeCallingLlmService() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 8L)).thenReturn(null);

        assertThatThrownBy(() -> step.execute(contextWithAsrResult(8L)))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(subtitleTranslationService, never()).translateTaskSubtitlesWithAiCallRecord(any());
    }

    @Test
    void translateSubtitleSegmentsRequiresAsrResultBeforeCallingLlmService() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());

        assertThatThrownBy(() -> step.execute(context(7L)))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("ASR result is required");

        verify(subtitleTranslationService, never()).translateTaskSubtitlesWithAiCallRecord(any());
    }

    private static PipelineAnalysisTaskStepContext contextWithAsrResult(Long userId) {
        PipelineAnalysisTaskStepContext context = context(userId);
        context.setSpeechToTextResult(new SpeechToTextResult(
            "fake-asr",
            "en",
            "hello world",
            List.of(new TranscribedSegment(0, 0, 1000, "hello world")),
            Duration.ofMillis(1),
            1000,
            Map.of("safe", "metadata")
        ));
        return context;
    }

    private static PipelineAnalysisTaskStepContext context(Long userId) {
        return new PipelineAnalysisTaskStepContext(
            new AnalysisTaskExecutionContext("task_1", "up_1", userId, "zh-CN", "req_1")
        );
    }

    private static AnalysisTask task() {
        AnalysisTask task = new AnalysisTask();
        task.setId("task_1");
        task.setUserId(7L);
        return task;
    }
}
