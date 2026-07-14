package com.example.courselingo.task;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.dto.TaskDetailResponse;
import com.example.courselingo.task.dto.TaskListQuery;
import com.example.courselingo.task.dto.TaskListResponse;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.task.service.TaskQueryServiceImpl;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class TaskQueryServiceTest {

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    private TaskQueryServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new TaskQueryServiceImpl(currentUserService, analysisTaskMapper);
        lenient().when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
    }

    @Test
    void ownerCanListOwnTasksWithDefaultPagingAndCreatedAtDescOrder() {
        AnalysisTask newest = task("task_new", 42L, AnalysisTaskStatus.RUNNING);
        newest.setCreatedAt(LocalDateTime.of(2026, 6, 27, 10, 2));
        AnalysisTask older = task("task_old", 42L, AnalysisTaskStatus.CREATED);
        older.setCreatedAt(LocalDateTime.of(2026, 6, 27, 10, 1));
        when(analysisTaskMapper.selectPageByUserId(42L, null, 0L, 20))
            .thenReturn(List.of(newest, older));
        when(analysisTaskMapper.countByUserId(42L, null)).thenReturn(2L);

        TaskListResponse response = service.list(new TaskListQuery(null, null, null), "Bearer access-token");

        assertThat(response.page()).isEqualTo(1);
        assertThat(response.pageSize()).isEqualTo(20);
        assertThat(response.total()).isEqualTo(2L);
        assertThat(response.items()).extracting("taskId").containsExactly("task_new", "task_old");
        assertThat(response.items()).extracting("uploadId").containsExactly("up_1", "up_1");
        assertThat(response.items()).extracting("targetLanguage").containsExactly("zh-CN", "zh-CN");
        assertThat(response.items()).extracting("status").containsExactly("RUNNING", "CREATED");
        assertThat(response.items()).extracting("retryCount").containsExactly(0, 0);
        assertThat(response.items()).extracting("maxRetryCount").containsExactly(3, 3);
        verify(analysisTaskMapper).selectPageByUserId(42L, null, 0L, 20);
        verify(analysisTaskMapper).countByUserId(42L, null);
    }

    @Test
    void listUsesCurrentUserOnlyAndIgnoresCallerSuppliedOwnerFields() {
        when(analysisTaskMapper.selectPageByUserId(42L, "RUNNING", 10L, 10))
            .thenReturn(List.of(task("task_owned", 42L, AnalysisTaskStatus.RUNNING)));
        when(analysisTaskMapper.countByUserId(42L, "RUNNING")).thenReturn(1L);

        TaskListResponse response = service.list(new TaskListQuery("RUNNING", 2, 10), "Bearer access-token");

        assertThat(response.items()).extracting("taskId").containsExactly("task_owned");
        assertThat(response.page()).isEqualTo(2);
        assertThat(response.pageSize()).isEqualTo(10);
        assertThat(response.total()).isEqualTo(1L);
        verify(analysisTaskMapper).selectPageByUserId(42L, "RUNNING", 10L, 10);
    }

    @Test
    void ownerCanGetOwnTaskDetail() {
        when(analysisTaskMapper.selectByIdAndUserId("task_detail", 42L))
            .thenReturn(task("task_detail", 42L, AnalysisTaskStatus.SUCCEEDED));

        TaskDetailResponse response = service.detail("task_detail", "Bearer access-token");

        assertThat(response.taskId()).isEqualTo("task_detail");
        assertThat(response.uploadId()).isEqualTo("up_1");
        assertThat(response.targetLanguage()).isEqualTo("zh-CN");
        assertThat(response.status()).isEqualTo("SUCCEEDED");
        assertThat(response.progressPercent()).isEqualTo(35);
        assertThat(response.currentStage()).isEqualTo("EXTRACT_AUDIO");
        assertThat(response.retryCount()).isEqualTo(0);
        assertThat(response.maxRetryCount()).isEqualTo(3);
        assertThat(response.createdAt()).isNotNull();
        assertThat(response.updatedAt()).isNotNull();
        assertThat(response.startedAt()).isNotNull();
        assertThat(response.finishedAt()).isNull();
        verify(analysisTaskMapper).selectByIdAndUserId("task_detail", 42L);
    }

    @Test
    void detailMissingOrNonOwnerFailsWithoutLeakingOwnerInformation() {
        when(analysisTaskMapper.selectByIdAndUserId("task_missing", 42L)).thenReturn(null);

        assertThatThrownBy(() -> service.detail("task_missing", "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                BusinessException exception = (BusinessException) error;
                assertThat(exception.errorCode()).isEqualTo(ErrorCode.TASK_NOT_FOUND);
                assertThat(exception.getMessage()).doesNotContain("42");
                assertThat(exception.getMessage()).doesNotContain("userId");
            });
    }

    @Test
    void refreshTokenFailsBeforeLoadingTasks() {
        doThrow(new BusinessException(ErrorCode.AUTH_TOKEN_INVALID))
            .when(currentUserService).currentUser("Bearer refresh-token");

        assertThatThrownBy(() -> service.list(new TaskListQuery(null, null, null), "Bearer refresh-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_TOKEN_INVALID);

        verify(analysisTaskMapper, never()).selectPageByUserId(any(), any(), anyLong(), anyInt());
        verify(analysisTaskMapper, never()).countByUserId(any(), any());
    }

    @Test
    void listRejectsInvalidStatusAndInvalidPaging() {
        assertThatThrownBy(() -> service.list(new TaskListQuery("NOT_A_STATUS", 1, 20), "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
        assertThatThrownBy(() -> service.list(new TaskListQuery(null, 0, 20), "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
        assertThatThrownBy(() -> service.list(new TaskListQuery(null, 1, 0), "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
        assertThatThrownBy(() -> service.list(new TaskListQuery(null, 1, 101), "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
    }

    @Test
    void responseSanitizesAndLimitsErrorMessage() {
        AnalysisTask task = task("task_failed", 42L, AnalysisTaskStatus.FAILED);
        task.setErrorCode("PIPELINE_FAILED");
        task.setErrorMessage(
            "failed at C:/Users/demo/work/video.mp4 with accessToken=secret-token and passwordHash=hash-value "
                + "x".repeat(700)
        );
        when(analysisTaskMapper.selectByIdAndUserId("task_failed", 42L)).thenReturn(task);

        TaskDetailResponse response = service.detail("task_failed", "Bearer access-token");

        assertThat(response.errorMessage()).hasSizeLessThanOrEqualTo(512);
        assertThat(response.errorMessage()).doesNotContain("secret-token");
        assertThat(response.errorMessage()).doesNotContain("passwordHash");
        assertThat(response.errorMessage()).doesNotContain("C:/Users");
    }

    private static AnalysisTask task(String taskId, Long userId, AnalysisTaskStatus status) {
        AnalysisTask task = new AnalysisTask();
        task.setId(taskId);
        task.setUserId(userId);
        task.setUploadId("up_1");
        task.setTargetLanguage("zh-CN");
        task.setStatus(status.name());
        task.setProgressPercent(35);
        task.setCurrentStage("EXTRACT_AUDIO");
        task.setErrorCode(null);
        task.setErrorMessage(null);
        task.setRetryCount(0);
        task.setMaxRetryCount(3);
        task.setCreatedAt(LocalDateTime.of(2026, 6, 27, 10, 0));
        task.setUpdatedAt(LocalDateTime.of(2026, 6, 27, 10, 1));
        task.setStartedAt(LocalDateTime.of(2026, 6, 27, 10, 1));
        task.setFinishedAt(null);
        return task;
    }
}
