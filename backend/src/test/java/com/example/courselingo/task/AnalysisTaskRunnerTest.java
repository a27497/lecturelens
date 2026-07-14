package com.example.courselingo.task;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.StructuredLogFields;
import com.example.courselingo.common.tracing.TracingContextHolder;
import com.example.courselingo.dispatch.BoundedTaskExecutor;
import com.example.courselingo.mq.AnalysisTaskMessage;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.entity.TaskLog;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.mapper.TaskLogMapper;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.task.claim.TaskClaimResult;
import com.example.courselingo.task.claim.TaskClaimService;
import com.example.courselingo.task.runner.AnalysisTaskExecutionContext;
import com.example.courselingo.task.runner.AnalysisTaskRunner;
import com.example.courselingo.task.runner.AnalysisTaskRunnerImpl;
import com.example.courselingo.task.runner.AnalysisTaskWorkExecutor;
import com.example.courselingo.task.runner.AnalysisTaskWorkResult;
import com.example.courselingo.task.runner.NoopAnalysisTaskWorkExecutor;
import com.example.courselingo.task.runner.PipelineAnalysisTaskStepException;
import com.example.courselingo.task.runner.PipelineAnalysisTaskStepName;
import com.example.courselingo.task.progress.NoopTaskProgressSnapshotService;
import com.example.courselingo.task.service.AnalysisTaskStateMachine;
import com.example.courselingo.task.service.AnalysisTaskStateServiceImpl;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.slf4j.MDC;

