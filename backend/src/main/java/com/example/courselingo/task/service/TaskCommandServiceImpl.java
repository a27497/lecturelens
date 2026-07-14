package com.example.courselingo.task.service;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.tracing.TracingContext;
import com.example.courselingo.common.tracing.TracingContextHolder;
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
import com.example.courselingo.task.model.AnalysisTaskStage;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.EnumSet;
import java.util.Set;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class TaskCommandServiceImpl implements TaskCommandService {

    private static final Set<AnalysisTaskStatus> CANCELABLE_STATUSES = EnumSet.of(
        AnalysisTaskStatus.CREATED,
        AnalysisTaskStatus.QUEUED,
        AnalysisTaskStatus.RUNNING,
        AnalysisTaskStatus.RETRYING
    );

    private final CurrentUserService currentUserService;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final TaskLogMapper taskLogMapper;
    private final AnalysisTaskMessageProducer messageProducer;
    private final AnalysisTaskStateService stateService;
    private final TaskCreationService taskCreationService;
    private final Clock clock;

    @Autowired
    public TaskCommandServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        TaskLogMapper taskLogMapper,
        AnalysisTaskMessageProducer messageProducer,
        AnalysisTaskStateService stateService,
        TaskCreationService taskCreationService
    ) {
        this(
            currentUserService,
            analysisTaskMapper,
            taskLogMapper,
            messageProducer,
            stateService,
            taskCreationService,
            Clock.systemDefaultZone()
        );
    }

    public TaskCommandServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        TaskLogMapper taskLogMapper,
        AnalysisTaskMessageProducer messageProducer,
        AnalysisTaskStateService stateService,
        TaskCreationService taskCreationService,
        Clock clock
    ) {
        this.currentUserService = currentUserService;
        this.analysisTaskMapper = analysisTaskMapper;
        this.taskLogMapper = taskLogMapper;
        this.messageProducer = messageProducer;
        this.stateService = stateService;
        this.taskCreationService = taskCreationService;
        this.clock = clock;
    }

    @Override
    public TaskRetryResponse retry(String taskId, String authorizationHeader) {
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        AnalysisTask task = loadOwnedTask(taskId, currentUser.userId());
        AnalysisTaskStatus currentStatus = AnalysisTaskStatus.fromDatabaseValue(task.getStatus());
        if (currentStatus != AnalysisTaskStatus.FAILED && currentStatus != AnalysisTaskStatus.CANCELED) {
            throw retryNotAllowed(currentStatus);
        }

        CreateAnalysisTaskResponse created = taskCreationService.create(
            new CreateAnalysisTaskRequest(task.getUploadId(), task.getTargetLanguage()),
            authorizationHeader
        );
        return new TaskRetryResponse(
            task.getId(),
            created.taskId(),
            created.status(),
            "已创建新的分析任务"
        );
    }

    @Override
    public TaskCommandResponse cancel(String taskId, String authorizationHeader) {
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        AnalysisTask task = loadOwnedTask(taskId, currentUser.userId());
        AnalysisTaskStatus currentStatus = AnalysisTaskStatus.fromDatabaseValue(task.getStatus());
        if (!CANCELABLE_STATUSES.contains(currentStatus)) {
            throw new BusinessException(ErrorCode.TASK_INVALID_STATUS);
        }

        stateService.changeState(AnalysisTaskStateChangeCommand.builder()
            .taskId(task.getId())
            .userId(currentUser.userId())
            .targetStatus(AnalysisTaskStatus.CANCELED)
            .progressPercent(task.getProgressPercent())
            .stage(null)
            .build());
        sendMessage(AnalysisTaskMessageTag.ANALYSIS_CANCEL, task, "cancel");

        return new TaskCommandResponse(task.getId(), AnalysisTaskStatus.CANCELED.name());
    }

    private AnalysisTask loadOwnedTask(String taskId, Long userId) {
        if (taskId == null || taskId.isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(taskId, userId);
        if (task == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        return task;
    }

    private BusinessException retryNotAllowed(AnalysisTaskStatus currentStatus) {
        if (currentStatus == AnalysisTaskStatus.SUCCEEDED) {
            return new BusinessException(ErrorCode.TASK_RETRY_NOT_ALLOWED, "任务已完成，无需重新分析");
        }
        if (CANCELABLE_STATUSES.contains(currentStatus)) {
            return new BusinessException(ErrorCode.TASK_RETRY_NOT_ALLOWED, "任务正在处理中，不能重复分析");
        }
        return new BusinessException(ErrorCode.TASK_RETRY_NOT_ALLOWED, "只能重新分析失败或已取消的任务");
    }

    private void sendMessage(AnalysisTaskMessageTag tag, AnalysisTask task, String action) {
        try {
            messageProducer.send(tag, buildMessage(task));
        } catch (BusinessException exception) {
            writeLog(task, "WARN", task.getStatus(), "MQ send failed for " + action);
            throw exception;
        }
    }

    private AnalysisTaskMessage buildMessage(AnalysisTask task) {
        TracingContext tracingContext = TracingContextHolder.currentOrCreate();
        return new AnalysisTaskMessage(
            task.getId(),
            task.getUploadId(),
            task.getUserId(),
            task.getTargetLanguage(),
            tracingContext.requestId(),
            tracingContext.traceId(),
            clock.instant()
        );
    }

    private void writeLog(AnalysisTask task, String level, String stage, String message) {
        TaskLog taskLog = new TaskLog();
        taskLog.setTaskId(task.getId());
        taskLog.setUserId(task.getUserId());
        taskLog.setLevel(level);
        taskLog.setStage(stage);
        taskLog.setMessage(message);
        taskLog.setCreatedAt(LocalDateTime.ofInstant(clock.instant(), clock.getZone()));
        taskLogMapper.insert(taskLog);
    }

}
