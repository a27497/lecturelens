package com.example.courselingo.task.service;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.dto.TaskBatchDeleteRequest;
import com.example.courselingo.task.dto.TaskBatchDeleteResponse;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.vision.keyframe.VideoKeyframeEvidenceLifecycleService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Service
public class TaskBatchDeleteServiceImpl implements TaskBatchDeleteService {

    private static final Logger LOGGER = LoggerFactory.getLogger(TaskBatchDeleteServiceImpl.class);
    private static final int MAX_BATCH_SIZE = 100;
    private static final int MAX_TASK_ID_LENGTH = 64;
    private static final Set<String> DELETABLE_STATUSES = Set.of("SUCCEEDED", "FAILED", "CANCELED");

    private final CurrentUserService currentUserService;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final Clock clock;
    private final VideoKeyframeEvidenceLifecycleService evidenceLifecycleService;

    @Autowired
    public TaskBatchDeleteServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        VideoKeyframeEvidenceLifecycleService evidenceLifecycleService
    ) {
        this(currentUserService, analysisTaskMapper, Clock.systemDefaultZone(), evidenceLifecycleService);
    }

    TaskBatchDeleteServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        Clock clock
    ) {
        this(currentUserService, analysisTaskMapper, clock, null);
    }

    TaskBatchDeleteServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        Clock clock,
        VideoKeyframeEvidenceLifecycleService evidenceLifecycleService
    ) {
        this.currentUserService = currentUserService;
        this.analysisTaskMapper = analysisTaskMapper;
        this.clock = clock;
        this.evidenceLifecycleService = evidenceLifecycleService;
    }

    @Override
    @Transactional
    public TaskBatchDeleteResponse delete(TaskBatchDeleteRequest request, String authorizationHeader) {
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        List<String> taskIds = normalizeTaskIds(request);
        List<AnalysisTask> tasks = analysisTaskMapper.selectByIdsAndUserIdIncludingDeleted(
            taskIds,
            currentUser.userId()
        );
        if (tasks.size() != taskIds.size()) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }

        List<AnalysisTask> activeTasks = tasks.stream()
            .filter(task -> task.getDeletedAt() == null)
            .toList();
        if (activeTasks.stream().anyMatch(task -> !DELETABLE_STATUSES.contains(task.getStatus()))) {
            throw new BusinessException(ErrorCode.TASK_DELETE_NOT_ALLOWED);
        }
        if (activeTasks.isEmpty()) {
            cleanupEvidence(tasks, currentUser.userId());
            return new TaskBatchDeleteResponse(taskIds.size(), 0);
        }

        List<String> activeTaskIds = activeTasks.stream().map(AnalysisTask::getId).toList();
        LocalDateTime deletedAt = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        int deletedCount = analysisTaskMapper.softDeleteByIdsAndUserId(
            activeTaskIds,
            currentUser.userId(),
            DELETABLE_STATUSES,
            deletedAt
        );
        if (deletedCount != activeTaskIds.size()) {
            throw new BusinessException(ErrorCode.TASK_DELETE_NOT_ALLOWED);
        }
        cleanupEvidence(activeTasks, currentUser.userId());
        return new TaskBatchDeleteResponse(taskIds.size(), deletedCount);
    }

    private void cleanupEvidence(List<AnalysisTask> tasks, Long userId) {
        if (evidenceLifecycleService == null) {
            return;
        }
        for (AnalysisTask task : tasks) {
            try {
                evidenceLifecycleService.cleanupTaskEvidence(task.getId(), userId);
            } catch (RuntimeException exception) {
                LOGGER.warn(
                    "event=deleted_task_evidence_cleanup_failed taskId={} errorType={}",
                    SafeLogSanitizer.sanitize(task.getId()),
                    exception.getClass().getSimpleName()
                );
            }
        }
    }

    private static List<String> normalizeTaskIds(TaskBatchDeleteRequest request) {
        if (request == null || request.taskIds() == null || request.taskIds().isEmpty()
            || request.taskIds().size() > MAX_BATCH_SIZE) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        LinkedHashSet<String> uniqueTaskIds = new LinkedHashSet<>();
        for (String taskId : request.taskIds()) {
            if (taskId == null || taskId.isBlank()) {
                throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
            }
            String normalizedTaskId = taskId.trim();
            if (normalizedTaskId.length() > MAX_TASK_ID_LENGTH) {
                throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
            }
            uniqueTaskIds.add(normalizedTaskId);
        }
        if (uniqueTaskIds.size() > MAX_BATCH_SIZE) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        return List.copyOf(uniqueTaskIds);
    }
}
