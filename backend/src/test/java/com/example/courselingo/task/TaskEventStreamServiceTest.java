package com.example.courselingo.task;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.events.TaskEventStreamProperties;
import com.example.courselingo.task.events.TaskEventStreamServiceImpl;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.progress.TaskProgressSnapshot;
import com.example.courselingo.task.progress.TaskProgressSnapshotService;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@ExtendWith(MockitoExtension.class)
class TaskEventStreamServiceTest {

    private static final Instant UPDATED_AT = Instant.parse("2026-06-27T10:00:00Z");

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private TaskProgressSnapshotService progressSnapshotService;

    private ScheduledExecutorService executor;

    @BeforeEach
    void setUp() {
        executor = Executors.newScheduledThreadPool(1);
    }

    @AfterEach
    void tearDown() {
        executor.shutdownNow();
    }

    @Test
    void terminalSnapshotReleasesTheConnectionWithoutPolling() {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_done", 42L))
            .thenReturn(mysqlTask("task_done", 42L, "SUCCEEDED", 100, "DONE"));
        when(progressSnapshotService.find("task_done"))
            .thenReturn(Optional.of(snapshot("task_done", "SUCCEEDED", 100, "DONE")));

        TaskEventStreamServiceImpl service = new TaskEventStreamServiceImpl(
            currentUserService,
            analysisTaskMapper,
            progressSnapshotService,
            new TaskEventStreamProperties(1, 1, 20, 1),
            executor
        );

        service.open("Bearer access-token", "task_done");

        assertThat(service.activeConnectionCount()).isZero();
    }

    @Test
    void changedSnapshotKeepsStreamOpenForNonTerminalProgress() throws Exception {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_running", 42L))
            .thenReturn(mysqlTask("task_running", 42L, "RUNNING", 20, "ASR"));
        when(progressSnapshotService.find("task_running"))
            .thenReturn(Optional.of(snapshot("task_running", "RUNNING", 20, "ASR")))
            .thenReturn(Optional.of(snapshot("task_running", "RUNNING", 35, "TRANSLATE")));

        TaskEventStreamServiceImpl service = new TaskEventStreamServiceImpl(
            currentUserService,
            analysisTaskMapper,
            progressSnapshotService,
            new TaskEventStreamProperties(5, 1, 20, 1),
            executor
        );

        SseEmitter emitter = service.open("Bearer access-token", "task_running");

        Thread.sleep(100);

        assertThat(service.activeConnectionCount()).isEqualTo(1);
        emitter.complete();
    }

    private static TaskProgressSnapshot snapshot(
        String taskId,
        String status,
        int progressPercent,
        String currentStage
    ) {
        return new TaskProgressSnapshot(taskId, status, progressPercent, currentStage, null, null, UPDATED_AT);
    }

    private static AnalysisTask mysqlTask(
        String taskId,
        Long userId,
        String status,
        int progressPercent,
        String currentStage
    ) {
        AnalysisTask task = new AnalysisTask();
        task.setId(taskId);
        task.setUserId(userId);
        task.setStatus(status);
        task.setProgressPercent(progressPercent);
        task.setCurrentStage(currentStage);
        task.setUpdatedAt(LocalDateTime.ofInstant(UPDATED_AT, ZoneOffset.UTC));
        return task;
    }
}
