package com.example.courselingo.common.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.example.courselingo.common.logging.StructuredLogFields;
import com.example.courselingo.common.response.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@WebMvcTest(GlobalExceptionStructuredLoggingTest.TestController.class)
@Import({
    GlobalExceptionHandler.class,
    StructuredRequestLoggingFilter.class,
    GlobalExceptionStructuredLoggingTest.TestController.class
})
class GlobalExceptionStructuredLoggingTest {

    private final MockMvc mockMvc;
    private final Logger logger = (Logger) LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @Autowired
    GlobalExceptionStructuredLoggingTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @Test
    void exceptionLogSanitizesAndLimitsErrorMessage() throws Exception {
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            mockMvc.perform(get("/test/sensitive-error").header(StructuredLogFields.REQUEST_ID_HEADER, "req-123"))
                .andExpect(status().isInternalServerError());

            assertThat(appender.list).hasSize(1);
            ILoggingEvent event = appender.list.getFirst();
            assertThat(event.getFormattedMessage())
                .contains("event=exception_handled")
                .contains("errorCode=COMMON_INTERNAL_ERROR")
                .contains("exceptionType=IllegalStateException")
                .doesNotContain("Bearer access-token")
                .doesNotContain("api_key=secret")
                .doesNotContain("C:\\Users\\demo")
                .doesNotContain("/tmp/courselingo")
                .doesNotContain("raw prompt")
                .doesNotContain("raw response");
            assertThat(event.getFormattedMessage()).hasSizeLessThan(900);
            assertThat(event.getMDCPropertyMap()).containsEntry(StructuredLogFields.REQUEST_ID, "req-123");
        } finally {
            logger.detachAppender(appender);
        }
    }

    @Test
    void validationExceptionLogUsesSafeSummary() throws Exception {
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            mockMvc.perform(post("/test/validation")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":\"\",\"note\":\"secret request body\"}"))
                .andExpect(status().isBadRequest());

            assertThat(appender.list).hasSize(1);
            assertThat(appender.list.getFirst().getFormattedMessage())
                .contains("event=exception_handled")
                .contains("errorCode=COMMON_VALIDATION_FAILED")
                .contains("exceptionType=MethodArgumentNotValidException")
                .contains("errorMessage=请求参数校验失败")
                .doesNotContain("secret request body");
        } finally {
            logger.detachAppender(appender);
        }
    }

    @RestController
    public static class TestController {

        @GetMapping("/test/sensitive-error")
        ApiResponse<Void> sensitiveError() {
            throw new IllegalStateException(
                "Authorization: Bearer access-token api_key=secret C:\\Users\\demo\\file.wav "
                    + "/tmp/courselingo/audio.wav raw prompt: " + "x".repeat(600) + " raw response: y"
            );
        }

        @PostMapping("/test/validation")
        ApiResponse<Void> validation(@Valid @RequestBody TestRequest request) {
            return ApiResponse.success();
        }
    }

    public record TestRequest(@NotBlank String name) {
    }
}
