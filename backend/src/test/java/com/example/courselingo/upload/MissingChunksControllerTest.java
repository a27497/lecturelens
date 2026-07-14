package com.example.courselingo.upload;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import com.example.courselingo.upload.controller.UploadSessionController;
import com.example.courselingo.upload.dto.MissingChunksResponse;
import com.example.courselingo.upload.service.CompleteUploadService;
import com.example.courselingo.upload.service.MissingChunksService;
import com.example.courselingo.upload.service.UploadChunkService;
import com.example.courselingo.upload.service.UploadSessionService;
import java.util.List;
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
class MissingChunksControllerTest {

    private final MockMvc mockMvc;

    @Autowired
    private MissingChunksService missingChunksService;

    @Autowired
    MissingChunksControllerTest(MockMvc mockMvc) {
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
    void missingChunksReturnsSuccessForValidBearerAccessToken() throws Exception {
        when(missingChunksService.findMissingChunks(eq("Bearer access-token"), eq("up_abc123")))
            .thenReturn(new MissingChunksResponse(
                "up_abc123",
                5,
                List.of(0, 2, 4),
                List.of(1, 3),
                false,
                "UPLOADING"
            ));

        mockMvc.perform(get("/api/uploads/sessions/{uploadId}/missing-chunks", "up_abc123")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("0"))
            .andExpect(jsonPath("$.message").value("ok"))
            .andExpect(jsonPath("$.data.uploadId").value("up_abc123"))
            .andExpect(jsonPath("$.data.totalChunks").value(5))
            .andExpect(jsonPath("$.data.uploadedChunks[0]").value(0))
            .andExpect(jsonPath("$.data.uploadedChunks[1]").value(2))
            .andExpect(jsonPath("$.data.uploadedChunks[2]").value(4))
            .andExpect(jsonPath("$.data.missingChunks[0]").value(1))
            .andExpect(jsonPath("$.data.missingChunks[1]").value(3))
            .andExpect(jsonPath("$.data.allUploaded").value(false))
            .andExpect(jsonPath("$.data.status").value("UPLOADING"))
            .andExpect(jsonPath("$.data.objectKey").doesNotExist())
            .andExpect(jsonPath("$.data.localPath").doesNotExist())
            .andExpect(jsonPath("$.data.userId").doesNotExist())
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("localPath"))))
            .andExpect(content().string(not(containsString("userId"))));
    }

    @Test
    void missingChunksReturnsUnauthorizedWhenAuthorizationHeaderMissing() throws Exception {
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(missingChunksService).findMissingChunks(isNull(), eq("up_abc123"));

        mockMvc.perform(get("/api/uploads/sessions/{uploadId}/missing-chunks", "up_abc123"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_UNAUTHORIZED.code()));
    }

    @Test
    void missingChunksRejectsRefreshOrNonAccessToken() throws Exception {
        doThrow(new BusinessException(ErrorCode.AUTH_TOKEN_INVALID))
            .when(missingChunksService).findMissingChunks(eq("Bearer refresh-token"), eq("up_abc123"));

        mockMvc.perform(get("/api/uploads/sessions/{uploadId}/missing-chunks", "up_abc123")
                .header("Authorization", "Bearer refresh-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value(ErrorCode.AUTH_TOKEN_INVALID.code()));
    }

    @Test
    void missingChunksRejectsInvalidUploadIdFormat() throws Exception {
        doThrow(new BusinessException(ErrorCode.UPLOAD_INVALID_SESSION_ID))
            .when(missingChunksService).findMissingChunks(eq("Bearer access-token"), eq("..%2Fbad"));

        mockMvc.perform(get("/api/uploads/sessions/{uploadId}/missing-chunks", "..%2Fbad")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.UPLOAD_INVALID_SESSION_ID.code()));
    }
}
