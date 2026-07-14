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

@Service
public class TaskBatchDeleteServiceImpl implements TaskBatchDeleteService {

    private static final int MAX_BATCH_SIZE = 100;
    private static final int MAX_TASK_ID_LENGTH = 64;
    private static final Set<String> DELETABLE_STATUSES = Set.of("SUCCEEDED", "FAILED", "CANCELED");

    private final CurrentUserService currentUserService;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final Clock clock;

    @Autowired
    public TaskBatchDeleteServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper
    ) {
        this(currentUserService, analysisTaskMapper, Clock.systemDefaultZone());
    }

    TaskBatchDeleteServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        Clock clock
    ) {
        this.currentUserService = currentUserService;
        this.analysisTaskMapper = analysisTaskMapper;
        this.clock = clock;
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
        return new TaskBatchDeleteResponse(taskIds.size(), deletedCount);
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