@ExtendWith(MockitoExtension.class)
class AnalysisTaskRunnerTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(
        Instant.parse("2026-06-27T12:00:00Z"),
        ZoneOffset.UTC
    );

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private TaskLogMapper taskLogMapper;

    @Mock
    private AnalysisTaskWorkExecutor executor;

    @Mock
    private BoundedTaskExecutor boundedTaskExecutor;

    @Mock
    private TaskClaimService taskClaimService;

    private AnalysisTaskRunner runner;
    private List<CapturedTaskState> updatedStates;

    @BeforeEach
    void setUp() {
        TracingContextHolder.clear();
        MDC.clear();
        updatedStates = new ArrayList<>();
        AnalysisTaskStateServiceImpl stateService = new AnalysisTaskStateServiceImpl(
            analysisTaskMapper,
            taskLogMapper,
            new AnalysisTaskStateMachine(),
            FIXED_CLOCK,
            new NoopTaskProgressSnapshotService()
        );
        runner = new AnalysisTaskRunnerImpl(
            analysisTaskMapper,
            stateService,
            executor,
            boundedTaskExecutor,
            taskClaimService
        );
        lenient().when(analysisTaskMapper.updateStateByIdAndUserId(any(AnalysisTask.class))).thenAnswer(invocation -> {
            AnalysisTask task = invocation.getArgument(0, AnalysisTask.class);
            updatedStates.add(new CapturedTaskState(
                task.getStatus(),
                task.getProgressPercent(),
                task.getCurrentStage(),
                task.getErrorCode(),
                task.getErrorMessage()
            ));
            return 1;
        });
        lenient().doAnswer(invocation -> {
            java.util.concurrent.Callable<?> callable = invocation.getArgument(2, java.util.concurrent.Callable.class);
            return callable.call();
        }).when(boundedTaskExecutor).submitAndWait(any(), any(), any());
        lenient().when(taskClaimService.tryAcquire("task_1", "req_1")).thenReturn(TaskClaimResult.acquiredResult());
    }

    @Test
    void runFailsWhenTaskDoesNotExist() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(null);

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(executor, never()).execute(any());
        verify(boundedTaskExecutor, never()).submitAndWait(any(), any(), any());
        verify(taskLogMapper, never()).insert(any(TaskLog.class));
    }

    @Test
    void runFailsForNonOwnerScopedMessage() {
        AnalysisTaskMessage nonOwnerMessage = new AnalysisTaskMessage(
            "task_1",
            "up_1",
            99L,
            "zh-CN",
            "req_1",
            "trace_1",
            Instant.parse("2026-06-27T10:00:00Z")
        );
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 99L)).thenReturn(null);

        assertThatThrownBy(() -> runner.run(nonOwnerMessage))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(executor, never()).execute(any());
        verify(boundedTaskExecutor, never()).submitAndWait(any(), any(), any());
    }

    @Test
    void runFailsWhenUploadIdDoesNotMatchTask() {
        AnalysisTask task = task(AnalysisTaskStatus.QUEUED);
        task.setUploadId("up_other");
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);

        verify(executor, never()).execute(any());
        verify(boundedTaskExecutor, never()).submitAndWait(any(), any(), any());
    }

    @Test
    void runFailsWhenTargetLanguageDoesNotMatchTask() {
        AnalysisTask task = task(AnalysisTaskStatus.QUEUED);
        task.setTargetLanguage("en-US");
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);

        verify(executor, never()).execute(any());
        verify(boundedTaskExecutor, never()).submitAndWait(any(), any(), any());
    }

    @Test
    void runOnlyAllowsQueuedTasks() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task(AnalysisTaskStatus.CREATED));

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_INVALID_STATUS);

        verify(executor, never()).execute(any());
        verify(boundedTaskExecutor, never()).submitAndWait(any(), any(), any());
    }

    @Test
    void runMovesQueuedTaskToRunningThenSucceededWhenExecutorSucceeds() {
        AnalysisTask task = task(AnalysisTaskStatus.QUEUED);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(executor.execute(any(AnalysisTaskExecutionContext.class))).thenAnswer(invocation -> {
            assertThat(TracingContextHolder.current()).isPresent();
            assertThat(TracingContextHolder.current().orElseThrow().traceId()).isEqualTo("trace_1");
            assertThat(TracingContextHolder.current().orElseThrow().requestId()).isEqualTo("req_1");
            assertThat(MDC.get(StructuredLogFields.TRACE_ID)).isEqualTo("trace_1");
            assertThat(MDC.get(StructuredLogFields.REQUEST_ID)).isEqualTo("req_1");
            return successResult();
        });

        runner.run(message());

        List<CapturedTaskState> states = capturedUpdatedTasks();
        assertThat(states)
            .extracting(CapturedTaskState::status)
            .containsExactly("RUNNING", "SUCCEEDED");
        CapturedTaskState succeeded = states.get(1);
        assertThat(succeeded.progressPercent()).isEqualTo(100);
        assertThat(succeeded.currentStage()).isEqualTo("DONE");

        ArgumentCaptor<AnalysisTaskExecutionContext> contextCaptor =
            ArgumentCaptor.forClass(AnalysisTaskExecutionContext.class);
        verify(executor).execute(contextCaptor.capture());
        verify(boundedTaskExecutor).submitAndWait(
            org.mockito.ArgumentMatchers.eq("task_1"),
            org.mockito.ArgumentMatchers.eq("req_1"),
            any()
        );
        verify(taskClaimService).tryAcquire("task_1", "req_1");
        verify(taskClaimService).release("task_1", "req_1");
        assertThat(contextCaptor.getValue()).isEqualTo(new AnalysisTaskExecutionContext(
            "task_1",
            "up_1",
            7L,
            "zh-CN",
            "req_1"
        ));
        assertThat(TracingContextHolder.current()).isEmpty();
        assertThat(MDC.get(StructuredLogFields.TRACE_ID)).isNull();
        assertThat(MDC.get(StructuredLogFields.REQUEST_ID)).isNull();
    }

    @Test
    void runMovesTaskToFailedWhenExecutorReturnsFailure() {
        AnalysisTask task = task(AnalysisTaskStatus.QUEUED);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(executor.execute(any())).thenReturn(new AnalysisTaskWorkResult(
            false,
            "EXECUTOR_FAILED",
            sensitiveLongMessage()
        ));

        runner.run(message());

        CapturedTaskState failed = capturedUpdatedTasks().get(1);
        assertThat(failed.status()).isEqualTo("FAILED");
        assertThat(failed.errorCode()).isEqualTo("EXECUTOR_FAILED");
        assertSanitizedAndLimited(failed.errorMessage());
        assertSanitizedAndLimited(capturedInsertedLogs().get(1).getMessage());
        verify(taskClaimService).release("task_1", "req_1");
    }

    @Test
    void runMarksTaskFailedAndThrowsProjectExceptionWhenExecutorThrows() {
        AnalysisTask task = task(AnalysisTaskStatus.QUEUED);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(executor.execute(any())).thenThrow(new IllegalStateException(sensitiveLongMessage()));

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                BusinessException exception = (BusinessException) error;
                assertThat(exception.errorCode()).isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED);
                assertSanitizedAndLimited(exception.getMessage());
            });

        CapturedTaskState failed = capturedUpdatedTasks().get(1);
        assertThat(failed.status()).isEqualTo("FAILED");
        assertThat(failed.errorCode()).isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED.code());
        assertSanitizedAndLimited(failed.errorMessage());
        verify(taskClaimService).release("task_1", "req_1");
    }

    @Test
    void runKeepsTranslationStageWhenTranslateSubtitlesStepFails() {
        AnalysisTask task = task(AnalysisTaskStatus.QUEUED);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(executor.execute(any())).thenThrow(new PipelineAnalysisTaskStepException(
            PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES,
            new IllegalStateException("Subtitle translation provider returned non-Chinese text")
        ));

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED);

        CapturedTaskState failed = capturedUpdatedTasks().get(1);
        assertThat(failed.status()).isEqualTo("FAILED");
        assertThat(failed.currentStage()).isEqualTo("TRANSLATE");
        assertThat(failed.errorMessage()).contains("Subtitle translation provider returned non-Chinese text");
    }

    @Test
    void runKeepsArtifactStageWhenGenerateArtifactsStepFails() {
        AnalysisTask task = task(AnalysisTaskStatus.QUEUED);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(executor.execute(any())).thenThrow(new PipelineAnalysisTaskStepException(
            PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS,
            new IllegalStateException("Markdown glossary translation is required")
        ));

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED);

        CapturedTaskState failed = capturedUpdatedTasks().get(1);
        assertThat(failed.status()).isEqualTo("FAILED");
        assertThat(failed.currentStage()).isEqualTo("GENERATE_ARTIFACTS");
        assertThat(failed.currentStage()).isNotEqualTo("FAILED");
    }

    @Test
    void runDoesNotExecuteWorkWhenClaimAlreadyExists() {
        AnalysisTask task = task(AnalysisTaskStatus.QUEUED);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(taskClaimService.tryAcquire("task_1", "req_1")).thenReturn(TaskClaimResult.rejectedResult());

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_DUPLICATE_CLAIMED);

        assertThat(capturedUpdatedTasks()).isEmpty();
        verify(executor, never()).execute(any());
        verify(boundedTaskExecutor, never()).submitAndWait(any(), any(), any());
        verify(taskClaimService, never()).release("task_1", "req_1");
    }

    @Test
    void runDoesNotExecuteWorkWhenClaimAcquireFails() {
        AnalysisTask task = task(AnalysisTaskStatus.QUEUED);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(taskClaimService.tryAcquire("task_1", "req_1"))
            .thenThrow(new BusinessException(ErrorCode.TASK_CLAIM_UNAVAILABLE));

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_CLAIM_UNAVAILABLE);

        assertThat(capturedUpdatedTasks()).isEmpty();
        verify(executor, never()).execute(any());
        verify(boundedTaskExecutor, never()).submitAndWait(any(), any(), any());
    }

    @Test
    void runRethrowsBoundedExecutorBusyWithoutMarkingTaskSucceeded() {
        AnalysisTask task = task(AnalysisTaskStatus.QUEUED);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        doThrow(new BusinessException(ErrorCode.TASK_EXECUTOR_BUSY))
            .when(boundedTaskExecutor).submitAndWait(any(), any(), any());

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_EXECUTOR_BUSY);

        assertThat(capturedUpdatedTasks())
            .extracting(CapturedTaskState::status)
            .containsExactly("RUNNING");
        verify(executor, never()).execute(any());
        verify(taskClaimService).release("task_1", "req_1");
    }

    @Test
    void retryOnlyAllowsRetryingTasksAndReusesStateMachineTransitions() {
        AnalysisTask task = task(AnalysisTaskStatus.RETRYING);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(executor.execute(any())).thenReturn(successResult());

        runner.retry(message());

        assertThat(capturedUpdatedTasks())
            .extracting(CapturedTaskState::status)
            .containsExactly("QUEUED", "RUNNING", "SUCCEEDED");
        verify(taskClaimService).tryAcquire("task_1", "req_1");
        verify(taskClaimService).release("task_1", "req_1");
    }

    @Test
    void retryRejectsNonRetryingTasks() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task(AnalysisTaskStatus.QUEUED));

        assertThatThrownBy(() -> runner.retry(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_INVALID_STATUS);

        verify(executor, never()).execute(any());
    }

    @Test
    void cancelCancelsCreatedQueuedRunningAndRetryingTasks() {
        assertCancelTransition(AnalysisTaskStatus.CREATED);
        assertCancelTransition(AnalysisTaskStatus.QUEUED);
        assertCancelTransition(AnalysisTaskStatus.RUNNING);
        assertCancelTransition(AnalysisTaskStatus.RETRYING);
    }

    @Test
    void cancelRejectsTerminalTasks() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task(AnalysisTaskStatus.SUCCEEDED));

        assertThatThrownBy(() -> runner.cancel(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_INVALID_STATUS);
    }

    @Test
    void noopExecutorReturnsSuccessfulResultWithoutExternalWork() {
        AnalysisTaskWorkResult result = new NoopAnalysisTaskWorkExecutor().execute(new AnalysisTaskExecutionContext(
            "task_1",
            "up_1",
            7L,
            "zh-CN",
            "req_1"
        ));

        assertThat(result.success()).isTrue();
        assertThat(result.errorCode()).isNull();
        assertThat(result.errorMessage()).isNull();
    }

    private void assertCancelTransition(AnalysisTaskStatus status) {
        setUp();
        clearInvocations(taskClaimService);
        AnalysisTask task = task(status);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);

        runner.cancel(message());

        assertThat(capturedUpdatedTasks()).last()
            .extracting(CapturedTaskState::status)
            .isEqualTo("CANCELED");
        verify(taskClaimService).release("task_1", "req_1");
    }

    private List<CapturedTaskState> capturedUpdatedTasks() {
        return updatedStates;
    }

    private List<TaskLog> capturedInsertedLogs() {
        ArgumentCaptor<TaskLog> captor = ArgumentCaptor.forClass(TaskLog.class);
        verify(taskLogMapper, org.mockito.Mockito.atLeastOnce()).insert(captor.capture());
        return captor.getAllValues();
    }

    private static void assertSanitizedAndLimited(String value) {
        assertThat(value).doesNotContainIgnoringCase("token");
        assertThat(value).doesNotContainIgnoringCase("secret");
        assertThat(value).doesNotContainIgnoringCase("api key");
        assertThat(value).doesNotContain("C:\\");
        assertThat(value).doesNotContain("/home/");
        assertThat(value.length()).isLessThanOrEqualTo(1024);
    }

    private static AnalysisTask task(AnalysisTaskStatus status) {
        AnalysisTask task = new AnalysisTask();
        task.setId("task_1");
        task.setUserId(7L);
        task.setUploadId("up_1");
        task.setTargetLanguage("zh-CN");
        task.setStatus(status.name());
        task.setProgressPercent(0);
        task.setRetryCount(0);
        task.setMaxRetryCount(3);
        return task;
    }

    private static AnalysisTaskMessage message() {
        return new AnalysisTaskMessage(
            "task_1",
            "up_1",
            7L,
            "zh-CN",
            "req_1",
            "trace_1",
            Instant.parse("2026-06-27T10:00:00Z")
        );
    }

    private static AnalysisTaskWorkResult successResult() {
        return new AnalysisTaskWorkResult(true, null, null);
    }

    private record CapturedTaskState(
        String status,
        Integer progressPercent,
        String currentStage,
        String errorCode,
        String errorMessage
    ) {
    }

    private static String sensitiveLongMessage() {
        return "access token raw-token secret key raw-secret api key raw-key C:\\Users\\demo\\video.mp4 "
            + "/home/demo/video.mp4 " + "x".repeat(1200);
    }
}
