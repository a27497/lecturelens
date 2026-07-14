package com.example.courselingo.task;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import com.example.courselingo.task.controller.TaskQueryController;
import com.example.courselingo.task.dto.TaskDetailResponse;
import com.example.courselingo.task.dto.TaskListQuery;
import com.example.courselingo.task.dto.TaskListResponse;
import com.example.courselingo.task.dto.TaskSummaryResponse;
import com.example.courselingo.task.service.TaskQueryService;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(TaskQueryController.class)
@Import({GlobalExceptionHandler.class, TaskQueryControllerTest.TestConfig.class})
class TaskQueryControllerTest {

    private final MockMvc mockMvc;

    @Autowired
    private TaskQueryService taskQueryService;

    @Autowired
    TaskQueryControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @BeforeEach
    void resetMocks() {
        Mockito.reset(taskQueryService);
    }

    @TestConfiguration
    static class TestConfig {

        @Bean
        TaskQueryService taskQueryService() {
            return Mockito.mock(TaskQueryService.class);
        }
    }

    @Test
    void listReturnsPageEnvelopeAndDoesNotExposeSensitiveFields() throws Exception {
        when(taskQueryService.list(new TaskListQuery("RUNNING", 1, 20), "Bearer access-token"))
            .thenReturn(new TaskListResponse(
                List.of(summary("task_1", "RUNNING")),
                1,
                20,
                1L
            ));

        mockMvc.perform(get("/api/tasks")
                .param("status", "RUNNING")
                .param("page", "1")
                .param("pageSize", "20")
                .param("userId", "999")
                .param("ownerId", "999")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.page").value(1))
            .andExpect(jsonPath("$.data.pageSize").value(20))
            .andExpect(jsonPath("$.data.total").value(1))
            .andExpect(jsonPath("$.data.items[0].taskId").value("task_1"))
            .andExpect(jsonPath("$.data.items[0].uploadId").value("up_1"))
            .andExpect(jsonPath("$.data.items[0].targetLanguage").value("zh-CN"))
            .andExpect(jsonPath("$.data.items[0].status").value("RUNNING"))
            .andExpect(jsonPath("$.data.items[0].progressPercent").value(35))
            .andExpect(jsonPath("$.data.items[0].currentStage").value("EXTRACT_AUDIO"))
            .andExpect(jsonPath("$.data.items[0].retryCount").value(0))
            .andExpect(jsonPath("$.data.items[0].maxRetryCount").value(3))
            .andExpect(content().string(not(containsString("userId"))))
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("localPath"))))
            .andExpect(content().string(not(containsString("refreshTokenHash"))))
            .andExpect(content().string(not(containsString("passwordHash"))))
            .andExpect(content().string(not(containsString("access-token"))));

        verify(taskQueryService).list(new TaskListQuery("RUNNING", 1, 20), "Bearer access-token");
    }

    @Test
    void detailReturnsAllowedTaskFieldsOnly() throws Exception {
        when(taskQueryService.detail("task_1", "Bearer access-token"))
            .thenReturn(detail("task_1", "SUCCEEDED"));

        mockMvc.perform(get("/api/tasks/{taskId}", "task_1")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.taskId").value("task_1"))
            .andExpect(jsonPath("$.data.uploadId").value("up_1"))
            .andExpect(jsonPath("$.data.targetLanguage").value("zh-CN"))
            .andExpect(jsonPath("$.data.status").value("SUCCEEDED"))
            .andExpect(jsonPath("$.data.progressPercent").value(35))
            .andExpect(jsonPath("$.data.currentStage").value("EXTRACT_AUDIO"))
            .andExpect(jsonPath("$.data.errorCode").doesNotExist())
            .andExpect(jsonPath("$.data.errorMessage").doesNotExist())
            .andExpect(jsonPath("$.data.retryCount").value(0))
            .andExpect(jsonPath("$.data.maxRetryCount").value(3))
            .andExpect(jsonPath("$.data.createdAt").exists())
            .andExpect(jsonPath("$.data.updatedAt").exists())
            .andExpect(jsonPath("$.data.startedAt").exists())
            .andExpect(jsonPath("$.data.finishedAt").doesNotExist())
            .andExpect(content().string(not(containsString("userId"))))
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("localPath"))))
            .andExpect(content().string(not(containsString("secret"))))
            .andExpect(content().string(not(containsString("passwordHash"))));

        verify(taskQueryService).detail("task_1", "Bearer access-token");
    }

    @Test
    void listRejectsMissingAuthorizationAndRefreshToken() throws Exception {
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(taskQueryService).list(new TaskListQuery(null, null, null), null);
        doThrow(new BusinessException(ErrorCode.AUTH_TOKEN_INVALID))
            .when(taskQueryService).list(new TaskListQuery(null, null, null), "Bearer refresh-token");

        mockMvc.perform(get("/api/tasks"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string(containsString(ErrorCode.COMMON_UNAUTHORIZED.code())));

        mockMvc.perform(get("/api/tasks")
                .header("Authorization", "Bearer refresh-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string(containsString(ErrorCode.AUTH_TOKEN_INVALID.code())));
    }

    @Test
    void detailRejectsMissingAndNonOwnerTasks() throws Exception {
        doThrow(new BusinessException(ErrorCode.TASK_NOT_FOUND))
            .when(taskQueryService).detail("task_missing", "Bearer access-token");

        mockMvc.perform(get("/api/tasks/{taskId}", "task_missing")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isNotFound())
            .andExpect(content().string(containsString(ErrorCode.TASK_NOT_FOUND.code())));
    }

    @Test
    void invalidQueryParametersFail() throws Exception {
        doThrow(new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED))
            .when(taskQueryService).list(new TaskListQuery("NOT_A_STATUS", 0, 101), "Bearer access-token");

        mockMvc.perform(get("/api/tasks")
                .param("status", "NOT_A_STATUS")
                .param("page", "0")
                .param("pageSize", "101")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(containsString(ErrorCode.COMMON_VALIDATION_FAILED.code())));
    }

    private static TaskSummaryResponse summary(String taskId, String status) {
        return new TaskSummaryResponse(
            taskId,
            "up_1",
            "zh-CN",
            status,
            35,
            "EXTRACT_AUDIO",
            null,
            null,
            0,
            3,
            LocalDateTime.of(2026, 6, 27, 10, 0),
            LocalDateTime.of(2026, 6, 27, 10, 1),
            LocalDateTime.of(2026, 6, 27, 10, 1),
            null
        );
    }

    private static TaskDetailResponse detail(String taskId, String status) {
        return new TaskDetailResponse(
            taskId,
            "up_1",
            "zh-CN",
            status,
            35,
            "EXTRACT_AUDIO",
            null,
            null,
            0,
            3,
            LocalDateTime.of(2026, 6, 27, 10, 0),
            LocalDateTime.of(2026, 6, 27, 10, 1),
            LocalDateTime.of(2026, 6, 27, 10, 1),
            null
        );
    }
}
