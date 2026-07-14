package com.example.courselingo.upload;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import com.example.courselingo.upload.controller.UploadSessionController;
import com.example.courselingo.upload.dto.CompleteUploadResponse;
import com.example.courselingo.upload.service.CompleteUploadService;
import com.example.courselingo.upload.service.MissingChunksService;
import com.example.courselingo.upload.service.UploadChunkService;
import com.example.courselingo.upload.service.UploadSessionService;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(UploadSessionController.class)
@Import(GlobalExceptionHandler.class)
class CompleteUploadControllerTest {

    private final MockMvc mockMvc;

    @Autowired
    private CompleteUploadService completeUploadService;

    @Autowired
    CompleteUploadControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @TestConfiguration
    static class TestConfig {

        @Bean
        UploadSessionService uploadSessionService() {
            return Mockito.mock(UploadSessionService.class);
        }

        @Bean
        UploadChunkService uploadChunkService() {
            return Mockito.mock(UploadChunkService.class);
        }

        @Bean
        MissingChunksService missingChunksService() {
            return Mockito.mock(MissingChunksService.class);
        }

        @Bean
        CompleteUploadService completeUploadService() {
            return Mockito.mock(CompleteUploadService.class);
        }
    }

    @Test
    void completeUploadReturnsSuccessForValidBearerAccessToken() throws Exception {
        when(completeUploadService.complete(eq("Bearer access-token"), eq("up_abc123")))
            .thenReturn(new CompleteUploadResponse(
                "up_abc123",
                "STORED",
                12L,
                "e1b6b2b3211076a71632bbf2ad0edc05"
            ));

        mockMvc.perform(post("/api/uploads/sessions/{uploadId}/complete", "up_abc123")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("0"))
            .andExpect(jsonPath("$.message").value("ok"))
            .andExpect(jsonPath("$.data.uploadId").value("up_abc123"))
            .andExpect(jsonPath("$.data.status").value("STORED"))
            .andExpect(jsonPath("$.data.sizeBytes").value(12))
            .andExpect(jsonPath("$.data.fileMd5").value("e1b6b2b3211076a71632bbf2ad0edc05"))
            .andExpect(jsonPath("$.data.objectKey").doesNotExist())
            .andExpect(jsonPath("$.data.localPath").doesNotExist())
            .andExpect(jsonPath("$.data.userId").doesNotExist())
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("localPath"))))
            .andExpect(content().string(not(containsString("userId"))));
    }

    @Test
    void completeUploadReturnsUnauthorizedWhenAuthorizationHeaderMissing() throws Exception {
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(completeUploadService).complete(isNull(), eq("up_abc123"));

        mockMvc.perform(post("/api/uploads/sessions/{uploadId}/complete", "up_abc123"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_UNAUTHORIZED.code()));
    }

    @Test
    void completeUploadRejectsRefreshOrNonAccessToken() throws Exception {
        doThrow(new BusinessException(ErrorCode.AUTH_TOKEN_INVALID))
            .when(completeUploadService).complete(eq("Bearer refresh-token"), eq("up_abc123"));

        mockMvc.perform(post("/api/uploads/sessions/{uploadId}/complete", "up_abc123")
                .header("Authorization", "Bearer refresh-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value(ErrorCode.AUTH_TOKEN_INVALID.code()));
    }

    @Test
    void completeUploadRejectsInvalidUploadIdFormat() throws Exception {
        doThrow(new BusinessException(ErrorCode.UPLOAD_INVALID_SESSION_ID))
            .when(completeUploadService).complete(eq("Bearer access-token"), eq("..%2Fbad"));

        mockMvc.perform(post("/api/uploads/sessions/{uploadId}/complete", "..%2Fbad")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.UPLOAD_INVALID_SESSION_ID.code()));
    }
}
