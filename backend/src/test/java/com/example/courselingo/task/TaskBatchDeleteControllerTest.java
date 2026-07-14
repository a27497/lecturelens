package com.example.courselingo.task;

import static org.hamcrest.Matchers.containsString;
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
import com.example.courselingo.task.controller.TaskBatchDeleteController;
import com.example.courselingo.task.dto.TaskBatchDeleteRequest;
import com.example.courselingo.task.dto.TaskBatchDeleteResponse;
import com.example.courselingo.task.service.TaskBatchDeleteService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(TaskBatchDeleteController.class)
@Import({GlobalExceptionHandler.class, TaskBatchDeleteControllerTest.TestConfig.class})
class TaskBatchDeleteControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private TaskBatchDeleteService taskBatchDeleteService;

    @BeforeEach
    void resetMocks() {
        Mockito.reset(taskBatchDeleteService);
    }

    @TestConfiguration
    static class TestConfig {

        @Bean
        TaskBatchDeleteService taskBatchDeleteService() {
            return Mockito.mock(TaskBatchDeleteService.class);
        }
    }

    @Test
    void batchDeleteReturnsCounts() throws Exception {
        TaskBatchDeleteRequest request = new TaskBatchDeleteRequest(List.of("task_1", "task_2"));
        when(taskBatchDeleteService.delete(request, null))
            .thenReturn(new TaskBatchDeleteResponse(2, 2));

        mockMvc.perform(post("/api/tasks/batch-delete")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsBytes(request)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.requestedCount").value(2))
            .andExpect(jsonPath("$.data.deletedCount").value(2));

        verify(taskBatchDeleteService).delete(request, null);
    }

    @Test
    void missingAuthorizationReturnsUnauthorized() throws Exception {
        TaskBatchDeleteRequest request = new TaskBatchDeleteRequest(List.of("task_1"));
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(taskBatchDeleteService).delete(request, null);

        mockMvc.perform(post("/api/tasks/batch-delete")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsBytes(request)))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string(containsString(ErrorCode.COMMON_UNAUTHORIZED.code())));
    }

    @Test
    void activeTaskConflictAndHiddenTaskUseFixedHttpStatuses() throws Exception {
        TaskBatchDeleteRequest conflictRequest = new TaskBatchDeleteRequest(List.of("task_1"));
        TaskBatchDeleteRequest missingRequest = new TaskBatchDeleteRequest(List.of("task_2"));
        doThrow(new BusinessException(ErrorCode.TASK_DELETE_NOT_ALLOWED))
            .when(taskBatchDeleteService).delete(conflictRequest, null);
        doThrow(new BusinessException(ErrorCode.TASK_NOT_FOUND))
            .when(taskBatchDeleteService).delete(missingRequest, null);

        mockMvc.perform(post("/api/tasks/batch-delete")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsBytes(conflictRequest)))
            .andExpect(status().isConflict())
            .andExpect(content().string(containsString(ErrorCode.TASK_DELETE_NOT_ALLOWED.code())));

        mockMvc.perform(post("/api/tasks/batch-delete")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsBytes(missingRequest)))
            .andExpect(status().isNotFound())
            .andExpect(content().string(containsString(ErrorCode.TASK_NOT_FOUND.code())));
    }

    @Test
    void nullEmptyBlankAndOversizedTaskIdsReturnValidationFailed() throws Exception {
        List<String> oversized = IntStream.range(0, 101).mapToObj(index -> "task_" + index).toList();

        assertValidationFailed("{\"taskIds\":null}");
        assertValidationFailed("{\"taskIds\":[]}");
        assertValidationFailed(objectMapper.writeValueAsString(new TaskBatchDeleteRequest(List.of(" "))));
        assertValidationFailed(objectMapper.writeValueAsString(new TaskBatchDeleteRequest(oversized)));
        assertValidationFailed(objectMapper.writeValueAsString(new TaskBatchDeleteRequest(List.of("x".repeat(65)))));
    }

    private void assertValidationFailed(String body) throws Exception {
        mockMvc.perform(post("/api/tasks/batch-delete")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(containsString(ErrorCode.COMMON_VALIDATION_FAILED.code())));
    }
}
