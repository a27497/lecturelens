package com.example.courselingo.qa;

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
import com.example.courselingo.qa.controller.CourseQaController;
import com.example.courselingo.qa.dto.CourseQaAskRequest;
import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import com.example.courselingo.qa.dto.CourseQaResponse;
import com.example.courselingo.qa.dto.CourseQaUsage;
import com.example.courselingo.qa.service.CourseQaService;
import java.util.List;
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

@WebMvcTest(CourseQaController.class)
@Import({GlobalExceptionHandler.class, CourseQaControllerTest.TestConfig.class})
class CourseQaControllerTest {

    private final MockMvc mockMvc;

    @Autowired
    private CourseQaService courseQaService;

    @Autowired
    CourseQaControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @BeforeEach
    void resetMocks() {
        Mockito.reset(courseQaService);
    }

    @TestConfiguration
    static class TestConfig {
        @Bean
        CourseQaService courseQaService() {
            return Mockito.mock(CourseQaService.class);
        }
    }

    @Test
    void askReturnsAnswerEvidenceAndUsageWithoutSensitiveFields() throws Exception {
        CourseQaResponse response = new CourseQaResponse(
            "101",
            "The course explains OpenCL around 00:03:00.",
            List.of(new CourseQaEvidenceItem(
                "VIDEO_SEGMENT",
                "10",
                180000L,
                240000L,
                "00:03:00 - 00:04:00",
                "OpenCL gateway",
                "OpenCL gateway summary",
                0.9d
            )),
            new CourseQaUsage("openai-compatible", "qa-model", 10, 20, 30, 250L)
        );
        CourseQaAskRequest request = new CourseQaAskRequest("Where is OpenCL discussed?");
        when(courseQaService.ask("task_1", "Bearer demo", request)).thenReturn(response);

        mockMvc.perform(post("/api/tasks/{taskId}/qa", "task_1")
                .header("Authorization", "Bearer demo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"question\":\"Where is OpenCL discussed?\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.recordId").value("101"))
            .andExpect(jsonPath("$.data.answer").value("The course explains OpenCL around 00:03:00."))
            .andExpect(jsonPath("$.data.evidence[0].sourceType").value("VIDEO_SEGMENT"))
            .andExpect(jsonPath("$.data.evidence[0].startTimeMillis").value(180000))
            .andExpect(jsonPath("$.data.usage.totalTokens").value(30))
            .andExpect(content().string(not(containsString("object" + "Key"))))
            .andExpect(content().string(not(containsString("raw" + "Prompt"))))
            .andExpect(content().string(not(containsString("raw" + "Response"))))
            .andExpect(content().string(not(containsString("api" + "Key"))))
            .andExpect(content().string(not(containsString("token"))));

        verify(courseQaService).ask("task_1", "Bearer demo", request);
    }

    @Test
    void askMapsTaskNotFoundAndRateLimitErrors() throws Exception {
        CourseQaAskRequest request = new CourseQaAskRequest("hello");
        doThrow(new BusinessException(ErrorCode.TASK_NOT_FOUND))
            .when(courseQaService)
            .ask("task_missing", "Bearer demo", request);

        mockMvc.perform(post("/api/tasks/{taskId}/qa", "task_missing")
                .header("Authorization", "Bearer demo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"question\":\"hello\"}"))
            .andExpect(status().isNotFound())
            .andExpect(content().string(containsString(ErrorCode.TASK_NOT_FOUND.code())));

        doThrow(new BusinessException(ErrorCode.TASK_RATE_LIMITED))
            .when(courseQaService)
            .ask("task_1", "Bearer demo", request);

        mockMvc.perform(post("/api/tasks/{taskId}/qa", "task_1")
                .header("Authorization", "Bearer demo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"question\":\"hello\"}"))
            .andExpect(status().isTooManyRequests())
            .andExpect(content().string(containsString(ErrorCode.TASK_RATE_LIMITED.code())));
    }

    @Test
    void askReturnsExactInsufficientEvidenceJsonContract() throws Exception {
        CourseQaAskRequest request = new CourseQaAskRequest("unrelated question");
        when(courseQaService.ask("task_1", "Bearer demo", request)).thenReturn(new CourseQaResponse(
            "102",
            "当前课程内容中没有找到明确依据",
            List.of(),
            null
        ));

        mockMvc.perform(post("/api/tasks/{taskId}/qa", "task_1")
                .header("Authorization", "Bearer demo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"question\":\"unrelated question\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.answer").value("当前课程内容中没有找到明确依据"))
            .andExpect(jsonPath("$.data.evidence").isEmpty())
            .andExpect(jsonPath("$.data.usage").doesNotExist())
            .andExpect(content().string(containsString("\"usage\":null")));

        verify(courseQaService).ask("task_1", "Bearer demo", request);
    }
}
