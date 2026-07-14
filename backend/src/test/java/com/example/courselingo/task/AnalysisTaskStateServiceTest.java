package com.example.courselingo.task;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.dto.AnalysisTaskStateChangeCommand;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.entity.TaskLog;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.mapper.TaskLogMapper;
import com.example.courselingo.task.model.AnalysisTaskStage;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.task.progress.TaskProgressSnapshot;
import com.example.courselingo.task.progress.TaskProgressSnapshotService;
import com.example.courselingo.task.service.AnalysisTaskStateMachine;
import com.example.courselingo.task.service.AnalysisTaskStateServiceImpl;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class AnalysisTaskStateServiceTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(
        Instant.parse("2026-06-27T12:00:00Z"),
        ZoneOffset.UTC
    );

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private TaskLogMapper taskLogMapper;

    @Mock
    private TaskProgressSnapshotService progressSnapshotService;

    private AnalysisTaskStateServiceImpl stateService;

    @BeforeEach
    void setUp() {
        stateService = new AnalysisTaskStateServiceImpl(
            analysisTaskMapper,
            taskLogMapper,
            new AnalysisTaskStateMachine(),
            FIXED_CLOCK,
            progressSnapshotService
        );
    }

    @Test
    void runningTransitionSetsStartedAtWhenMissingAndWritesTaskLog() {
        AnalysisTask task = task("task_1", 7L, AnalysisTaskStatus.QUEUED, null, null);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(analysisTaskMapper.updateStateByIdAndUserId(any(AnalysisTask.class))).thenReturn(1);

        stateService.changeState(command("task_1", 7L, AnalysisTaskStatus.RUNNING, 20, AnalysisTaskStage.ASR));

        AnalysisTask updated = captureUpdatedTask();
        assertThat(updated.getId()).isEqualTo("task_1");
        assertThat(updated.getUserId()).isEqualTo(7L);
        assertThat(updated.getStatus()).isEqualTo("RUNNING");
        assertThat(updated.getProgressPercent()).isEqualTo(20);
        assertThat(updated.getCurrentStage()).isEqualTo("ASR");
        assertThat(updated.getStartedAt()).isEqualTo(now());
        assertThat(updated.getFinishedAt()).isNull();

        TaskLog log = captureInsertedLog();
        assertThat(log.getTaskId()).isEqualTo("task_1");
        assertThat(log.getUserId()).isEqualTo(7L);
        assertThat(log.getLevel()).isEqualTo("INFO");
        assertThat(log.getStage()).isEqualTo("ASR");
        assertThat(log.getMessage()).contains("QUEUED -> RUNNING");

        TaskProgressSnapshot snapshot = captureSavedSnapshot();
        assertThat(snapshot.taskId()).isEqualTo("task_1");
        assertThat(snapshot.status()).isEqualTo("RUNNING");
        assertThat(snapshot.progressPercent()).isEqualTo(20);
        assertThat(snapshot.currentStage()).isEqualTo("ASR");
        assertThat(snapshot.errorCode()).isNull();
        assertThat(snapshot.errorMessage()).isNull();
        assertThat(snapshot.updatedAt()).isEqualTo(FIXED_CLOCK.instant());
    }

    @Test
    void succeededTransitionAcceptsProgress100AndSetsFinishedAt() {
        AnalysisTask task = task("task_1", 7L, AnalysisTaskStatus.RUNNING, now().minusMinutes(5), null);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(analysisTaskMapper.updateStateByIdAndUserId(any(AnalysisTask.class))).thenReturn(1);

        stateService.changeState(command("task_1", 7L, AnalysisTaskStatus.SUCCEEDED, 100, AnalysisTaskStage.DONE));

        AnalysisTask updated = captureUpdatedTask();
        assertThat(updated.getProgressPercent()).isEqualTo(100);
        assertThat(updated.getFinishedAt()).isEqualTo(now());
        assertThat(updated.getErrorCode()).isNull();
        assertThat(updated.getErrorMessage()).isNull();
        assertThat(captureSavedSnapshot().progressPercent()).isEqualTo(100);
    }

    @Test
    void failedTransitionSetsFinishedAt() {
        assertTerminalFinishedAt(AnalysisTaskStatus.FAILED);
    }

    @Test
    void keepsExistingProgressWhenCommandDoesNotProvideProgress() {
        AnalysisTask task = task("task_1", 7L, AnalysisTaskStatus.QUEUED, null, null);
        task.setProgressPercent(35);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(analysisTaskMapper.updateStateByIdAndUserId(any(AnalysisTask.class))).thenReturn(1);

        stateService.changeState(command("task_1", 7L, AnalysisTaskStatus.RUNNING, null, AnalysisTaskStage.ASR));

        assertThat(captureUpdatedTask().getProgressPercent()).isEqualTo(35);
    }

    @Test
    void canceledTransitionSetsFinishedAt() {
        assertTerminalFinishedAt(AnalysisTaskStatus.CANCELED);
    }

    @Test
    void rejectsProgressOutsideRange() {
        assertThatThrownBy(() ->
            stateService.changeState(command("task_1", 7L, AnalysisTaskStatus.RUNNING, -1, AnalysisTaskStage.ASR)))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);

        assertThatThrownBy(() ->
            stateService.changeState(command("task_1", 7L, AnalysisTaskStatus.RUNNING, 101, AnalysisTaskStage.ASR)))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
    }

    @Test
    void succeededTransitionRejectsNon100RequestedProgress() {
        assertThatThrownBy(() ->
            stateService.changeState(command("task_1", 7L, AnalysisTaskStatus.SUCCEEDED, 99, AnalysisTaskStage.DONE)))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);

        verify(analysisTaskMapper, never()).selectByIdAndUserId(any(), any());
        verify(analysisTaskMapper, never()).updateStateByIdAndUserId(any());
        verify(taskLogMapper, never()).insert(any(TaskLog.class));
    }

    @Test
    void rejectsIllegalTransitionWithoutUpdatingOrLogging() {
        AnalysisTask task = task("task_1", 7L, AnalysisTaskStatus.CREATED, null, null);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);

        assertThatThrownBy(() ->
            stateService.changeState(command("task_1", 7L, AnalysisTaskStatus.SUCCEEDED, 100, AnalysisTaskStage.DONE)))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_INVALID_STATUS);

        verify(analysisTaskMapper, never()).updateStateByIdAndUserId(any());
        verify(taskLogMapper, never()).insert(any(TaskLog.class));
    }

    @Test
    void nonOwnerOrMissingTaskFailsWithoutLeakingUserId() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 99L)).thenReturn(null);

        assertThatThrownBy(() ->
            stateService.changeState(command("task_1", 99L, AnalysisTaskStatus.RUNNING, 10, AnalysisTaskStage.ASR)))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                BusinessException exception = (BusinessException) error;
                assertThat(exception.errorCode()).isEqualTo(ErrorCode.TASK_NOT_FOUND);
                assertThat(exception.getMessage()).doesNotContain("99");
            });

        verify(analysisTaskMapper, never()).updateStateByIdAndUserId(any());
        verify(taskLogMapper, never()).insert(any(TaskLog.class));
    }

    @Test
    void stateUpdateIsScopedByTaskIdAndUserId() {
        AnalysisTask task = task("task_1", 7L, AnalysisTaskStatus.QUEUED, null, null);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(analysisTaskMapper.updateStateByIdAndUserId(any(AnalysisTask.class))).thenReturn(1);

        stateService.changeState(command("task_1", 7L, AnalysisTaskStatus.RUNNING, 10, AnalysisTaskStage.ASR));

        verify(analysisTaskMapper).selectByIdAndUserId("task_1", 7L);
        AnalysisTask updated = captureUpdatedTask();
        assertThat(updated.getId()).isEqualTo("task_1");
        assertThat(updated.getUserId()).isEqualTo(7L);
    }

    @Test
    void failedOwnerScopedUpdateFailsIfNoRowWasUpdated() {
        AnalysisTask task = task("task_1", 7L, AnalysisTaskStatus.QUEUED, null, null);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(analysisTaskMapper.updateStateByIdAndUserId(any(AnalysisTask.class))).thenReturn(0);

        assertThatThrownBy(() ->
            stateService.changeState(command("task_1", 7L, AnalysisTaskStatus.RUNNING, 20, AnalysisTaskStage.ASR)))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(taskLogMapper, never()).insert(any(TaskLog.class));
    }

    @Test
    void sanitizesTaskLogAndStoredErrorMessage() {
        AnalysisTask task = task("task_1", 7L, AnalysisTaskStatus.RUNNING, now().minusMinutes(5), null);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(analysisTaskMapper.updateStateByIdAndUserId(any(AnalysisTask.class))).thenReturn(1);

        stateService.changeState(AnalysisTaskStateChangeCommand.builder()
            .taskId("task_1")
            .userId(7L)
            .targetStatus(AnalysisTaskStatus.FAILED)
            .progressPercent(30)
            .stage(AnalysisTaskStage.FAILED)
            .errorCode("ASR_FAILED")
            .errorMessage("access token abc secret key xyz api key pqr C:\\Users\\demo\\video.mp4 /home/demo/file")
            .build());

        AnalysisTask updated = captureUpdatedTask();
        assertThat(updated.getErrorMessage()).doesNotContainIgnoringCase("token");
        assertThat(updated.getErrorMessage()).doesNotContainIgnoringCase("secret");
        assertThat(updated.getErrorMessage()).doesNotContainIgnoringCase("api key");
        assertThat(updated.getErrorMessage()).doesNotContain("C:\\");
        assertThat(updated.getErrorMessage()).doesNotContain("/home/");
        assertThat(updated.getErrorMessage().length()).isLessThanOrEqualTo(1024);

        TaskLog log = captureInsertedLog();
        assertThat(log.getMessage()).doesNotContainIgnoringCase("token");
        assertThat(log.getMessage()).doesNotContainIgnoringCase("secret");
        assertThat(log.getMessage()).doesNotContainIgnoringCase("api key");
        assertThat(log.getMessage()).doesNotContain("C:\\");
        assertThat(log.getMessage()).doesNotContain("/home/");

        TaskProgressSnapshot snapshot = captureSavedSnapshot();
        assertThat(snapshot.errorCode()).isEqualTo("ASR_FAILED");
        assertThat(snapshot.errorMessage()).isEqualTo(updated.getErrorMessage());
    }

    @Test
    void redisSnapshotFailureDoesNotRollbackMysqlStateUpdate() {
        AnalysisTask task = task("task_1", 7L, AnalysisTaskStatus.QUEUED, null, null);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(analysisTaskMapper.updateStateByIdAndUserId(any(AnalysisTask.class))).thenReturn(1);
        org.mockito.Mockito.doThrow(new IllegalStateException("redis unavailable"))
            .when(progressSnapshotService).save(any(TaskProgressSnapshot.class));

        stateService.changeState(command("task_1", 7L, AnalysisTaskStatus.RUNNING, 20, AnalysisTaskStage.ASR));

        AnalysisTask updated = captureUpdatedTask();
        assertThat(updated.getStatus()).isEqualTo("RUNNING");
        assertThat(captureInsertedLog().getMessage()).contains("QUEUED -> RUNNING");
    }

    private void assertTerminalFinishedAt(AnalysisTaskStatus targetStatus) {
        AnalysisTask task = task("task_" + targetStatus.name(), 7L, AnalysisTaskStatus.RUNNING, now().minusMinutes(5), null);
        when(analysisTaskMapper.selectByIdAndUserId(task.getId(), 7L)).thenReturn(task);
        when(analysisTaskMapper.updateStateByIdAndUserId(any(AnalysisTask.class))).thenReturn(1);

        stateService.changeState(command(task.getId(), 7L, targetStatus, 50, AnalysisTaskStage.FAILED));

        assertThat(captureUpdatedTask().getFinishedAt()).isEqualTo(now());
    }

    private AnalysisTask captureUpdatedTask() {
        ArgumentCaptor<AnalysisTask> captor = ArgumentCaptor.forClass(AnalysisTask.class);
        verify(analysisTaskMapper).updateStateByIdAndUserId(captor.capture());
        return captor.getValue();
    }

    private TaskLog captureInsertedLog() {
        ArgumentCaptor<TaskLog> captor = ArgumentCaptor.forClass(TaskLog.class);
        verify(taskLogMapper).insert(captor.capture());
        return captor.getValue();
    }

    private TaskProgressSnapshot captureSavedSnapshot() {
        ArgumentCaptor<TaskProgressSnapshot> captor = ArgumentCaptor.forClass(TaskProgressSnapshot.class);
        verify(progressSnapshotService).save(captor.capture());
        return captor.getValue();
    }

    private static AnalysisTaskStateChangeCommand command(
        String taskId,
        Long userId,
        AnalysisTaskStatus status,
        Integer progress,
        AnalysisTaskStage stage
    ) {
        return AnalysisTaskStateChangeCommand.builder()
            .taskId(taskId)
            .userId(userId)
            .targetStatus(status)
            .progressPercent(progress)
            .stage(stage)
            .build();
    }

    private static AnalysisTask task(
        String taskId,
        Long userId,
        AnalysisTaskStatus status,
        LocalDateTime startedAt,
        LocalDateTime finishedAt
    ) {
        AnalysisTask task = new AnalysisTask();
        task.setId(taskId);
        task.setUserId(userId);
        task.setStatus(status.name());
        task.setProgressPercent(0);
        task.setStartedAt(startedAt);
        task.setFinishedAt(finishedAt);
        return task;
    }

    private static LocalDateTime now() {
        return LocalDateTime.ofInstant(FIXED_CLOCK.instant(), FIXED_CLOCK.getZone());
    }
}
