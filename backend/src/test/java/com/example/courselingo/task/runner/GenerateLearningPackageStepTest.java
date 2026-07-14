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
import com.example.courselingo.learning.service.GenerateLearningPackageCommand;
import com.example.courselingo.learning.service.LearningPackageAiCallResult;
import com.example.courselingo.learning.service.LearningPackageService;
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
class GenerateLearningPackageStepTest {

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private LearningPackageService learningPackageService;

    private GenerateLearningPackageStep step;

    @BeforeEach
    void setUp() {
        step = new GenerateLearningPackageStep(analysisTaskMapper, learningPackageService);
    }

    @Test
    void generateLearningPackageUsesOwnerScopedTaskAndAsrLanguage() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        when(learningPackageService.generateLearningPackageWithAiCallRecord(any(GenerateLearningPackageCommand.class)))
            .thenReturn(new LearningPackageAiCallResult(
                1,
                "fake-llm",
                "fake-learning-model",
                Duration.ofMillis(19),
                21,
                34,
                55,
                4,
                1,
                null,
                null
            ));

        step.execute(contextWithAsrResult(7L));

        ArgumentCaptor<GenerateLearningPackageCommand> captor =
            ArgumentCaptor.forClass(GenerateLearningPackageCommand.class);
        verify(learningPackageService).generateLearningPackageWithAiCallRecord(captor.capture());
        GenerateLearningPackageCommand command = captor.getValue();
        assertThat(command.taskId()).isEqualTo("task_1");
        assertThat(command.userId()).isEqualTo(7L);
        assertThat(command.sourceLanguage()).isEqualTo("en");
        assertThat(command.targetLanguage()).isEqualTo("zh-CN");
        assertThat(command.requestId()).isEqualTo("req_1");
    }

    @Test
    void generateLearningPackageAddsSafeLlmCallSummary() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        when(learningPackageService.generateLearningPackageWithAiCallRecord(any(GenerateLearningPackageCommand.class)))
            .thenReturn(new LearningPackageAiCallResult(
                1,
                "fake-llm",
                "fake-learning-model",
                Duration.ofMillis(19),
                21,
                34,
                55,
                4,
                1,
                null,
                null
            ));
        PipelineAnalysisTaskStepContext context = contextWithAsrResult(7L);

        step.execute(context);

        assertThat(context.pendingAiCallRecords()).singleElement().satisfies(record -> {
            assertThat(record.callType()).isEqualTo(AiCallType.LLM);
            assertThat(record.stage()).isEqualTo(AiCallStage.LEARNING_PACKAGE);
            assertThat(record.provider()).isEqualTo("fake-llm");
            assertThat(record.model()).isEqualTo("fake-learning-model");
            assertThat(record.durationMillis()).isEqualTo(19L);
            assertThat(record.promptTokens()).isEqualTo(21);
            assertThat(record.completionTokens()).isEqualTo(34);
            assertThat(record.totalTokens()).isEqualTo(55);
            assertThat(record.outputUnits()).isEqualTo(1);
            assertThat(record.toString()).doesNotContain("hello world");
        });
    }

    @Test
    void generateLearningPackageAddsSanitizedFailureRecordWhenLlmServiceFails() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        when(learningPackageService.generateLearningPackageWithAiCallRecord(any(GenerateLearningPackageCommand.class)))
            .thenThrow(new IllegalStateException("raw response secret at C:\\secret\\response.txt"));
        PipelineAnalysisTaskStepContext context = contextWithAsrResult(7L);

        assertThatThrownBy(() -> step.execute(context))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("raw response secret");

        assertThat(context.pendingAiCallRecords()).singleElement().satisfies(record -> {
            assertThat(record.callType()).isEqualTo(AiCallType.LLM);
            assertThat(record.stage()).isEqualTo(AiCallStage.LEARNING_PACKAGE);
            assertThat(record.provider()).isEqualTo("learning-package-service");
            assertThat(record.errorCode()).isEqualTo("AI_PROVIDER_FAILED");
            assertThat(record.errorMessage()).doesNotContainIgnoringCase("secret");
            assertThat(record.errorMessage()).doesNotContain("C:\\secret");
        });
    }

    @Test
    void generateLearningPackagePreservesTypedProviderFailureInAiCallRecord() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        OpenAiCompatibleLlmException cause = new OpenAiCompatibleLlmException(
            "OpenAI-compatible LLM response JSON is invalid type=MALFORMED_RESPONSE taskId=task_1",
            LlmProviderFailureType.MALFORMED_RESPONSE,
            false,
            200,
            null,
            "openai-compatible",
            "Qwen/Qwen3-8B",
            "https://api.siliconflow.cn/v1/chat/completions",
            123L,
            "trace-1",
            "not-json",
            null,
            null
        );
        when(learningPackageService.generateLearningPackageWithAiCallRecord(any(GenerateLearningPackageCommand.class)))
            .thenThrow(new BusinessException(ErrorCode.AI_PROVIDER_FAILED, cause.getMessage(), cause));
        PipelineAnalysisTaskStepContext context = contextWithAsrResult(7L);

        assertThatThrownBy(() -> step.execute(context))
            .isInstanceOf(BusinessException.class);

        assertThat(context.pendingAiCallRecords()).singleElement().satisfies(record -> {
            assertThat(record.provider()).isEqualTo("openai-compatible");
            assertThat(record.model()).isEqualTo("Qwen/Qwen3-8B");
            assertThat(record.errorCode()).isEqualTo("MALFORMED_RESPONSE");
            assertThat(record.retryable()).isFalse();
            assertThat(record.errorMessage()).contains("uploadId=up_1");
            assertThat(record.errorMessage()).contains("MALFORMED_RESPONSE");
        });
    }

    @Test
    void generateLearningPackageRejectsOwnerMismatchBeforeCallingLlmService() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 8L)).thenReturn(null);

        assertThatThrownBy(() -> step.execute(contextWithAsrResult(8L)))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(learningPackageService, never()).generateLearningPackageWithAiCallRecord(any());
    }

    @Test
    void generateLearningPackageRequiresAsrResultBeforeCallingLlmService() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());

        assertThatThrownBy(() -> step.execute(context(7L)))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("ASR result is required");

        verify(learningPackageService, never()).generateLearningPackageWithAiCallRecord(any());
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
