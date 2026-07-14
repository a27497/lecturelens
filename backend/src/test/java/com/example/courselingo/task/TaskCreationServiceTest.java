package com.example.courselingo.task;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.lenient;
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
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.entity.TaskLog;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.mapper.TaskLogMapper;
import com.example.courselingo.task.model.AnalysisTaskStage;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.task.ratelimit.AnalysisRateLimitResult;
import com.example.courselingo.task.ratelimit.AnalysisRateLimitService;
import com.example.courselingo.task.service.AnalysisTaskStateService;
import com.example.courselingo.task.service.TaskCreationServiceImpl;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
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
class TaskCreationServiceTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(
        Instant.parse("2026-06-27T15:00:00Z"),
        ZoneOffset.UTC
    );

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private UploadSessionMapper uploadSessionMapper;

    @Mock
    private AnalysisRateLimitService rateLimitService;

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private AnalysisTaskStateService stateService;

    @Mock
    private AnalysisTaskMessageProducer messageProducer;

    @Mock
    private TaskLogMapper taskLogMapper;

    private TaskCreationServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new TaskCreationServiceImpl(
            currentUserService,
            uploadSessionMapper,
            rateLimitService,
            analysisTaskMapper,
            stateService,
            messageProducer,
            taskLogMapper,
            FIXED_CLOCK
        );
        lenient().when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
    }

    @Test
    void ownerCanCreateTaskFromStoredSessionAndMessageUsesCreatedTag() {
        when(uploadSessionMapper.selectByIdAndUserId("up_1", 42L)).thenReturn(uploadSession("up_1", 42L, "STORED"));
        when(rateLimitService.checkAndConsume(42L)).thenReturn(AnalysisRateLimitResult.allowed(10, 9));
        when(analysisTaskMapper.insert(any(AnalysisTask.class))).thenReturn(1);

        CreateAnalysisTaskResponse response;
        try (TracingScope ignored = TracingContextHolder.open(new TracingContext("trace_create", "req_create"))) {
            response = service.create(
                new CreateAnalysisTaskRequest("up_1", "zh-CN"),
                "Bearer access-token"
            );
        }

        AnalysisTask inserted = captureInsertedTask();
        assertThat(inserted.getId()).startsWith("task_");
        assertThat(inserted.getUserId()).isEqualTo(42L);
        assertThat(inserted.getUploadId()).isEqualTo("up_1");
        assertThat(inserted.getTargetLanguage()).isEqualTo("zh-CN");
        assertThat(inserted.getStatus()).isEqualTo("CREATED");
        assertThat(inserted.getProgressPercent()).isZero();
        assertThat(inserted.getCurrentStage()).isEqualTo("CREATED");
        assertThat(inserted.getRetryCount()).isZero();
        assertThat(inserted.getMaxRetryCount()).isEqualTo(3);
        assertThat(inserted.getCreatedAt()).isEqualTo(now());

        ArgumentCaptor<AnalysisTaskStateChangeCommand> stateCaptor =
            ArgumentCaptor.forClass(AnalysisTaskStateChangeCommand.class);
        verify(stateService).changeState(stateCaptor.capture());
        assertThat(stateCaptor.getValue().getTaskId()).isEqualTo(inserted.getId());
        assertThat(stateCaptor.getValue().getUserId()).isEqualTo(42L);
        assertThat(stateCaptor.getValue().getTargetStatus()).isEqualTo(AnalysisTaskStatus.QUEUED);
        assertThat(stateCaptor.getValue().getProgressPercent()).isZero();
        assertThat(stateCaptor.getValue().getStage()).isEqualTo(AnalysisTaskStage.QUEUED);

        ArgumentCaptor<AnalysisTaskMessage> messageCaptor = ArgumentCaptor.forClass(AnalysisTaskMessage.class);
        verify(messageProducer).send(eq(AnalysisTaskMessageTag.ANALYSIS_CREATED), messageCaptor.capture());
        AnalysisTaskMessage message = messageCaptor.getValue();
        assertThat(message.taskId()).isEqualTo(inserted.getId());
        assertThat(message.uploadId()).isEqualTo("up_1");
        assertThat(message.userId()).isEqualTo(42L);
        assertThat(message.targetLanguage()).isEqualTo("zh-CN");
        assertThat(message.requestId()).isEqualTo("req_create");
        assertThat(message.traceId()).isEqualTo("trace_create");
        assertThat(message.createdAt()).isEqualTo(FIXED_CLOCK.instant());

        assertThat(response.taskId()).isEqualTo(inserted.getId());
        assertThat(response.uploadId()).isEqualTo("up_1");
        assertThat(response.status()).isEqualTo("QUEUED");
        assertThat(response.targetLanguage()).isEqualTo("zh-CN");
    }

    @Test
    void legacyUploadedSessionCanStillCreateTask() {
        when(uploadSessionMapper.selectByIdAndUserId("up_1", 42L)).thenReturn(uploadSession("up_1", 42L, "UPLOADED"));
        when(rateLimitService.checkAndConsume(42L)).thenReturn(AnalysisRateLimitResult.allowed(10, 9));
        when(analysisTaskMapper.insert(any(AnalysisTask.class))).thenReturn(1);

        CreateAnalysisTaskResponse response = service.create(
            new CreateAnalysisTaskRequest("up_1", "zh-CN"),
            "Bearer access-token"
        );

        assertThat(response.status()).isEqualTo("QUEUED");
    }

    @Test
    void missingOrNonOwnerUploadFailsBeforeRateLimitAndTaskInsert() {
        when(uploadSessionMapper.selectByIdAndUserId("up_missing", 42L)).thenReturn(null);

        assertThatThrownBy(() ->
            service.create(new CreateAnalysisTaskRequest("up_missing", "zh-CN"), "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_NOT_FOUND);

        verify(rateLimitService, never()).checkAndConsume(any());
        verify(analysisTaskMapper, never()).insert(any(AnalysisTask.class));
        verify(messageProducer, never()).send(any(), any());
    }

    @Test
    void unfinishedAndUnknownUploadStatusesCannotCreateTask() {
        for (String status : new String[] {"CREATED", "UPLOADING", "MERGING", "FAILED", "CANCELLED", "UNKNOWN"}) {
            when(uploadSessionMapper.selectByIdAndUserId("up_1", 42L)).thenReturn(uploadSession("up_1", 42L, status));

            assertThatThrownBy(() ->
                service.create(new CreateAnalysisTaskRequest("up_1", "zh-CN"), "Bearer access-token"))
                .isInstanceOf(BusinessException.class)
                .extracting("errorCode")
                .isEqualTo(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);
        }

        verify(rateLimitService, never()).checkAndConsume(any());
        verify(analysisTaskMapper, never()).insert(any(AnalysisTask.class));
    }

    @Test
    void rateLimitRejectedDoesNotInsertTaskOrExposeRedisKey() {
        when(uploadSessionMapper.selectByIdAndUserId("up_1", 42L)).thenReturn(uploadSession("up_1", 42L, "UPLOADED"));
        when(rateLimitService.checkAndConsume(42L)).thenReturn(AnalysisRateLimitResult.blocked(10, 60));

        assertThatThrownBy(() ->
            service.create(new CreateAnalysisTaskRequest("up_1", "zh-CN"), "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                BusinessException exception = (BusinessException) error;
                assertThat(exception.errorCode()).isEqualTo(ErrorCode.TASK_RATE_LIMITED);
                assertThat(exception.getMessage()).doesNotContain("cl:rate");
                assertThat(exception.getMessage()).doesNotContain("42");
                assertThat(exception.getMessage()).doesNotContain("userId");
            });

        verify(analysisTaskMapper, never()).insert(any(AnalysisTask.class));
        verify(stateService, never()).changeState(any());
        verify(messageProducer, never()).send(any(), any());
    }

    @Test
    void refreshTokenFailsBeforeUploadLookup() {
        doThrow(new BusinessException(ErrorCode.AUTH_TOKEN_INVALID))
            .when(currentUserService).currentUser("Bearer refresh-token");

        assertThatThrownBy(() ->
            service.create(new CreateAnalysisTaskRequest("up_1", "zh-CN"), "Bearer refresh-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_TOKEN_INVALID);

        verify(uploadSessionMapper, never()).selectByIdAndUserId(any(), any());
    }

    @Test
    void invalidUploadIdFailsBeforeAuthLookup() {
        assertThatThrownBy(() ->
            service.create(new CreateAnalysisTaskRequest("../up_1", "zh-CN"), "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_SESSION_ID);

        verify(currentUserService, never()).currentUser(any());
    }

    @Test
    void targetLanguageTooLongFailsBeforeAuthLookup() {
        assertThatThrownBy(() ->
            service.create(new CreateAnalysisTaskRequest("up_1", "x".repeat(33)), "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);

        verify(currentUserService, never()).currentUser(any());
    }

    @Test
    void mqFailureWritesWarnLogAndDoesNotPretendSuccess() {
        when(uploadSessionMapper.selectByIdAndUserId("up_1", 42L)).thenReturn(uploadSession("up_1", 42L, "UPLOADED"));
        when(rateLimitService.checkAndConsume(42L)).thenReturn(AnalysisRateLimitResult.allowed(10, 9));
        when(analysisTaskMapper.insert(any(AnalysisTask.class))).thenReturn(1);
        doThrow(new BusinessException(ErrorCode.MQ_SEND_FAILED, "message send failed"))
            .when(messageProducer).send(any(), any());

        assertThatThrownBy(() ->
            service.create(new CreateAnalysisTaskRequest("up_1", "zh-CN"), "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MQ_SEND_FAILED);

        verify(stateService).changeState(any());
        TaskLog warnLog = captureInsertedLog();
        assertThat(warnLog.getLevel()).isEqualTo("WARN");
        assertThat(warnLog.getStage()).isEqualTo("QUEUED");
        assertThat(warnLog.getMessage()).contains("MQ send failed");
        assertThat(warnLog.getMessage()).doesNotContainIgnoringCase("token");
        assertThat(warnLog.getMessage()).doesNotContainIgnoringCase("secret");
    }

    private AnalysisTask captureInsertedTask() {
        ArgumentCaptor<AnalysisTask> captor = ArgumentCaptor.forClass(AnalysisTask.class);
        verify(analysisTaskMapper).insert(captor.capture());
        return captor.getValue();
    }

    private TaskLog captureInsertedLog() {
        ArgumentCaptor<TaskLog> captor = ArgumentCaptor.forClass(TaskLog.class);
        verify(taskLogMapper).insert(captor.capture());
        return captor.getValue();
    }

    private static UploadSession uploadSession(String uploadId, Long userId, String status) {
        UploadSession uploadSession = new UploadSession();
        uploadSession.setId(uploadId);
        uploadSession.setUserId(userId);
        uploadSession.setStatus(status);
        return uploadSession;
    }

    private static LocalDateTime now() {
        return LocalDateTime.ofInstant(FIXED_CLOCK.instant(), FIXED_CLOCK.getZone());
    }
}
