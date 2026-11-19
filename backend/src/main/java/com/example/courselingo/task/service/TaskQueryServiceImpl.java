package com.example.courselingo.task.service;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.time.UtcTimestamps;
import com.example.courselingo.task.dto.TaskDetailResponse;
import com.example.courselingo.task.dto.TaskListQuery;
import com.example.courselingo.task.dto.TaskListResponse;
import com.example.courselingo.task.dto.TaskSummaryResponse;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
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
    private final UploadSessionMapper uploadSessionMapper;

    public TaskQueryServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        UploadSessionMapper uploadSessionMapper
    ) {
        this.currentUserService = currentUserService;
        this.analysisTaskMapper = analysisTaskMapper;
        this.uploadSessionMapper = uploadSessionMapper;
    }

    @Override
    public TaskListResponse list(TaskListQuery query, String authorizationHeader) {
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        int page = normalizePage(query);
        int pageSize = normalizePageSize(query);
        String status = normalizeStatus(query);
        long offset = (long) (page - 1) * pageSize;
        List<AnalysisTask> tasks = analysisTaskMapper.selectPageByUserId(currentUser.userId(), status, offset, pageSize);
        Map<String, String> names = courseNames(tasks, currentUser.userId());
        List<TaskSummaryResponse> items = tasks.stream()
            .map(task -> toSummaryResponse(task, names.get(task.getUploadId())))
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
        Map<String, String> names = courseNames(List.of(task), currentUser.userId());
        return toDetailResponse(task, names.get(task.getUploadId()));
    }

    /**
     * Display names come from the caller's own upload sessions only. The task row is already
     * owner-filtered; the upload lookup repeats the owner condition and drops any row whose owner
     * differs, so a mismatched upload ID can never surface another user's file name.
     */
    private Map<String, String> courseNames(List<AnalysisTask> tasks, Long userId) {
        List<String> uploadIds = tasks.stream()
            .map(AnalysisTask::getUploadId)
            .filter(Objects::nonNull)
            .distinct()
            .toList();
        if (uploadIds.isEmpty()) {
            return Collections.emptyMap();
        }
        Map<String, String> names = new HashMap<>();
        for (UploadSession upload : uploadSessionMapper.selectByIdsAndUserId(uploadIds, userId)) {
            if (Objects.equals(upload.getUserId(), userId)) {
                names.put(upload.getId(), displayName(upload.getFilename()));
            }
        }
        return names;
    }

    /** Upload validation already rejects paths and control characters. */
    public static String displayName(String filename) {
        if (filename == null) {
            return null;
        }
        String name = filename.strip();
        int dot = name.lastIndexOf('.');
        if (dot >= 0) {
            name = name.substring(0, dot).strip();
        }
        return name.isEmpty() ? null : name;
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

    private TaskSummaryResponse toSummaryResponse(AnalysisTask task, String courseName) {
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
            UtcTimestamps.toInstant(task.getCreatedAt()),
            UtcTimestamps.updatedAt(task.getCreatedAt(), task.getUpdatedAt()),
            UtcTimestamps.toInstant(task.getStartedAt()),
            UtcTimestamps.toInstant(task.getFinishedAt()),
            courseName
        );
    }

    private TaskDetailResponse toDetailResponse(AnalysisTask task, String courseName) {
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
            UtcTimestamps.toInstant(task.getCreatedAt()),
            UtcTimestamps.updatedAt(task.getCreatedAt(), task.getUpdatedAt()),
            UtcTimestamps.toInstant(task.getStartedAt()),
            UtcTimestamps.toInstant(task.getFinishedAt()),
            LearningAvailability.learnable(task.getStatus(), task.getLearningReadyAt()),
            courseName
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
