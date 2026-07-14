package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.asr.SpeechToTextResult;
import com.example.courselingo.ai.asr.TranscribedSegment;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.subtitle.service.SaveTranscriptionSegmentsCommand;
import com.example.courselingo.subtitle.service.SubtitleSegmentPersistenceService;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PersistSubtitleSegmentsStepTest {

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    private CapturingSubtitlePersistenceService persistenceService;
    private PersistSubtitleSegmentsStep step;

    @BeforeEach
    void setUp() {
        persistenceService = new CapturingSubtitlePersistenceService();
        step = new PersistSubtitleSegmentsStep(analysisTaskMapper, persistenceService);
    }

    @Test
    void persistSubtitleSegmentsUsesOwnerScopedTaskAndAsrSegments() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        PipelineAnalysisTaskStepContext context = context(7L);
        SpeechToTextResult result = result();
        context.setSpeechToTextResult(result);

        step.execute(context);

        SaveTranscriptionSegmentsCommand command = persistenceService.capturedCommand.get();
        assertThat(command.taskId()).isEqualTo("task_1");
        assertThat(command.userId()).isEqualTo(7L);
        assertThat(command.result()).isSameAs(result);
        assertThat(command.result().segments())
            .extracting(TranscribedSegment::index)
            .containsExactly(0, 1);
        assertThat(persistenceService.savedCount).isEqualTo(2);
    }

    @Test
    void persistSubtitleSegmentsRejectsOwnerMismatchBeforeWritingSubtitles() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 8L)).thenReturn(null);
        PipelineAnalysisTaskStepContext context = context(8L);
        context.setSpeechToTextResult(result());

        assertThatThrownBy(() -> step.execute(context))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        assertThat(persistenceService.capturedCommand.get()).isNull();
        verify(analysisTaskMapper).selectByIdAndUserId("task_1", 8L);
    }

    @Test
    void persistSubtitleSegmentsRequiresAsrResultBeforeWritingSubtitles() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());

        assertThatThrownBy(() -> step.execute(context(7L)))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("ASR result is required");

        assertThat(persistenceService.capturedCommand.get()).isNull();
        verify(analysisTaskMapper).selectByIdAndUserId("task_1", 7L);
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

    private static SpeechToTextResult result() {
        return new SpeechToTextResult(
            "fake-asr",
            "zh-CN",
            "hello course world",
            List.of(
                new TranscribedSegment(0, 0, 1200, "hello course"),
                new TranscribedSegment(1, 1200, 2400, "world")
            ),
            Duration.ofMillis(10),
            2400,
            Map.of("safe", "metadata")
        );
    }

    private static final class CapturingSubtitlePersistenceService implements SubtitleSegmentPersistenceService {

        private final AtomicReference<SaveTranscriptionSegmentsCommand> capturedCommand = new AtomicReference<>();
        private int savedCount;

        @Override
        public int saveTranscriptionResult(SaveTranscriptionSegmentsCommand command) {
            capturedCommand.set(command);
            savedCount = command.result().segments().size();
            return savedCount;
        }

        @Override
        public int deleteByTaskId(String taskId, Long userId) {
            throw new UnsupportedOperationException("not used");
        }
    }
}
