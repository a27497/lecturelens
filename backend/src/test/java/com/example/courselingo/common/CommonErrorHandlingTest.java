package com.example.courselingo.common;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.response.ApiResponse;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@WebMvcTest(CommonErrorHandlingTest.TestController.class)
@Import({GlobalExceptionHandler.class, CommonErrorHandlingTest.TestController.class})
class CommonErrorHandlingTest {

    private final MockMvc mockMvc;

    @Autowired
    CommonErrorHandlingTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @Test
    void apiResponseSuccessUsesZeroCodeAndOkMessage() {
        ApiResponse<String> response = ApiResponse.success("pong");

        org.assertj.core.api.Assertions.assertThat(response.code()).isEqualTo("0");
        org.assertj.core.api.Assertions.assertThat(response.message()).isEqualTo("ok");
        org.assertj.core.api.Assertions.assertThat(response.data()).isEqualTo("pong");
        org.assertj.core.api.Assertions.assertThat(response.timestamp()).isNotNull();
        org.assertj.core.api.Assertions.assertThat(response.traceId()).isNotBlank();
    }

    @Test
    void businessExceptionCarriesErrorCode() {
        BusinessException exception = new BusinessException(ErrorCode.TASK_NOT_FOUND);

        org.assertj.core.api.Assertions.assertThat(exception.errorCode()).isEqualTo(ErrorCode.TASK_NOT_FOUND);
        org.assertj.core.api.Assertions.assertThat(exception.getMessage()).isEqualTo(ErrorCode.TASK_NOT_FOUND.defaultMessage());
    }

    @Test
    void businessExceptionKeepsCause() {
        IllegalArgumentException cause = new IllegalArgumentException("root cause");

        BusinessException exception = new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "provider failed", cause);

        org.assertj.core.api.Assertions.assertThat(exception.errorCode()).isEqualTo(ErrorCode.AI_PROVIDER_FAILED);
        org.assertj.core.api.Assertions.assertThat(exception.getMessage()).isEqualTo("provider failed");
        org.assertj.core.api.Assertions.assertThat(exception.getCause()).isSameAs(cause);
    }

    @Test
    void globalExceptionHandlerReturnsBusinessExceptionResponse() throws Exception {
        mockMvc.perform(get("/test/business-error").header("X-Trace-Id", "trace-123"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code").value(ErrorCode.TASK_NOT_FOUND.code()))
            .andExpect(jsonPath("$.message").value(ErrorCode.TASK_NOT_FOUND.defaultMessage()))
            .andExpect(jsonPath("$.traceId").value("trace-123"));
    }

    @Test
    void globalExceptionHandlerReturnsFieldValidationDetails() throws Exception {
        mockMvc.perform(post("/test/validation")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_VALIDATION_FAILED.code()))
            .andExpect(jsonPath("$.data.name").exists());
    }

    @Test
    void globalExceptionHandlerDoesNotExposeStackTraceForFallbackException() throws Exception {
        mockMvc.perform(get("/test/fallback-error").accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_INTERNAL_ERROR.code()))
            .andExpect(jsonPath("$.message").value(ErrorCode.COMMON_INTERNAL_ERROR.defaultMessage()))
            .andExpect(jsonPath("$.data").doesNotExist())
            .andExpect(content().string(not(containsString("IllegalStateException"))))
            .andExpect(content().string(not(containsString("at com.example"))));
    }

    @Test
    void globalExceptionHandlerReturnsNotFoundForMissingRoute() throws Exception {
        mockMvc.perform(get("/test/not-exists"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_NOT_FOUND.code()));
    }

    @RestController
    public static class TestController {

        @GetMapping("/test/business-error")
        ApiResponse<Void> businessError() {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }

        @GetMapping("/test/missing-param")
        ApiResponse<Void> missingParam(@RequestParam("name") String name) {
            return ApiResponse.success();
        }

        @org.springframework.web.bind.annotation.PostMapping("/test/validation")
        ApiResponse<Void> validation(@Valid @RequestBody TestRequest request) {
            return ApiResponse.success();
        }

        @GetMapping("/test/fallback-error")
        ApiResponse<Void> fallbackError() {
            throw new IllegalStateException("database password leaked stack trace should never be returned");
        }
    }

    public record TestRequest(@NotBlank String name) {
    }
}
