package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.llm.TranslationFailure;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.service.LearningAvailability;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CancellationException;
import java.util.function.Supplier;
import org.junit.jupiter.api.Test;

/** Step 3: subtitles-ready means learnable; background stages fail independently. */
class PipelineEarlyLearningTest {

    private final List<String> events = new ArrayList<>();

    @Test
    void opensLearningRightAfterSubtitlesAreStoredAndBeforeTranslation() {
        LearningAvailability learning = enabledLearning(true);

        AnalysisTaskWorkResult result = executor(Map.of(), learning).execute(context());

        assertThat(result.success()).isTrue();
        assertThat(result.errorCode()).isNull();
        int persisted = events.indexOf("PERSIST_SUBTITLES");
        int opened = events.indexOf("open");
        assertThat(opened).isEqualTo(persisted + 1);
        assertThat(events.indexOf("TRANSLATE_SUBTITLES")).isGreaterThan(opened);
        var order = inOrder(learning);
        order.verify(learning).resetStages("task_1", 7L);
        order.verify(learning).openAfterSubtitles("task_1", 7L);
        verify(learning).recordStage("task_1", 7L, LearningAvailability.TRANSLATION, LearningAvailability.SUCCEEDED, null);
        verify(learning).recordStage("task_1", 7L, LearningAvailability.LEARNING_PACKAGE, LearningAvailability.SUCCEEDED, null);
        verify(learning).recordStage("task_1", 7L, LearningAvailability.ARTIFACTS, LearningAvailability.SUCCEEDED, null);
    }

    @Test
    void translationFailureAfterLearningOpenedOnlyAffectsTranslation() {
        LearningAvailability learning = enabledLearning(true);

        AnalysisTaskWorkResult result = executor(Map.of(
            PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES, () -> new IllegalStateException("provider down")
        ), learning).execute(context());

        assertThat(result.success()).isTrue();
        assertThat(result.errorCode()).isEqualTo(AnalysisTaskWorkResult.DEGRADED_BACKGROUND);
        assertThat(events).contains("GENERATE_LEARNING_PACKAGE", "GENERATE_ARTIFACTS", "WRITE_AI_CALL_RECORD",
            "UPDATE_TASK_PROGRESS_STATUS");
        verify(learning).recordStage("task_1", 7L, LearningAvailability.TRANSLATION, LearningAvailability.FAILED,
            "ILLEGALSTATEEXCEPTION");
        verify(learning).recordStage("task_1", 7L, LearningAvailability.LEARNING_PACKAGE, LearningAvailability.SUCCEEDED, null);
        verify(learning).recordStage("task_1", 7L, LearningAvailability.ARTIFACTS, LearningAvailability.SUCCEEDED, null);
    }

    @Test
    void learningPackageFailureStillProducesDownloadFiles() {
        LearningAvailability learning = enabledLearning(true);

        AnalysisTaskWorkResult result = executor(Map.of(
            PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE,
            () -> new BusinessException(ErrorCode.LEARNING_PACKAGE_CONTEXT_LIMIT_EXCEEDED)
        ), learning).execute(context());

        assertThat(result.success()).isTrue();
        assertThat(result.errorCode()).isEqualTo(AnalysisTaskWorkResult.DEGRADED_BACKGROUND);
        assertThat(events).contains("GENERATE_ARTIFACTS");
        verify(learning).recordStage("task_1", 7L, LearningAvailability.LEARNING_PACKAGE, LearningAvailability.FAILED,
            ErrorCode.LEARNING_PACKAGE_CONTEXT_LIMIT_EXCEEDED.code());
        verify(learning).recordStage("task_1", 7L, LearningAvailability.ARTIFACTS, LearningAvailability.SUCCEEDED, null);
    }

    @Test
    void backgroundFailureStillFailsTheCourseWhenLearningDidNotOpen() {
        LearningAvailability learning = enabledLearning(false);

        assertThatThrownBy(() -> executor(Map.of(
            PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES, () -> new IllegalStateException("provider down")
        ), learning).execute(context()))
            .isInstanceOf(PipelineAnalysisTaskStepException.class);
        verify(learning, never()).recordStage(anyString(), any(), anyString(), anyString(), any());
    }

    @Test
    void switchOffKeepsHistoricalWholeCourseFailure() {
        LearningAvailability learning = mock(LearningAvailability.class);
        when(learning.enabled()).thenReturn(false);

        assertThatThrownBy(() -> executor(Map.of(
            PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES, () -> new IllegalStateException("provider down")
        ), learning).execute(context()))
            .isInstanceOf(PipelineAnalysisTaskStepException.class);
        verify(learning, never()).openAfterSubtitles(anyString(), any());
        verify(learning, never()).recordStage(anyString(), any(), anyString(), anyString(), any());
        // A switched-off run still clears outcomes left by an earlier switched-on run.
        verify(learning).resetStages("task_1", 7L);
    }

