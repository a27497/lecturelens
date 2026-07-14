package com.example.courselingo.result;

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
import com.example.courselingo.result.controller.TaskResultController;
import com.example.courselingo.result.dto.ResultAiCallRecord;
import com.example.courselingo.result.dto.ResultArtifactFile;
import com.example.courselingo.result.dto.ResultLearningPackage;
import com.example.courselingo.result.dto.ResultSubtitleSegment;
import com.example.courselingo.result.dto.ResultTranslationSegment;
import com.example.courselingo.result.dto.TaskResultResponse;
import com.example.courselingo.result.service.TaskResultService;
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

@WebMvcTest(TaskResultController.class)
@Import({GlobalExceptionHandler.class, TaskResultControllerTest.TestConfig.class})
class TaskResultControllerTest {

    private final MockMvc mockMvc;

    @Autowired
    private TaskResultService taskResultService;

    @Autowired
    TaskResultControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @BeforeEach
    void resetMocks() {
        Mockito.reset(taskResultService);
    }

    @TestConfiguration
    static class TestConfig {

        @Bean
        TaskResultService taskResultService() {
            return Mockito.mock(TaskResultService.class);
        }
    }

    @Test
    void resultEndpointReturnsSafeAggregatedPayload() throws Exception {
        when(taskResultService.getResult("task_1", "Bearer access-token")).thenReturn(result());

        mockMvc.perform(get("/api/tasks/{taskId}/results", "task_1")
                .header("Authorization", "Bearer access-token")
                .param("userId", "999"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.taskId").value("task_1"))
            .andExpect(jsonPath("$.data.targetLanguage").value("zh-CN"))
            .andExpect(jsonPath("$.data.subtitles[0].sourceText").value("hello"))
            .andExpect(jsonPath("$.data.translations[0].translatedText").value("你好"))
            .andExpect(jsonPath("$.data.learningPackage.title").value("Lesson"))
            .andExpect(jsonPath("$.data.artifacts[0].artifactType").value("JSON"))
            .andExpect(jsonPath("$.data.aiCallRecords[0].status").value("SUCCEEDED"))
            .andExpect(content().string(not(containsString("userId"))))
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("localPath"))))
            .andExpect(content().string(not(containsString("authorization"))))
            .andExpect(content().string(not(containsString("apiKey"))))
            .andExpect(content().string(not(containsString("secret"))));

        verify(taskResultService).getResult("task_1", "Bearer access-token");
    }

    @Test
    void resultEndpointReturnsNotFoundForMissingOrNonOwnerTask() throws Exception {
        doThrow(new BusinessException(ErrorCode.TASK_NOT_FOUND))
            .when(taskResultService).getResult("task_missing", "Bearer access-token");

        mockMvc.perform(get("/api/tasks/{taskId}/results", "task_missing")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isNotFound())
            .andExpect(content().string(containsString(ErrorCode.TASK_NOT_FOUND.code())));
    }

    @Test
    void resultEndpointRequiresAuthorization() throws Exception {
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(taskResultService).getResult("task_1", null);

        mockMvc.perform(get("/api/tasks/{taskId}/results", "task_1"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string(containsString(ErrorCode.COMMON_UNAUTHORIZED.code())));
    }

    private static TaskResultResponse result() {
        return new TaskResultResponse(
            "task_1",
            "zh-CN",
            "hello",
            List.of("hello"),
            "你好",
            List.of(new ResultSubtitleSegment(0, 0L, 3000L, "en", "hello")),
            List.of(new ResultTranslationSegment(0, 0L, 3000L, "en", "zh-CN", "你好")),
            new ResultLearningPackage("zh-CN", "Lesson", "Summary", List.of(), List.of(), List.of()),
            List.of(new ResultArtifactFile(
                "JSON",
                "zh-CN",
                "task_1-zh-CN.json",
                "application/json; charset=utf-8",
                1234L,
                "abc123",
                time()
            )),
            List.of(),
            List.of(),
            List.of(new ResultAiCallRecord(
                7L,
                "LLM",
                "TRANSLATION",
                "mock-llm",
                "mock-model",
                "SUCCEEDED",
                100L,
                10,
                20,
                30,
                time()
            ))
        );
    }

    private static LocalDateTime time() {
        return LocalDateTime.of(2026, 6, 28, 10, 0);
    }
}
