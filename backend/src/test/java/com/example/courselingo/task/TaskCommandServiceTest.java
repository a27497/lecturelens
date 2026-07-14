package com.example.courselingo.task;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.tracing.TracingContext;
import com.example.courselingo.common.tracing.TracingContextHolder;
import com.example.courselingo.common.tracing.TracingScope;
import com.example.courselingo.mq.AnalysisTaskMessage;
import com.example.courselingo.mq.AnalysisTaskMessageProducer;
import com.example.courselingo.mq.AnalysisTaskMessageTag;
import com.example.courselingo.task.dto.AnalysisTaskStateChangeCommand;
import com.example.courselingo.task.dto.CreateAnalysisTaskRequest;
import com.example.courselingo.task.dto.CreateAnalysisTaskResponse;
import com.example.courselingo.task.dto.TaskCommandResponse;
import com.example.courselingo.task.dto.TaskRetryResponse;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.entity.TaskLog;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.mapper.TaskLogMapper;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.task.service.AnalysisTaskStateService;
import com.example.courselingo.task.service.TaskCommandServiceImpl;
import com.example.courselingo.task.service.TaskCreationService;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.stream.Stream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.junit.jupiter.params.provider.MethodSource;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class TaskCommandServiceTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(
        Instant.parse("2026-06-27T14:00:00Z"),
        ZoneOffset.UTC
    );

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private TaskLogMapper taskLogMapper;

    @Mock
    private AnalysisTaskMessageProducer messageProducer;

    @Mock
    private AnalysisTaskStateService stateService;

    @Mock
    private TaskCreationService taskCreationService;

    private TaskCommandServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new TaskCommandServiceImpl(
            currentUserService,
            analysisTaskMapper,
            taskLogMapper,
            messageProducer,
            stateService,
            taskCreationService,
            FIXED_CLOCK
        );
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
    }

    @Test
    void ownerCanRetryOwnFailedTaskByCreatingNewTask() {
        AnalysisTask task = task("task_retry", 42L, AnalysisTaskStatus.FAILED);
        task.setErrorCode("ASR_FAILED");
        task.setErrorMessage("provider failed");
        when(analysisTaskMapper.selectByIdAndUserId("task_retry", 42L)).thenReturn(task);
        when(taskCreationService.create(any(CreateAnalysisTaskRequest.class), org.mockito.ArgumentMatchers.eq("Bearer access-token")))
            .thenReturn(new CreateAnalysisTaskResponse("task_new", "up_1", "QUEUED", "zh-CN"));

        TaskRetryResponse response;
        try (TracingScope ignored = TracingContextHolder.open(new TracingContext("trace_retry", "req_retry"))) {
            response = service.retry("task_retry", "Bearer access-token");
        }

        assertThat(response.originalTaskId()).isEqualTo("task_retry");
        assertThat(response.newTaskId()).isEqualTo("task_new");
        assertThat(response.status()).isEqualTo("QUEUED");
        assertThat(response.message()).isEqualTo("已创建新的分析任务");

        ArgumentCaptor<CreateAnalysisTaskRequest> requestCaptor = ArgumentCaptor.forClass(CreateAnalysisTaskRequest.class);
        verify(taskCreationService).create(requestCaptor.capture(), org.mockito.ArgumentMatchers.eq("Bearer access-token"));
        assertThat(requestCaptor.getValue().uploadId()).isEqualTo("up_1");
        assertThat(requestCaptor.getValue().targetLanguage()).isEqualTo("zh-CN");

        verify(analysisTaskMapper, never()).updateRetryingByIdAndUserId(any(AnalysisTask.class));
        verify(messageProducer, never()).send(eqTag(AnalysisTaskMessageTag.ANALYSIS_RETRY), any());
        assertThat(task.getStatus()).isEqualTo("FAILED");
        assertThat(task.getErrorCode()).isEqualTo("ASR_FAILED");
        assertThat(task.getErrorMessage()).isEqualTo("provider failed");
    }

    @Test
    void ownerCanRetryCanceledTaskByCreatingNewTask() {
        AnalysisTask task = task("task_canceled", 42L, AnalysisTaskStatus.CANCELED);
        task.setTargetLanguage("en");
        when(analysisTaskMapper.selectByIdAndUserId("task_canceled", 42L)).thenReturn(task);
        when(taskCreationService.create(any(CreateAnalysisTaskRequest.class), org.mockito.ArgumentMatchers.eq("Bearer access-token")))
            .thenReturn(new CreateAnalysisTaskResponse("task_new_cancel", "up_1", "QUEUED", "en"));

        TaskRetryResponse response = service.retry("task_canceled", "Bearer access-token");

        assertThat(response.originalTaskId()).isEqualTo("task_canceled");
        assertThat(response.newTaskId()).isEqualTo("task_new_cancel");
        assertThat(response.status()).isEqualTo("QUEUED");

        ArgumentCaptor<CreateAnalysisTaskRequest> requestCaptor = ArgumentCaptor.forClass(CreateAnalysisTaskRequest.class);
        verify(taskCreationService).create(requestCaptor.capture(), org.mockito.ArgumentMatchers.eq("Bearer access-token"));
        assertThat(requestCaptor.getValue().uploadId()).isEqualTo("up_1");
        assertThat(requestCaptor.getValue().targetLanguage()).isEqualTo("en");
    }

    @ParameterizedTest
    @EnumSource(value = AnalysisTaskStatus.class, names = {"SUCCEEDED", "RUNNING", "QUEUED", "CREATED", "RETRYING"})
    void retryRejectsNonRetryableStatuses(AnalysisTaskStatus status) {
        when(analysisTaskMapper.selectByIdAndUserId("task_retry", 42L))
            .thenReturn(task("task_retry", 42L, status));

        assertThatThrownBy(() -> service.retry("task_retry", "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_RETRY_NOT_ALLOWED);

        verify(analysisTaskMapper, never()).updateRetryingByIdAndUserId(any(AnalysisTask.class));
        verify(taskCreationService, never()).create(any(), any());
        verify(messageProducer, never()).send(any(), any());
    }

    @Test
    void retryRejectsMissingOrNonOwnerTaskWithoutLeakingUserId() {
        when(analysisTaskMapper.selectByIdAndUserId("task_missing", 42L)).thenReturn(null);

        assertThatThrownBy(() -> service.retry("task_missing", "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                BusinessException exception = (BusinessException) error;
                assertThat(exception.errorCode()).isEqualTo(ErrorCode.TASK_NOT_FOUND);
                assertThat(exception.getMessage()).doesNotContain("42");
                assertThat(exception.getMessage()).doesNotContain("userId");
            });

        verify(taskCreationService, never()).create(any(), any());
    }

    @Test
    void retryPropagatesUploadValidationFailureFromTaskCreation() {
        AnalysisTask task = task("task_retry", 42L, AnalysisTaskStatus.FAILED);
        when(analysisTaskMapper.selectByIdAndUserId("task_retry", 42L)).thenReturn(task);
        doThrow(new BusinessException(ErrorCode.UPLOAD_SESSION_NOT_FOUND))
            .when(taskCreationService).create(any(CreateAnalysisTaskRequest.class), org.mockito.ArgumentMatchers.eq("Bearer access-token"));

        assertThatThrownBy(() -> service.retry("task_retry", "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_NOT_FOUND);

        verify(analysisTaskMapper, never()).updateRetryingByIdAndUserId(any(AnalysisTask.class));
        verify(messageProducer, never()).send(any(), any());
    }

    @Test
    void retryPropagatesUploadNotCompletedFailureFromTaskCreation() {
        AnalysisTask task = task("task_retry", 42L, AnalysisTaskStatus.FAILED);
        when(analysisTaskMapper.selectByIdAndUserId("task_retry", 42L)).thenReturn(task);
        doThrow(new BusinessException(ErrorCode.UPLOAD_SESSION_STATUS_INVALID))
            .when(taskCreationService).create(any(CreateAnalysisTaskRequest.class), org.mockito.ArgumentMatchers.eq("Bearer access-token"));

        assertThatThrownBy(() -> service.retry("task_retry", "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);

        verify(analysisTaskMapper, never()).updateRetryingByIdAndUserId(any(AnalysisTask.class));
        verify(messageProducer, never()).send(any(), any());
    }

    @Test
    void retryRejectsRefreshTokenBeforeLoadingTask() {
        doThrow(new BusinessException(ErrorCode.AUTH_TOKEN_INVALID))
            .when(currentUserService).currentUser("Bearer refresh-token");

        assertThatThrownBy(() -> service.retry("task_retry", "Bearer refresh-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_TOKEN_INVALID);

        verify(analysisTaskMapper, never()).selectByIdAndUserId(any(), any());
        verify(taskCreationService, never()).create(any(), any());
    }

    @Test
    void retryCreationFailureDoesNotModifyOriginalTask() {
        AnalysisTask task = task("task_retry", 42L, AnalysisTaskStatus.FAILED);
        when(analysisTaskMapper.selectByIdAndUserId("task_retry", 42L)).thenReturn(task);
        doThrow(new BusinessException(ErrorCode.MQ_SEND_FAILED, "消息发送失败"))
            .when(taskCreationService).create(any(CreateAnalysisTaskRequest.class), org.mockito.ArgumentMatchers.eq("Bearer access-token"));

        assertThatThrownBy(() -> service.retry("task_retry", "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                BusinessException exception = (BusinessException) error;
                assertThat(exception.errorCode()).isEqualTo(ErrorCode.MQ_SEND_FAILED);
                assertThat(exception.getMessage()).doesNotContainIgnoringCase("token");
                assertThat(exception.getMessage()).doesNotContainIgnoringCase("secret");
                assertThat(exception.getMessage()).doesNotContainIgnoringCase("api key");
            });

        verify(analysisTaskMapper, never()).updateRetryingByIdAndUserId(any(AnalysisTask.class));
        verify(taskLogMapper, never()).insert(any(TaskLog.class));
        assertThat(task.getStatus()).isEqualTo("FAILED");
    }

    @ParameterizedTest
    @MethodSource("cancelableStatuses")
    void ownerCanCancelCancelableTaskAndMessageUsesCancelTagAndTaskIdKey(AnalysisTaskStatus status) {
        AnalysisTask task = task("task_cancel", 42L, status);
        when(analysisTaskMapper.selectByIdAndUserId("task_cancel", 42L)).thenReturn(task);

        TaskCommandResponse response;
        try (TracingScope ignored = TracingContextHolder.open(new TracingContext("trace_cancel", "req_cancel"))) {
            response = service.cancel("task_cancel", "Bearer access-token");
        }

        assertThat(response.taskId()).isEqualTo("task_cancel");
        assertThat(response.status()).isEqualTo("CANCELED");

        ArgumentCaptor<AnalysisTaskStateChangeCommand> commandCaptor =
            ArgumentCaptor.forClass(AnalysisTaskStateChangeCommand.class);
        verify(stateService).changeState(commandCaptor.capture());
        assertThat(commandCaptor.getValue().getTaskId()).isEqualTo("task_cancel");
        assertThat(commandCaptor.getValue().getUserId()).isEqualTo(42L);
        assertThat(commandCaptor.getValue().getTargetStatus()).isEqualTo(AnalysisTaskStatus.CANCELED);

        ArgumentCaptor<AnalysisTaskMessage> messageCaptor = ArgumentCaptor.forClass(AnalysisTaskMessage.class);
        verify(messageProducer).send(eqTag(AnalysisTaskMessageTag.ANALYSIS_CANCEL), messageCaptor.capture());
        assertThat(messageCaptor.getValue().taskId()).isEqualTo("task_cancel");
        assertThat(messageCaptor.getValue().userId()).isEqualTo(42L);
        assertThat(messageCaptor.getValue().requestId()).isEqualTo("req_cancel");
        assertThat(messageCaptor.getValue().traceId()).isEqualTo("trace_cancel");
    }

    @ParameterizedTest
    @EnumSource(value = AnalysisTaskStatus.class, names = {"SUCCEEDED", "FAILED", "CANCELED"})
    void cancelRejectsTerminalStatuses(AnalysisTaskStatus status) {
        when(analysisTaskMapper.selectByIdAndUserId("task_cancel", 42L))
            .thenReturn(task("task_cancel", 42L, status));

        assertThatThrownBy(() -> service.cancel("task_cancel", "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_INVALID_STATUS);

        verify(stateService, never()).changeState(any());
        verify(messageProducer, never()).send(any(), any());
    }

    @Test
    void cancelRejectsMissingOrNonOwnerTask() {
        when(analysisTaskMapper.selectByIdAndUserId("task_missing", 42L)).thenReturn(null);

        assertThatThrownBy(() -> service.cancel("task_missing", "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(stateService, never()).changeState(any());
    }

    @Test
    void cancelMqFailureWritesWarnLogAndDoesNotPretendSuccess() {
        when(analysisTaskMapper.selectByIdAndUserId("task_cancel", 42L))
            .thenReturn(task("task_cancel", 42L, AnalysisTaskStatus.RUNNING));
        doThrow(new BusinessException(ErrorCode.MQ_SEND_FAILED, "消息发送失败"))
            .when(messageProducer).send(any(), any());

        assertThatThrownBy(() -> service.cancel("task_cancel", "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MQ_SEND_FAILED);

        verify(stateService).changeState(any());
        assertThat(captureInsertedLog().getMessage()).contains("MQ send failed");
    }

    @Test
    void cancelRejectsRefreshTokenBeforeLoadingTask() {
        doThrow(new BusinessException(ErrorCode.AUTH_TOKEN_INVALID))
            .when(currentUserService).currentUser("Bearer refresh-token");

        assertThatThrownBy(() -> service.cancel("task_cancel", "Bearer refresh-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_TOKEN_INVALID);

        verify(analysisTaskMapper, never()).selectByIdAndUserId(any(), any());
    }

    private static Stream<AnalysisTaskStatus> cancelableStatuses() {
        return Stream.of(
            AnalysisTaskStatus.CREATED,
            AnalysisTaskStatus.QUEUED,
            AnalysisTaskStatus.RUNNING,
            AnalysisTaskStatus.RETRYING
        );
    }

    private TaskLog captureInsertedLog() {
        ArgumentCaptor<TaskLog> captor = ArgumentCaptor.forClass(TaskLog.class);
        verify(taskLogMapper).insert(captor.capture());
        return captor.getValue();
    }

    private static AnalysisTaskMessageTag eqTag(AnalysisTaskMessageTag tag) {
        return org.mockito.ArgumentMatchers.eq(tag);
    }

    private static AnalysisTask task(String taskId, Long userId, AnalysisTaskStatus status) {
        AnalysisTask task = new AnalysisTask();
        task.setId(taskId);
        task.setUserId(userId);
        task.setUploadId("up_1");
        task.setTargetLanguage("zh-CN");
        task.setStatus(status.name());
        task.setProgressPercent(40);
        task.setRetryCount(0);
        task.setMaxRetryCount(3);
        task.setCreatedAt(LocalDateTime.ofInstant(FIXED_CLOCK.instant(), ZoneOffset.UTC).minusMinutes(5));
        task.setUpdatedAt(LocalDateTime.ofInstant(FIXED_CLOCK.instant(), ZoneOffset.UTC).minusMinutes(1));
        return task;
    }
}
