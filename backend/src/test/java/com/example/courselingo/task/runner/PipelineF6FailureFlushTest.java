package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.record.domain.AiCallRecordStatus;
import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.ai.record.dto.AiCallRecordView;
import com.example.courselingo.ai.record.dto.CompleteAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.FailAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.StartAiCallRecordCommand;
import com.example.courselingo.ai.record.service.AiCallRecordService;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class PipelineF6FailureFlushTest {

    @Test
    void executorFlushesPendingFailedAiCallRecordWhenProviderStepThrowsBeforeWriteStep() {
        AnalysisTaskMapper analysisTaskMapper = mock(AnalysisTaskMapper.class);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        RecordingAiCallRecordService service = new RecordingAiCallRecordService();
        PipelineAnalysisTaskWorkExecutor executor = new PipelineAnalysisTaskWorkExecutor(List.of(
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.VALIDATE_TASK),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.RESOLVE_UPLOADED_SOURCE),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.EXTRACT_AUDIO),
            new FailingTranslationStep(),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.PERSIST_SUBTITLES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.OCR_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS),
            new WriteAiCallRecordStep(analysisTaskMapper, service),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.UPDATE_TASK_PROGRESS_STATUS)
        ));

        assertThatThrownBy(() -> executor.execute(new AnalysisTaskExecutionContext(
            "task_1",
            "up_1",
            7L,
            "zh-CN",
            "req_1"
        )))
            .isInstanceOf(PipelineAnalysisTaskStepException.class)
            .hasMessageContaining("TRANSCRIBE")
            .hasMessageNotContaining("secret")
            .hasMessageNotContaining("C:\\private");

        assertThat(service.started).hasSize(1);
        assertThat(service.failed).hasSize(1);
        assertThat(service.started.get(0).callType()).isEqualTo(AiCallType.ASR);
        assertThat(service.started.get(0).stage()).isEqualTo(AiCallStage.TRANSCRIPTION);
        assertThat(service.failed.get(0).errorMessage())
            .doesNotContainIgnoringCase("secret")
            .doesNotContain("C:\\private");
    }

    private static AnalysisTask task() {
        AnalysisTask task = new AnalysisTask();
        task.setId("task_1");
        task.setUserId(7L);
        return task;
    }

    private static final class FailingTranslationStep implements PipelineAnalysisTaskStep {

        @Override
        public PipelineAnalysisTaskStepName name() {
            return PipelineAnalysisTaskStepName.TRANSCRIBE;
        }

        @Override
        public void execute(PipelineAnalysisTaskStepContext context) {
            context.addAiCallRecord(PipelineAiCallRecord.failed(
                AiCallType.ASR,
                AiCallStage.TRANSCRIPTION,
                "fake-asr",
                null,
                5L,
                "AI_PROVIDER_FAILED",
                "provider failed with secret at C:\\private\\audio.wav",
                true,
                null,
                null
            ));
            throw new IllegalStateException("provider failed with secret at C:\\private\\audio.wav");
        }
    }

    private static final class RecordingAiCallRecordService implements AiCallRecordService {

        private long nextId = 1L;
        private final List<StartAiCallRecordCommand> started = new ArrayList<>();
        private final List<FailAiCallRecordCommand> failed = new ArrayList<>();

        @Override
        public AiCallRecordView startCall(StartAiCallRecordCommand command) {
            started.add(command);
            return view(nextId++, command.callType(), command.stage(), AiCallRecordStatus.STARTED);
        }

        @Override
        public AiCallRecordView completeCall(CompleteAiCallRecordCommand command) {
            return view(command.recordId(), AiCallType.ASR, AiCallStage.TRANSCRIPTION, AiCallRecordStatus.SUCCEEDED);
        }

        @Override
        public AiCallRecordView failCall(FailAiCallRecordCommand command) {
            failed.add(command);
            return view(command.recordId(), AiCallType.ASR, AiCallStage.TRANSCRIPTION, AiCallRecordStatus.FAILED);
        }

        @Override
        public List<AiCallRecordView> listByTask(String taskId, Long userId) {
            return List.of();
        }

        private static AiCallRecordView view(
            Long id,
            AiCallType callType,
            AiCallStage stage,
            AiCallRecordStatus status
        ) {
            return new AiCallRecordView(
                id,
                "task_1",
                callType,
                stage,
                "fake",
                null,
                status,
                LocalDateTime.parse("2026-06-28T10:00:00"),
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
                null,
                null,
                LocalDateTime.parse("2026-06-28T10:00:00"),
                LocalDateTime.parse("2026-06-28T10:00:00")
            );
        }
    }
}