    @Test
    void cancellationLeaseLossAndRunLevelFailuresStayFatalAfterLearningOpened() {
        List<Supplier<RuntimeException>> fatal = List.of(
            () -> new CancellationException("canceled"),
            () -> new BusinessException(ErrorCode.TASK_INVALID_STATUS),
            () -> TranslationFailure.of(TranslationFailure.Reason.SOURCE_CHANGED),
            () -> TranslationFailure.of(TranslationFailure.Reason.DEADLINE_EXCEEDED),
            () -> TranslationFailure.of(TranslationFailure.Reason.ACCOUNTING_INCOMPLETE),
            () -> TranslationFailure.of(TranslationFailure.Reason.SNAPSHOT_INVALID)
        );
        for (Supplier<RuntimeException> failure : fatal) {
            events.clear();
            LearningAvailability learning = enabledLearning(true);
            assertThatThrownBy(() -> executor(Map.of(PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES, failure), learning)
                .execute(context()))
                .as(failure.get().getClass().getSimpleName())
                .isNotNull();
            assertThat(events).doesNotContain("GENERATE_LEARNING_PACKAGE");
            verify(learning, never()).recordStage(anyString(), any(), anyString(), eq(LearningAvailability.FAILED), any());
        }
    }

    @Test
    void costAccountingFailureAfterLearningOpenedStillFailsTheRun() {
        LearningAvailability learning = enabledLearning(true);

        assertThatThrownBy(() -> executor(Map.of(
            PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD, () -> new IllegalStateException("ledger down")
        ), learning).execute(context()))
            .isInstanceOf(PipelineAnalysisTaskStepException.class)
            .hasMessageContaining("WRITE_AI_CALL_RECORD");
    }

    @Test
    void outcomeWriteFailureDoesNotTurnALearnableCourseIntoAFailedOne() {
        LearningAvailability learning = enabledLearning(true);
        doThrow(new IllegalStateException("db hiccup")).when(learning)
            .recordStage(anyString(), any(), anyString(), anyString(), any());

        AnalysisTaskWorkResult result = executor(Map.of(
            PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS, () -> new IllegalStateException("storage down")
        ), learning).execute(context());

        assertThat(result.success()).isTrue();
        assertThat(result.errorCode()).isEqualTo(AnalysisTaskWorkResult.DEGRADED_BACKGROUND);
    }

    @Test
    void failingToOpenLearningFallsBackToOpeningOnSuccess() {
        LearningAvailability learning = mock(LearningAvailability.class);
        when(learning.enabled()).thenReturn(true);
        when(learning.openAfterSubtitles("task_1", 7L)).thenThrow(new IllegalStateException("db hiccup"));

        assertThat(executor(Map.of(), learning).execute(context()).success()).isTrue();
        assertThatThrownBy(() -> executor(Map.of(
            PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES, () -> new IllegalStateException("provider down")
        ), learning).execute(context()))
            .isInstanceOf(PipelineAnalysisTaskStepException.class);
        verify(learning, never()).recordStage(anyString(), any(), anyString(), anyString(), any());
    }

    private LearningAvailability enabledLearning(boolean opens) {
        LearningAvailability learning = mock(LearningAvailability.class);
        when(learning.enabled()).thenReturn(true);
        doAnswer(invocation -> {
            events.add("open");
            return opens;
        }).when(learning).openAfterSubtitles("task_1", 7L);
        return learning;
    }

    private PipelineAnalysisTaskWorkExecutor executor(
        Map<PipelineAnalysisTaskStepName, Supplier<RuntimeException>> failures,
        LearningAvailability learning
    ) {
        List<PipelineAnalysisTaskStep> steps = PipelineAnalysisTaskStepName.ordered().stream()
            .map(name -> (PipelineAnalysisTaskStep) new Step(name, failures.get(name), events))
            .toList();
        return new PipelineAnalysisTaskWorkExecutor(steps).withLearningAvailability(learning);
    }

    private static AnalysisTaskExecutionContext context() {
        return new AnalysisTaskExecutionContext("task_1", "up_1", 7L, "zh-CN", "req_1");
    }

    private record Step(
        PipelineAnalysisTaskStepName name,
        Supplier<RuntimeException> failure,
        List<String> events
    ) implements PipelineAnalysisTaskStep {
        @Override
        public void execute(PipelineAnalysisTaskStepContext context) {
            if (failure != null) throw failure.get();
            events.add(name.name());
        }
    }
}
