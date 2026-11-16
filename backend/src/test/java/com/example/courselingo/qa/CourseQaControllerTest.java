package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.ai.llm.LlmProviderFailureCategory;
import com.example.courselingo.ai.llm.LlmProviderFailureDetails;
import com.example.courselingo.ai.llm.LlmStageException;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import com.example.courselingo.qa.controller.CourseQaController;
import com.example.courselingo.qa.dto.CourseQaAskRequest;
import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import com.example.courselingo.qa.dto.CourseQaResponse;
import com.example.courselingo.qa.dto.CourseQaUsage;
import com.example.courselingo.qa.service.CourseQaService;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
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
    private ObjectMapper objectMapper;

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
    void scopedRouteRequiresScopeAndLegacyRouteRejectsScopedPayloads() throws Exception {
        String body="{\"question\":\"Explain selection\",\"learning_scope\":{\"version\":1,\"kind\":\"segments\",\"policy\":\"strict\",\"revision\":1,\"evidence_ids\":[\"selected\"]}}";
        mockMvc.perform(post("/api/tasks/course/qa/scoped").contentType(MediaType.APPLICATION_JSON).content(body)).andExpect(status().isOk());
        var capture=org.mockito.ArgumentCaptor.forClass(CourseQaAskRequest.class);
        verify(courseQaService).ask(Mockito.eq("course"),Mockito.isNull(),capture.capture());
        org.assertj.core.api.Assertions.assertThat(capture.getValue().learning_scope().evidence_ids()).containsExactly("selected");
        Mockito.clearInvocations(courseQaService);
        mockMvc.perform(post("/api/tasks/course/qa").contentType(MediaType.APPLICATION_JSON).content(body)).andExpect(status().isBadRequest());
        mockMvc.perform(post("/api/tasks/course/qa/scoped").contentType(MediaType.APPLICATION_JSON).content("{\"question\":\"Explain\"}")).andExpect(status().isBadRequest());
        Mockito.verifyNoInteractions(courseQaService);
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
    void askReturnsExactProviderTimeoutResponse() throws Exception {
        var failure = new LlmStageException("COURSE_QA",
            new LlmProviderFailureDetails(LlmProviderFailureCategory.TIMEOUT, null, null, true), null);

        assertAskError(failure, 504, """
            {
              "code": "AI_PROVIDER_TIMEOUT",
              "message": "课程问答响应超时，本次请求已结束，请稍后重试。",
              "data": {
                "errorCode": "COURSE_QA_PROVIDER_TIMEOUT",
                "errorCategory": "TIMEOUT",
                "retryable": true,
                "stage": "COURSE_QA",
                "userMessage": "课程问答响应超时，本次请求已结束，请稍后重试。"
              },
              "traceId": "qa-error-trace"
            }
            """);
    }

    @Test
    void askReturnsExactModelNotFoundResponse() throws Exception {
        var failure = new LlmStageException("COURSE_QA",
            new LlmProviderFailureDetails(LlmProviderFailureCategory.MODEL_NOT_FOUND, 404, "provider-only-code", false),
            new IllegalStateException("provider-only-message"));

        assertAskError(failure, 502, """
            {
              "code": "AI_PROVIDER_FAILED",
              "message": "当前 AI 模型不可用，请检查模型配置。",
              "data": {
                "errorCode": "MODEL_NOT_FOUND",
                "errorCategory": "MODEL_NOT_FOUND",
                "retryable": false,
                "stage": "COURSE_QA",
                "userMessage": "当前 AI 模型不可用，请检查模型配置。"
              },
              "traceId": "qa-error-trace"
            }
            """);
    }

    @Test
    void askKeepsFallbackResponseWhenProviderFailureIsWrapped() throws Exception {
        var cause = new LlmStageException("COURSE_QA",
            new LlmProviderFailureDetails(LlmProviderFailureCategory.TIMEOUT, null, null, true), null);

        assertAskError(new IllegalStateException("unexpected failure", cause), 500, """
            {
              "code": "COMMON_INTERNAL_ERROR",
              "message": "服务内部错误",
              "traceId": "qa-error-trace"
            }
            """);
    }

    private void assertAskError(RuntimeException failure, int expectedStatus, String expectedBody) throws Exception {
        when(courseQaService.ask("task_1", "Bearer demo", new CourseQaAskRequest("hello"))).thenThrow(failure);

        var result = mockMvc.perform(post("/api/tasks/{taskId}/qa", "task_1")
                .header("Authorization", "Bearer demo")
                .header("X-Trace-Id", "qa-error-trace")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"question\":\"hello\"}"))
            .andExpect(status().is(expectedStatus))
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.timestamp").isString())
            .andReturn();

        var body = (ObjectNode) objectMapper.readTree(result.getResponse().getContentAsByteArray());
        body.remove("timestamp");
        assertThat(body).isEqualTo(objectMapper.readTree(expectedBody));
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
