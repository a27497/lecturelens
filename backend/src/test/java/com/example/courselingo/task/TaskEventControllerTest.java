package com.example.courselingo.task;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import com.example.courselingo.task.controller.TaskEventController;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.events.TaskEventStreamConfiguration;
import com.example.courselingo.task.events.TaskEventStreamProperties;
import com.example.courselingo.task.events.TaskEventStreamService;
import com.example.courselingo.task.events.TaskEventStreamServiceImpl;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.progress.TaskProgressSnapshot;
import com.example.courselingo.task.progress.TaskProgressSnapshotService;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.concurrent.ScheduledExecutorService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@WebMvcTest(TaskEventController.class)
@Import({GlobalExceptionHandler.class, TaskEventControllerTest.TestConfig.class})
class TaskEventControllerTest {

    private static final Instant UPDATED_AT = Instant.parse("2026-06-27T10:00:00Z");

    private final MockMvc mockMvc;

    @Autowired
    private CurrentUserService currentUserService;

    @Autowired
    private AnalysisTaskMapper analysisTaskMapper;

    @Autowired
    private TaskProgressSnapshotService progressSnapshotService;

    @Autowired
    TaskEventControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @BeforeEach
    void resetMocks() {
        Mockito.reset(currentUserService, analysisTaskMapper, progressSnapshotService);
    }

    @TestConfiguration
    static class TestConfig {

        @Bean
        CurrentUserService currentUserService() {
            return Mockito.mock(CurrentUserService.class);
        }

        @Bean
        AnalysisTaskMapper analysisTaskMapper() {
            return Mockito.mock(AnalysisTaskMapper.class);
        }

        @Bean
        TaskProgressSnapshotService taskProgressSnapshotService() {
            return Mockito.mock(TaskProgressSnapshotService.class);
        }

        @Bean
        TaskEventStreamProperties taskEventStreamProperties() {
            return new TaskEventStreamProperties(5, 1, 10, 1);
        }

        @Bean(destroyMethod = "shutdownNow")
        ScheduledExecutorService taskEventStreamExecutor(TaskEventStreamProperties properties) {
            return new TaskEventStreamConfiguration().taskEventStreamExecutor(properties);
        }

        @Bean
        TaskEventStreamService taskEventStreamService(
            CurrentUserService currentUserService,
            AnalysisTaskMapper analysisTaskMapper,
            TaskProgressSnapshotService progressSnapshotService,
            TaskEventStreamProperties properties,
            ScheduledExecutorService taskEventStreamExecutor
        ) {
            return new TaskEventStreamServiceImpl(
                currentUserService,
                analysisTaskMapper,
                progressSnapshotService,
                properties,
                taskEventStreamExecutor
            );
        }
    }

    @Test
    void ownerReceivesRedisSnapshotFirstAndTerminalCompletedEventWithoutSensitiveFields() throws Exception {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_abc123", 42L))
            .thenReturn(mysqlTask("task_abc123", 42L, "RUNNING", 20, "ASR"));
        when(progressSnapshotService.find("task_abc123"))
            .thenReturn(Optional.of(new TaskProgressSnapshot(
                "task_abc123",
                "SUCCEEDED",
                100,
                "DONE",
                null,
                null,
                UPDATED_AT
            )));

        MvcResult result = mockMvc.perform(get("/api/tasks/{taskId}/events", "task_abc123")
                .header("Authorization", "Bearer access-token")
                .header("Accept", "text/event-stream"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch(result))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith("text/event-stream"))
            .andExpect(content().string(containsString("event:snapshot")))
            .andExpect(content().string(containsString("event:completed")))
            .andExpect(content().string(containsString("\"taskId\":\"task_abc123\"")))
            .andExpect(content().string(containsString("\"status\":\"SUCCEEDED\"")))
            .andExpect(content().string(containsString("\"progressPercent\":100")))
            .andExpect(content().string(containsString("\"currentStage\":\"DONE\"")))
            .andExpect(content().string(containsString("\"updatedAt\":\"2026-06-27T10:00:00Z\"")))
            .andExpect(content().string(not(containsString("cl:t:progress"))))
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("localPath"))))
            .andExpect(content().string(not(containsString("userId"))))
            .andExpect(content().string(not(containsString("access-token"))))
            .andExpect(content().string(not(containsString(" secret "))))
            .andExpect(content().string(not(containsString("api key"))));

        verify(currentUserService).currentUser("Bearer access-token");
        verify(analysisTaskMapper).selectByIdAndUserId("task_abc123", 42L);
        verify(progressSnapshotService).find("task_abc123");
    }

    @Test
    void missingAuthorizationFailsBeforeOpeningStream() throws Exception {
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(currentUserService).currentUser(null);

        mockMvc.perform(get("/api/tasks/{taskId}/events", "task_abc123"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string(containsString(ErrorCode.COMMON_UNAUTHORIZED.code())));
    }

    @Test
    void refreshTokenIsRejectedBeforeOpeningStream() throws Exception {
        doThrow(new BusinessException(ErrorCode.AUTH_TOKEN_INVALID))
            .when(currentUserService).currentUser("Bearer refresh-token");

        mockMvc.perform(get("/api/tasks/{taskId}/events", "task_abc123")
                .header("Authorization", "Bearer refresh-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string(containsString(ErrorCode.AUTH_TOKEN_INVALID.code())));
    }

    @Test
    void missingOrNonOwnerTaskFailsWithoutLeakingOwnerInformation() throws Exception {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(99L, "other@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_abc123", 99L)).thenReturn(null);

        mockMvc.perform(get("/api/tasks/{taskId}/events", "task_abc123")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isNotFound())
            .andExpect(content().string(containsString(ErrorCode.TASK_NOT_FOUND.code())))
            .andExpect(content().string(not(containsString("userId"))));
    }

    @Test
    void mysqlSnapshotIsUsedWhenRedisSnapshotDoesNotExist() throws Exception {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_mysql", 42L))
            .thenReturn(mysqlTask("task_mysql", 42L, "FAILED", 35, "FAILED"));
        when(progressSnapshotService.find("task_mysql")).thenReturn(Optional.empty());

        MvcResult result = mockMvc.perform(get("/api/tasks/{taskId}/events", "task_mysql")
                .header("Authorization", "Bearer access-token"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch(result))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("event:snapshot")))
            .andExpect(content().string(containsString("event:failed")))
            .andExpect(content().string(containsString("\"taskId\":\"task_mysql\"")))
            .andExpect(content().string(containsString("\"status\":\"FAILED\"")))
            .andExpect(content().string(containsString("\"progressPercent\":35")))
            .andExpect(content().string(containsString("\"currentStage\":\"FAILED\"")))
            .andExpect(content().string(containsString("\"errorCode\":\"ASR_FAILED\"")))
            .andExpect(content().string(containsString("\"errorMessage\":\"provider failed\"")));
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
        task.setErrorCode("FAILED".equals(status) ? "ASR_FAILED" : null);
        task.setErrorMessage("FAILED".equals(status) ? "provider failed" : null);
        task.setUpdatedAt(LocalDateTime.ofInstant(UPDATED_AT, ZoneOffset.UTC));
        return task;
    }
}
