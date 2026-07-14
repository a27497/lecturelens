package com.example.courselingo.task;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
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
import com.example.courselingo.task.controller.TaskController;
import com.example.courselingo.task.dto.CreateAnalysisTaskRequest;
import com.example.courselingo.task.dto.CreateAnalysisTaskResponse;
import com.example.courselingo.task.service.TaskCreationService;
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

@WebMvcTest(TaskController.class)
@Import({GlobalExceptionHandler.class, TaskCreationControllerTest.TestConfig.class})
class TaskCreationControllerTest {

    private static final String VALID_REQUEST = """
        {
          "uploadId": "up_1",
          "targetLanguage": "zh-CN"
        }
        """;

    private final MockMvc mockMvc;

    @Autowired
    private TaskCreationService taskCreationService;

    @Autowired
    TaskCreationControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @BeforeEach
    void resetMocks() {
        Mockito.reset(taskCreationService);
    }

    @TestConfiguration
    static class TestConfig {

        @Bean
        TaskCreationService taskCreationService() {
            return Mockito.mock(TaskCreationService.class);
        }
    }

    @Test
    void createReturnsQueuedTaskWithoutSensitiveFields() throws Exception {
        when(taskCreationService.create(any(CreateAnalysisTaskRequest.class), eq("Bearer access-token")))
            .thenReturn(new CreateAnalysisTaskResponse("task_1", "up_1", "QUEUED", "zh-CN"));

        mockMvc.perform(post("/api/tasks")
                .header("Authorization", "Bearer access-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_REQUEST))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("0"))
            .andExpect(jsonPath("$.data.taskId").value("task_1"))
            .andExpect(jsonPath("$.data.uploadId").value("up_1"))
            .andExpect(jsonPath("$.data.status").value("QUEUED"))
            .andExpect(jsonPath("$.data.targetLanguage").value("zh-CN"))
            .andExpect(jsonPath("$.data.userId").doesNotExist())
            .andExpect(jsonPath("$.data.objectKey").doesNotExist())
            .andExpect(content().string(not(containsString("cl:rate"))))
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("localPath"))))
            .andExpect(content().string(not(containsString("userId"))))
            .andExpect(content().string(not(containsString("access-token"))))
            .andExpect(content().string(not(containsString("refreshToken"))))
            .andExpect(content().string(not(containsString("secret"))));
    }

    @Test
    void createRejectsMissingAuthorization() throws Exception {
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(taskCreationService).create(any(CreateAnalysisTaskRequest.class), isNull());

        mockMvc.perform(post("/api/tasks")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_REQUEST))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_UNAUTHORIZED.code()));
    }

    @Test
    void createRejectsRefreshToken() throws Exception {
        doThrow(new BusinessException(ErrorCode.AUTH_TOKEN_INVALID))
            .when(taskCreationService).create(any(CreateAnalysisTaskRequest.class), eq("Bearer refresh-token"));

        mockMvc.perform(post("/api/tasks")
                .header("Authorization", "Bearer refresh-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_REQUEST))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value(ErrorCode.AUTH_TOKEN_INVALID.code()));
    }

    @Test
    void forgedUserIdAndOwnerIdInBodyDoNotChangeOwnerDecision() throws Exception {
        when(taskCreationService.create(any(CreateAnalysisTaskRequest.class), eq("Bearer access-token")))
            .thenReturn(new CreateAnalysisTaskResponse("task_1", "up_1", "QUEUED", "zh-CN"));

        mockMvc.perform(post("/api/tasks")
                .header("Authorization", "Bearer access-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "uploadId": "up_1",
                      "targetLanguage": "zh-CN",
                      "userId": 999,
                      "ownerId": 999
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.taskId").value("task_1"))
            .andExpect(jsonPath("$.data.userId").doesNotExist())
            .andExpect(jsonPath("$.data.ownerId").doesNotExist());

        verify(taskCreationService).create(any(CreateAnalysisTaskRequest.class), eq("Bearer access-token"));
    }

    @Test
    void createRejectsBlankUploadId() throws Exception {
        mockMvc.perform(post("/api/tasks")
                .header("Authorization", "Bearer access-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "uploadId": "",
                      "targetLanguage": "zh-CN"
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_VALIDATION_FAILED.code()))
            .andExpect(jsonPath("$.data.uploadId").exists());
    }

    @Test
    void createRejectsBlankTargetLanguage() throws Exception {
        mockMvc.perform(post("/api/tasks")
                .header("Authorization", "Bearer access-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "uploadId": "up_1",
                      "targetLanguage": ""
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_VALIDATION_FAILED.code()))
            .andExpect(jsonPath("$.data.targetLanguage").exists());
    }

    @Test
    void createRejectsTooLongTargetLanguage() throws Exception {
        mockMvc.perform(post("/api/tasks")
                .header("Authorization", "Bearer access-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "uploadId": "up_1",
                      "targetLanguage": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_VALIDATION_FAILED.code()))
            .andExpect(jsonPath("$.data.targetLanguage").exists());
    }
}
