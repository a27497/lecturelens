package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.record.domain.AiCallRecordStatus;
import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.ai.record.dto.AiCallRecordView;
import com.example.courselingo.ai.record.dto.CompleteAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.FailAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.StartAiCallRecordCommand;
import com.example.courselingo.ai.record.service.AiCallRecordService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class WriteAiCallRecordStepTest {

    @Test
    void writeAiCallRecordFlushesSafePendingAsrAndLlmSummariesThroughD15Service() {
        AnalysisTaskMapper analysisTaskMapper = mock(AnalysisTaskMapper.class);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        RecordingAiCallRecordService service = new RecordingAiCallRecordService();
        PipelineAnalysisTaskStepContext context = context();
        context.addAiCallRecord(PipelineAiCallRecord.succeeded(
            AiCallType.ASR,
            AiCallStage.TRANSCRIPTION,
            "fake-asr",
            "asr-model",
            12L,
            null,
            null,
            null,
            2,
            1,
            null,
            null
        ));
        context.addAiCallRecord(PipelineAiCallRecord.succeeded(
            AiCallType.LLM,
            AiCallStage.TRANSLATION,
            "fake-llm",
            "translate-model",
            25L,
            11,
            13,
            24,
            2,
            2,
            null,
            null
        ));
        context.addAiCallRecord(PipelineAiCallRecord.failed(
            AiCallType.LLM,
            AiCallStage.LEARNING_PACKAGE,
            "fake-llm",
            "package-model",
            30L,
            "AI_PROVIDER_FAILED",
            "Authorization Bearer token at C:\\secret\\audio.wav",
            true,
            null,
            null
        ));

        new WriteAiCallRecordStep(analysisTaskMapper, service).execute(context);
        new WriteAiCallRecordStep(analysisTaskMapper, service).execute(context);

        assertThat(service.started).hasSize(3);
        assertThat(service.completed).hasSize(2);
        assertThat(service.failed).hasSize(1);
        assertThat(service.started).extracting(StartAiCallRecordCommand::taskId).containsOnly("task_1");
        assertThat(service.started).extracting(StartAiCallRecordCommand::userId).containsOnly(7L);
        assertThat(service.started).extracting(StartAiCallRecordCommand::callType)
            .containsExactly(AiCallType.ASR, AiCallType.LLM, AiCallType.LLM);
        assertThat(service.started).extracting(StartAiCallRecordCommand::stage)
            .containsExactly(AiCallStage.TRANSCRIPTION, AiCallStage.TRANSLATION, AiCallStage.LEARNING_PACKAGE);
        assertThat(service.completed.get(1).promptTokens()).isEqualTo(11);
        assertThat(service.completed.get(1).completionTokens()).isEqualTo(13);
        assertThat(service.completed.get(1).totalTokens()).isEqualTo(24);
        assertThat(service.completed.get(0).outputUnits()).isEqualTo(1);
        assertThat(service.failed.get(0).errorMessage())
            .doesNotContainIgnoringCase("authorization")
            .doesNotContainIgnoringCase("token")
            .doesNotContain("C:\\secret");
        assertThat(service.started.toString() + service.completed + service.failed)
            .doesNotContain("raw prompt")
            .doesNotContain("raw response")
            .doesNotContain("objectKey")
            .doesNotContain("full subtitle")
            .doesNotContain("full learning package");
    }

    @Test
    void writeAiCallRecordRejectsOwnerMismatchBeforeCallingService() {
        AnalysisTaskMapper analysisTaskMapper = mock(AnalysisTaskMapper.class);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(null);
        AiCallRecordService service = mock(AiCallRecordService.class);
        PipelineAnalysisTaskStepContext context = context();
        context.addAiCallRecord(PipelineAiCallRecord.succeeded(
            AiCallType.ASR,
            AiCallStage.TRANSCRIPTION,
            "fake-asr",
            null,
            1L,
            null,
            null,
            null,
            null,
            null,
            null,
            null
        ));

        assertThatThrownBy(() -> new WriteAiCallRecordStep(analysisTaskMapper, service).execute(context))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(service, never()).startCall(org.mockito.ArgumentMatchers.any());
    }

    @Test
    void writeAiCallRecordServiceFailurePropagatesWithoutPretendingSuccess() {
        AnalysisTaskMapper analysisTaskMapper = mock(AnalysisTaskMapper.class);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        AiCallRecordService service = mock(AiCallRecordService.class);
        when(service.startCall(org.mockito.ArgumentMatchers.any()))
            .thenThrow(new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "AI call record insert failed"));
        PipelineAnalysisTaskStepContext context = context();
        context.addAiCallRecord(PipelineAiCallRecord.succeeded(
            AiCallType.ASR,
            AiCallStage.TRANSCRIPTION,
            "fake-asr",
            null,
            1L,
            null,
            null,
            null,
            null,
            null,
            null,
            null
        ));

        assertThatThrownBy(() -> new WriteAiCallRecordStep(analysisTaskMapper, service).execute(context))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("AI call record insert failed");
    }

    private static PipelineAnalysisTaskStepContext context() {
        return new PipelineAnalysisTaskStepContext(
            new AnalysisTaskExecutionContext("task_1", "up_1", 7L, "zh-CN", "req_1")
        );
    }

    private static AnalysisTask task() {
        AnalysisTask task = new AnalysisTask();
        task.setId("task_1");
        task.setUserId(7L);
        return task;
    }

    private static final class RecordingAiCallRecordService implements AiCallRecordService {

        private long nextId = 1L;
        private final List<StartAiCallRecordCommand> started = new ArrayList<>();
        private final List<CompleteAiCallRecordCommand> completed = new ArrayList<>();
        private final List<FailAiCallRecordCommand> failed = new ArrayList<>();

        @Override
        public AiCallRecordView startCall(StartAiCallRecordCommand command) {
            started.add(command);
            return view(nextId++, command, AiCallRecordStatus.STARTED);
        }

        @Override
        public AiCallRecordView completeCall(CompleteAiCallRecordCommand command) {
            completed.add(command);
            return view(command.recordId(), AiCallRecordStatus.SUCCEEDED);
        }

        @Override
        public AiCallRecordView failCall(FailAiCallRecordCommand command) {
            failed.add(command);
            return view(command.recordId(), AiCallRecordStatus.FAILED);
        }

        @Override
        public List<AiCallRecordView> listByTask(String taskId, Long userId) {
            return List.of();
        }

        private static AiCallRecordView view(
            Long id,
            StartAiCallRecordCommand command,
            AiCallRecordStatus status
        ) {
            return new AiCallRecordView(
                id,
                command.taskId(),
                command.callType(),
                command.stage(),
                command.provider(),
                command.model(),
                status,
                LocalDateTime.parse("2026-06-28T10:00:00"),
                null,
                null,
                null,
                null,
                null,
                command.inputUnits(),
                null,
                command.requestFingerprint(),
                null,
                null,
                null,
                null,
                LocalDateTime.parse("2026-06-28T10:00:00"),
                LocalDateTime.parse("2026-06-28T10:00:00")
            );
        }

        private static AiCallRecordView view(Long id, AiCallRecordStatus status) {
            return new AiCallRecordView(
                id,
                "task_1",
                AiCallType.ASR,
                AiCallStage.TRANSCRIPTION,
                "fake",
                null,
                status,
                LocalDateTime.parse("2026-06-28T10:00:00"),
                LocalDateTime.parse("2026-06-28T10:00:01"),
                1L,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                LocalDateTime.parse("2026-06-28T10:00:00"),
                LocalDateTime.parse("2026-06-28T10:00:01")
            );
        }
    }
}
