package com.example.courselingo.task;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import com.example.courselingo.task.controller.TaskCommandController;
import com.example.courselingo.task.dto.TaskCommandResponse;
import com.example.courselingo.task.dto.TaskRetryResponse;
import com.example.courselingo.task.service.TaskCommandService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(TaskCommandController.class)
@Import({GlobalExceptionHandler.class, TaskCommandControllerTest.TestConfig.class})
class TaskCommandControllerTest {

    private final MockMvc mockMvc;

    @Autowired
    private TaskCommandService taskCommandService;

    @Autowired
    TaskCommandControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @BeforeEach
    void resetMocks() {
        Mockito.reset(taskCommandService);
    }

    @TestConfiguration
    static class TestConfig {

        @Bean
        TaskCommandService taskCommandService() {
            return Mockito.mock(TaskCommandService.class);
        }
    }

    @Test
    void retryReturnsOriginalTaskIdNewTaskIdAndStatus() throws Exception {
        when(taskCommandService.retry("task_retry", "Bearer access-token"))
            .thenReturn(new TaskRetryResponse("task_retry", "task_new", "QUEUED", "已创建新的分析任务"));

        mockMvc.perform(post("/api/tasks/{taskId}/retry", "task_retry")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.originalTaskId").value("task_retry"))
            .andExpect(jsonPath("$.data.newTaskId").value("task_new"))
            .andExpect(jsonPath("$.data.status").value("QUEUED"))
            .andExpect(jsonPath("$.data.message").value("已创建新的分析任务"))
            .andExpect(content().string(not(containsString("userId"))))
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("localPath"))))
            .andExpect(content().string(not(containsString("cl:t:progress"))))
            .andExpect(content().string(not(containsString("access-token"))));

        verify(taskCommandService).retry("task_retry", "Bearer access-token");
    }

    @Test
    void cancelReturnsOnlyTaskIdAndStatus() throws Exception {
        when(taskCommandService.cancel("task_cancel", "Bearer access-token"))
            .thenReturn(new TaskCommandResponse("task_cancel", "CANCELED"));

        mockMvc.perform(post("/api/tasks/{taskId}/cancel", "task_cancel")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.taskId").value("task_cancel"))
            .andExpect(jsonPath("$.data.status").value("CANCELED"))
            .andExpect(content().string(not(containsString("userId"))))
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("localPath"))))
            .andExpect(content().string(not(containsString("access-token"))));

        verify(taskCommandService).cancel("task_cancel", "Bearer access-token");
    }

    @Test
    void retryRejectsRefreshToken() throws Exception {
        doThrow(new BusinessException(ErrorCode.AUTH_TOKEN_INVALID))
            .when(taskCommandService).retry("task_retry", "Bearer refresh-token");

        mockMvc.perform(post("/api/tasks/{taskId}/retry", "task_retry")
                .header("Authorization", "Bearer refresh-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string(containsString(ErrorCode.AUTH_TOKEN_INVALID.code())));
    }

    @Test
    void cancelRejectsMissingAuthorization() throws Exception {
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(taskCommandService).cancel("task_cancel", null);

        mockMvc.perform(post("/api/tasks/{taskId}/cancel", "task_cancel"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string(containsString(ErrorCode.COMMON_UNAUTHORIZED.code())));
    }
}
