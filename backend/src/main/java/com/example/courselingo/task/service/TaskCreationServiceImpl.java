package com.example.courselingo.task.service;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.metrics.BusinessMetrics;
import com.example.courselingo.common.tracing.TracingContext;
import com.example.courselingo.common.tracing.TracingContextHolder;
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
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.UUID;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class TaskCreationServiceImpl implements TaskCreationService {

    private static final int MAX_RETRY_COUNT = 3;
    private static final Pattern UPLOAD_ID_PATTERN = Pattern.compile("[A-Za-z0-9][A-Za-z0-9_-]{0,63}");
    private static final Set<String> TASK_CREATABLE_UPLOAD_STATUSES = Set.of("STORED", "UPLOADED");

    private final CurrentUserService currentUserService;
    private final UploadSessionMapper uploadSessionMapper;
    private final AnalysisRateLimitService rateLimitService;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final AnalysisTaskStateService stateService;
    private final AnalysisTaskMessageProducer messageProducer;
    private final TaskLogMapper taskLogMapper;
    private final Clock clock;
    private final BusinessMetrics businessMetrics;

    @Autowired
    public TaskCreationServiceImpl(
        CurrentUserService currentUserService,
        UploadSessionMapper uploadSessionMapper,
        AnalysisRateLimitService rateLimitService,
        AnalysisTaskMapper analysisTaskMapper,
        AnalysisTaskStateService stateService,
        AnalysisTaskMessageProducer messageProducer,
        TaskLogMapper taskLogMapper,
        BusinessMetrics businessMetrics
    ) {
        this(
            currentUserService,
            uploadSessionMapper,
            rateLimitService,
            analysisTaskMapper,
            stateService,
            messageProducer,
            taskLogMapper,
            Clock.systemDefaultZone(),
            businessMetrics
        );
    }

    public TaskCreationServiceImpl(
        CurrentUserService currentUserService,
        UploadSessionMapper uploadSessionMapper,
        AnalysisRateLimitService rateLimitService,
        AnalysisTaskMapper analysisTaskMapper,
        AnalysisTaskStateService stateService,
        AnalysisTaskMessageProducer messageProducer,
        TaskLogMapper taskLogMapper,
        Clock clock
    ) {
        this(
            currentUserService,
            uploadSessionMapper,
            rateLimitService,
            analysisTaskMapper,
            stateService,
            messageProducer,
            taskLogMapper,
            clock,
            BusinessMetrics.noop()
        );
    }

    public TaskCreationServiceImpl(
        CurrentUserService currentUserService,
        UploadSessionMapper uploadSessionMapper,
        AnalysisRateLimitService rateLimitService,
        AnalysisTaskMapper analysisTaskMapper,
        AnalysisTaskStateService stateService,
        AnalysisTaskMessageProducer messageProducer,
        TaskLogMapper taskLogMapper,
        Clock clock,
        BusinessMetrics businessMetrics
    ) {
        this.currentUserService = currentUserService;
        this.uploadSessionMapper = uploadSessionMapper;
        this.rateLimitService = rateLimitService;
        this.analysisTaskMapper = analysisTaskMapper;
        this.stateService = stateService;
        this.messageProducer = messageProducer;
        this.taskLogMapper = taskLogMapper;
        this.clock = clock;
        this.businessMetrics = businessMetrics == null ? BusinessMetrics.noop() : businessMetrics;
    }

    @Override
    public CreateAnalysisTaskResponse create(CreateAnalysisTaskRequest request, String authorizationHeader) {
        String uploadId = normalizeUploadId(request);
        String targetLanguage = normalizeTargetLanguage(request);
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);

        UploadSession uploadSession = uploadSessionMapper.selectByIdAndUserId(uploadId, currentUser.userId());
        if (uploadSession == null) {
            throw new BusinessException(ErrorCode.UPLOAD_SESSION_NOT_FOUND);
        }
        if (!TASK_CREATABLE_UPLOAD_STATUSES.contains(uploadSession.getStatus())) {
            throw new BusinessException(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);
        }

        AnalysisRateLimitResult rateLimit = rateLimitService.checkAndConsume(currentUser.userId());
        if (rateLimit == null || !rateLimit.allowed()) {
            throw new BusinessException(ErrorCode.TASK_RATE_LIMITED);
        }

        AnalysisTask task = buildCreatedTask(uploadId, currentUser.userId(), targetLanguage);
        int inserted = analysisTaskMapper.insert(task);
        if (inserted != 1) {
            throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR);
        }

        stateService.changeState(AnalysisTaskStateChangeCommand.builder()
            .taskId(task.getId())
            .userId(task.getUserId())
            .targetStatus(AnalysisTaskStatus.QUEUED)
            .progressPercent(0)
            .stage(AnalysisTaskStage.QUEUED)
            .build());

        sendCreatedMessage(task);
        businessMetrics.incrementTaskCreated("success");
        return new CreateAnalysisTaskResponse(
            task.getId(),
            task.getUploadId(),
            AnalysisTaskStatus.QUEUED.name(),
            task.getTargetLanguage()
        );
    }

    private String normalizeUploadId(CreateAnalysisTaskRequest request) {
        if (request == null || request.uploadId() == null) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_SESSION_ID);
        }
        String uploadId = request.uploadId().trim();
        if (uploadId.isBlank() || !UPLOAD_ID_PATTERN.matcher(uploadId).matches()) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_SESSION_ID);
        }
        return uploadId;
    }

    private String normalizeTargetLanguage(CreateAnalysisTaskRequest request) {
        if (request == null || request.targetLanguage() == null) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        String targetLanguage = request.targetLanguage().trim();
        if (targetLanguage.isBlank() || targetLanguage.length() > 32) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        return targetLanguage;
    }

    private AnalysisTask buildCreatedTask(String uploadId, Long userId, String targetLanguage) {
        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        AnalysisTask task = new AnalysisTask();
        task.setId("task_" + UUID.randomUUID().toString().replace("-", ""));
        task.setUserId(userId);
        task.setUploadId(uploadId);
        task.setTargetLanguage(targetLanguage);
        task.setStatus(AnalysisTaskStatus.CREATED.name());
        task.setProgressPercent(0);
        task.setCurrentStage(AnalysisTaskStage.CREATED.name());
        task.setRetryCount(0);
        task.setMaxRetryCount(MAX_RETRY_COUNT);
        task.setCreatedAt(now);
        task.setUpdatedAt(now);
        return task;
    }

    private void sendCreatedMessage(AnalysisTask task) {
        try {
            messageProducer.send(AnalysisTaskMessageTag.ANALYSIS_CREATED, buildMessage(task));
        } catch (BusinessException exception) {
            writeMqFailureLog(task);
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

    private void writeMqFailureLog(AnalysisTask task) {
        TaskLog taskLog = new TaskLog();
        taskLog.setTaskId(task.getId());
        taskLog.setUserId(task.getUserId());
        taskLog.setLevel("WARN");
        taskLog.setStage(AnalysisTaskStage.QUEUED.name());
        taskLog.setMessage("MQ send failed for create");
        taskLog.setCreatedAt(LocalDateTime.ofInstant(clock.instant(), clock.getZone()));
        taskLogMapper.insert(taskLog);
    }
}
