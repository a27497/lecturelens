package com.example.courselingo.task.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anySet;
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
import com.example.courselingo.task.dto.TaskBatchDeleteRequest;
import com.example.courselingo.task.dto.TaskBatchDeleteResponse;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.annotation.Transactional;

@ExtendWith(MockitoExtension.class)
class TaskBatchDeleteServiceTest {

    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-07-13T06:00:00Z"), ZoneOffset.UTC);

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    private TaskBatchDeleteServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new TaskBatchDeleteServiceImpl(currentUserService, analysisTaskMapper, CLOCK);
        lenient().when(currentUserService.currentUser(null))
            .thenReturn(new CurrentUserResponse(42L, "redacted", "ACTIVE"));
    }

    @Test
    void normalizesDuplicatesAndDeletesOnce() {
        when(analysisTaskMapper.selectByIdsAndUserIdIncludingDeleted(List.of("task_1"), 42L))
            .thenReturn(List.of(task("task_1", "SUCCEEDED")));
        when(analysisTaskMapper.softDeleteByIdsAndUserId(anyList(), eq(42L), anySet(), any()))
            .thenReturn(1);

        TaskBatchDeleteResponse response = service.delete(
            new TaskBatchDeleteRequest(List.of("task_1", " task_1 ")),
            null
        );

        assertThat(response.requestedCount()).isEqualTo(1);
        assertThat(response.deletedCount()).isEqualTo(1);
        verify(analysisTaskMapper).softDeleteByIdsAndUserId(
            List.of("task_1"),
            42L,
            java.util.Set.of("SUCCEEDED", "FAILED", "CANCELED"),
            LocalDateTime.ofInstant(CLOCK.instant(), CLOCK.getZone())
        );
    }

    @Test
    void mixedTerminalStatusesDeleteInOneBatch() {
        List<String> ids = List.of("task_1", "task_2", "task_3");
        when(analysisTaskMapper.selectByIdsAndUserIdIncludingDeleted(ids, 42L)).thenReturn(List.of(
            task("task_1", "SUCCEEDED"), task("task_2", "FAILED"), task("task_3", "CANCELED")
        ));
        when(analysisTaskMapper.softDeleteByIdsAndUserId(anyList(), eq(42L), anySet(), any()))
            .thenReturn(3);

        TaskBatchDeleteResponse response = service.delete(new TaskBatchDeleteRequest(ids), null);

        assertThat(response).isEqualTo(new TaskBatchDeleteResponse(3, 3));
        verify(analysisTaskMapper).softDeleteByIdsAndUserId(anyList(), eq(42L), anySet(), any());
    }

    @Test
    void anyNonTerminalStatusRejectsWholeBatch() {
        for (String status : List.of("RUNNING", "QUEUED", "CREATED", "RETRYING", "UNKNOWN")) {
            List<String> ids = List.of("task_done", "task_active_" + status);
            when(analysisTaskMapper.selectByIdsAndUserIdIncludingDeleted(ids, 42L)).thenReturn(List.of(
                task("task_done", "SUCCEEDED"), task("task_active_" + status, status)
            ));

            assertThatThrownBy(() -> service.delete(new TaskBatchDeleteRequest(ids), null))
                .isInstanceOf(BusinessException.class)
                .extracting("errorCode")
                .isEqualTo(ErrorCode.TASK_DELETE_NOT_ALLOWED);
        }

        verify(analysisTaskMapper, never()).softDeleteByIdsAndUserId(anyList(), any(), anySet(), any());
    }

    @Test
    void missingOrOtherUsersTaskReturnsNotFoundWithoutUpdating() {
        List<String> ids = List.of("task_owned", "task_hidden");
        when(analysisTaskMapper.selectByIdsAndUserIdIncludingDeleted(ids, 42L))
            .thenReturn(List.of(task("task_owned", "SUCCEEDED")));

        assertThatThrownBy(() -> service.delete(new TaskBatchDeleteRequest(ids), null))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(analysisTaskMapper, never()).softDeleteByIdsAndUserId(anyList(), any(), anySet(), any());
    }

    @Test
    void repeatedDeleteIsIdempotent() {
        List<String> ids = List.of("task_1", "task_2", "task_3");
        List<AnalysisTask> deletedTasks = List.of(
            task("task_1", "SUCCEEDED"),
            task("task_2", "FAILED"),
            task("task_3", "CANCELED")
        );
        deletedTasks.forEach(task -> task.setDeletedAt(LocalDateTime.of(2026, 7, 13, 5, 0)));
        when(analysisTaskMapper.selectByIdsAndUserIdIncludingDeleted(ids, 42L)).thenReturn(deletedTasks);

        TaskBatchDeleteResponse response = service.delete(
            new TaskBatchDeleteRequest(ids),
            null
        );

        assertThat(response).isEqualTo(new TaskBatchDeleteResponse(3, 0));
        verify(analysisTaskMapper, never()).softDeleteByIdsAndUserId(anyList(), any(), anySet(), any());
    }

    @Test
    void partiallyDeletedBatchOnlyUpdatesActiveTerminalTasks() {
        List<String> ids = List.of("task_1", "task_2", "task_3");
        AnalysisTask alreadyDeleted = task("task_1", "SUCCEEDED");
        alreadyDeleted.setDeletedAt(LocalDateTime.of(2026, 7, 13, 5, 0));
        when(analysisTaskMapper.selectByIdsAndUserIdIncludingDeleted(ids, 42L)).thenReturn(List.of(
            alreadyDeleted,
            task("task_2", "FAILED"),
            task("task_3", "CANCELED")
        ));
        when(analysisTaskMapper.softDeleteByIdsAndUserId(anyList(), eq(42L), anySet(), any()))
            .thenReturn(2);

        TaskBatchDeleteResponse response = service.delete(new TaskBatchDeleteRequest(ids), null);

        assertThat(response).isEqualTo(new TaskBatchDeleteResponse(3, 2));
        verify(analysisTaskMapper).softDeleteByIdsAndUserId(
            eq(List.of("task_2", "task_3")),
            eq(42L),
            anySet(),
            any()
        );
    }

    @Test
    void deletedHistoricalNonTerminalStatusDoesNotBlockIdempotentDelete() {
        AnalysisTask deletedRunning = task("task_1", "RUNNING");
        deletedRunning.setDeletedAt(LocalDateTime.of(2026, 7, 13, 5, 0));
        when(analysisTaskMapper.selectByIdsAndUserIdIncludingDeleted(List.of("task_1"), 42L))
            .thenReturn(List.of(deletedRunning));

        TaskBatchDeleteResponse response = service.delete(
            new TaskBatchDeleteRequest(List.of("task_1")),
            null
        );

        assertThat(response).isEqualTo(new TaskBatchDeleteResponse(1, 0));
        verify(analysisTaskMapper, never()).softDeleteByIdsAndUserId(anyList(), any(), anySet(), any());
    }

    @Test
    void concurrentStatusChangeRollsBackInsteadOfReturningPartialSuccess() {
        List<String> ids = List.of("task_1", "task_2");
        when(analysisTaskMapper.selectByIdsAndUserIdIncludingDeleted(ids, 42L))
            .thenReturn(List.of(task("task_1", "SUCCEEDED"), task("task_2", "FAILED")));
        when(analysisTaskMapper.softDeleteByIdsAndUserId(anyList(), eq(42L), anySet(), any()))
            .thenReturn(1);

        assertThatThrownBy(() -> service.delete(new TaskBatchDeleteRequest(ids), null))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_DELETE_NOT_ALLOWED);
    }

    @Test
    void authenticationFailureStopsBeforeDatabaseAccess() {
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(currentUserService).currentUser(null);

        assertThatThrownBy(() -> service.delete(new TaskBatchDeleteRequest(List.of("task_1")), null))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_UNAUTHORIZED);

        verify(analysisTaskMapper, never()).selectByIdsAndUserIdIncludingDeleted(anyList(), any());
    }

    @Test
    void deleteMethodDefinesTransactionBoundary() throws NoSuchMethodException {
        assertThat(TaskBatchDeleteServiceImpl.class
            .getMethod("delete", TaskBatchDeleteRequest.class, String.class)
            .isAnnotationPresent(Transactional.class)).isTrue();
    }

    @Test
    void serviceHasNoStorageMqOrAssociatedDataDeletionDependency() {
        assertThat(Arrays.stream(TaskBatchDeleteServiceImpl.class.getDeclaredFields())
            .map(field -> field.getType().getName())
            .filter(name -> !name.equals("int") && !name.equals("java.util.Set"))
            .toList())
            .containsExactlyInAnyOrder(
                CurrentUserService.class.getName(),
                AnalysisTaskMapper.class.getName(),
                Clock.class.getName()
            );
    }

    private static AnalysisTask task(String id, String status) {
        AnalysisTask task = new AnalysisTask();
        task.setId(id);
        task.setUserId(42L);
        task.setStatus(status);
        return task;
    }
}
