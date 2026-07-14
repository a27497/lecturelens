package com.example.courselingo.task.service;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.dto.TaskDetailResponse;
import com.example.courselingo.task.dto.TaskListQuery;
import com.example.courselingo.task.dto.TaskListResponse;
import com.example.courselingo.task.dto.TaskSummaryResponse;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;

@Service
public class TaskQueryServiceImpl implements TaskQueryService {

    private static final int DEFAULT_PAGE = 1;
    private static final int DEFAULT_PAGE_SIZE = 20;
    private static final int MAX_PAGE_SIZE = 100;
    private static final int MAX_ERROR_MESSAGE_LENGTH = 512;
    private static final Pattern WINDOWS_PATH_PATTERN =
        Pattern.compile("(?i)[a-z]:[\\\\/][^\\s,;]+");
    private static final Pattern SENSITIVE_ASSIGNMENT_PATTERN = Pattern.compile(
        "(?i)(access[_-]?token|refresh[_-]?token|api[_-]?key|secret|password(hash)?|token)\\s*[:=]\\s*[^\\s,;]+"
    );
    private static final Pattern BEARER_PATTERN = Pattern.compile("(?i)bearer\\s+[^\\s,;]+");

    private final CurrentUserService currentUserService;
    private final AnalysisTaskMapper analysisTaskMapper;

    public TaskQueryServiceImpl(CurrentUserService currentUserService, AnalysisTaskMapper analysisTaskMapper) {
        this.currentUserService = currentUserService;
        this.analysisTaskMapper = analysisTaskMapper;
    }

    @Override
    public TaskListResponse list(TaskListQuery query, String authorizationHeader) {
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        int page = normalizePage(query);
        int pageSize = normalizePageSize(query);
        String status = normalizeStatus(query);
        long offset = (long) (page - 1) * pageSize;
        List<TaskSummaryResponse> items = analysisTaskMapper
            .selectPageByUserId(currentUser.userId(), status, offset, pageSize)
            .stream()
            .map(this::toSummaryResponse)
            .toList();
        long total = analysisTaskMapper.countByUserId(currentUser.userId(), status);
        return new TaskListResponse(items, page, pageSize, total);
    }

    @Override
    public TaskDetailResponse detail(String taskId, String authorizationHeader) {
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        if (taskId == null || taskId.isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(taskId, currentUser.userId());
        if (task == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        return toDetailResponse(task);
    }

    private static int normalizePage(TaskListQuery query) {
        Integer page = query == null ? null : query.page();
        if (page == null) {
            return DEFAULT_PAGE;
        }
        if (page < 1) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        return page;
    }

    private static int normalizePageSize(TaskListQuery query) {
        Integer pageSize = query == null ? null : query.pageSize();
        if (pageSize == null) {
            return DEFAULT_PAGE_SIZE;
        }
        if (pageSize < 1 || pageSize > MAX_PAGE_SIZE) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        return pageSize;
    }

    private static String normalizeStatus(TaskListQuery query) {
        String status = query == null ? null : query.status();
        if (status == null || status.isBlank()) {
            return null;
        }
        try {
            return AnalysisTaskStatus.valueOf(status.trim().toUpperCase(Locale.ROOT)).name();
        } catch (IllegalArgumentException ex) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
    }

    private TaskSummaryResponse toSummaryResponse(AnalysisTask task) {
        return new TaskSummaryResponse(
            task.getId(),
            task.getUploadId(),
            task.getTargetLanguage(),
            task.getStatus(),
            task.getProgressPercent(),
            task.getCurrentStage(),
            task.getErrorCode(),
            sanitizeErrorMessage(task.getErrorMessage()),
            task.getRetryCount(),
            task.getMaxRetryCount(),
            task.getCreatedAt(),
            task.getUpdatedAt(),
            task.getStartedAt(),
            task.getFinishedAt()
        );
    }

    private TaskDetailResponse toDetailResponse(AnalysisTask task) {
        return new TaskDetailResponse(
            task.getId(),
            task.getUploadId(),
            task.getTargetLanguage(),
            task.getStatus(),
            task.getProgressPercent(),
            task.getCurrentStage(),
            task.getErrorCode(),
            sanitizeErrorMessage(task.getErrorMessage()),
            task.getRetryCount(),
            task.getMaxRetryCount(),
            task.getCreatedAt(),
            task.getUpdatedAt(),
            task.getStartedAt(),
            task.getFinishedAt()
        );
    }

    private static String sanitizeErrorMessage(String errorMessage) {
        if (errorMessage == null) {
            return null;
        }
        String sanitized = errorMessage.replaceAll("[\\r\\n\\t]+", " ");
        sanitized = WINDOWS_PATH_PATTERN.matcher(sanitized).replaceAll("[path]");
        sanitized = SENSITIVE_ASSIGNMENT_PATTERN.matcher(sanitized).replaceAll("[redacted]");
        sanitized = BEARER_PATTERN.matcher(sanitized).replaceAll("[redacted]");
        sanitized = sanitized.trim();
        if (sanitized.length() <= MAX_ERROR_MESSAGE_LENGTH) {
            return sanitized;
        }
        return sanitized.substring(0, MAX_ERROR_MESSAGE_LENGTH);
    }
}
