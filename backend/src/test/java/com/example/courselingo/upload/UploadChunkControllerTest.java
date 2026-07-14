package com.example.courselingo.upload;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import com.example.courselingo.upload.controller.UploadSessionController;
import com.example.courselingo.upload.dto.UploadChunkResponse;
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
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(UploadSessionController.class)
@Import(GlobalExceptionHandler.class)
class UploadChunkControllerTest {

    private final MockMvc mockMvc;

    @Autowired
    private UploadChunkService uploadChunkService;

    @Autowired
    UploadChunkControllerTest(MockMvc mockMvc) {
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
    void uploadChunkReturnsSuccessForValidBearerAccessTokenAndMultipartFile() throws Exception {
        when(uploadChunkService.upload(eq("Bearer access-token"), eq("up_abc123"), eq(0), any()))
            .thenReturn(new UploadChunkResponse("up_abc123", 0, true, "UPLOADING"));

        mockMvc.perform(multipart("/api/uploads/sessions/{uploadId}/chunks/{chunkIndex}", "up_abc123", 0)
                .file(chunk("file", "lesson-01.mp4", bytes(8)))
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("0"))
            .andExpect(jsonPath("$.message").value("ok"))
            .andExpect(jsonPath("$.data.uploadId").value("up_abc123"))
            .andExpect(jsonPath("$.data.chunkIndex").value(0))
            .andExpect(jsonPath("$.data.uploaded").value(true))
            .andExpect(jsonPath("$.data.status").value("UPLOADING"))
            .andExpect(jsonPath("$.data.objectKey").doesNotExist())
            .andExpect(jsonPath("$.data.localPath").doesNotExist())
            .andExpect(jsonPath("$.data.userId").doesNotExist())
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("localPath"))))
            .andExpect(content().string(not(containsString("userId"))));
    }

    @Test
    void uploadChunkIgnoresForgedUserIdFromHeaderQueryAndMultipartFields() throws Exception {
        clearInvocations(uploadChunkService);
        when(uploadChunkService.upload(eq("Bearer access-token"), eq("up_abc123"), eq(0), any()))
            .thenReturn(new UploadChunkResponse("up_abc123", 0, true, "UPLOADING"));

        mockMvc.perform(multipart("/api/uploads/sessions/{uploadId}/chunks/{chunkIndex}?userId=99", "up_abc123", 0)
                .file(chunk("file", "lesson-01.mp4", bytes(8)))
                .param("ownerId", "99")
                .param("userId", "99")
                .header("X-User-Id", "99")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.userId").doesNotExist())
            .andExpect(content().string(not(containsString("userId"))));

        verify(uploadChunkService).upload(eq("Bearer access-token"), eq("up_abc123"), eq(0), any());
    }

    @Test
    void uploadChunkReturnsUnauthorizedWhenAuthorizationHeaderMissing() throws Exception {
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(uploadChunkService).upload(isNull(), eq("up_abc123"), eq(0), any());

        mockMvc.perform(multipart("/api/uploads/sessions/{uploadId}/chunks/{chunkIndex}", "up_abc123", 0)
                .file(chunk("file", "lesson-01.mp4", bytes(8))))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_UNAUTHORIZED.code()));
    }

    @Test
    void uploadChunkRejectsRefreshOrNonAccessToken() throws Exception {
        doThrow(new BusinessException(ErrorCode.AUTH_TOKEN_INVALID))
            .when(uploadChunkService).upload(eq("Bearer refresh-token"), eq("up_abc123"), eq(0), any());

        mockMvc.perform(multipart("/api/uploads/sessions/{uploadId}/chunks/{chunkIndex}", "up_abc123", 0)
                .file(chunk("file", "lesson-01.mp4", bytes(8)))
                .header("Authorization", "Bearer refresh-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value(ErrorCode.AUTH_TOKEN_INVALID.code()));
    }

    @Test
    void uploadChunkRejectsMissingFileField() throws Exception {
        doThrow(new BusinessException(ErrorCode.UPLOAD_EMPTY_CHUNK))
            .when(uploadChunkService).upload(eq("Bearer access-token"), eq("up_abc123"), eq(0), isNull());

        mockMvc.perform(multipart("/api/uploads/sessions/{uploadId}/chunks/{chunkIndex}", "up_abc123", 0)
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.UPLOAD_EMPTY_CHUNK.code()));
    }

    @Test
    void uploadChunkRejectsEmptyFile() throws Exception {
        doThrow(new BusinessException(ErrorCode.UPLOAD_EMPTY_CHUNK))
            .when(uploadChunkService).upload(eq("Bearer access-token"), eq("up_abc123"), eq(0), any());

        mockMvc.perform(multipart("/api/uploads/sessions/{uploadId}/chunks/{chunkIndex}", "up_abc123", 0)
                .file(chunk("file", "lesson-01.mp4", new byte[0]))
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.UPLOAD_EMPTY_CHUNK.code()));
    }

    @Test
    void uploadChunkRejectsNegativeChunkIndex() throws Exception {
        doThrow(new BusinessException(ErrorCode.UPLOAD_INVALID_CHUNK))
            .when(uploadChunkService).upload(eq("Bearer access-token"), eq("up_abc123"), eq(-1), any());

        mockMvc.perform(multipart("/api/uploads/sessions/{uploadId}/chunks/{chunkIndex}", "up_abc123", -1)
                .file(chunk("file", "lesson-01.mp4", bytes(8)))
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.UPLOAD_INVALID_CHUNK.code()));
    }

    @Test
    void uploadChunkRejectsChunkIndexAtOrAboveTotalChunks() throws Exception {
        doThrow(new BusinessException(ErrorCode.UPLOAD_INVALID_CHUNK))
            .when(uploadChunkService).upload(eq("Bearer access-token"), eq("up_abc123"), eq(3), any());

        mockMvc.perform(multipart("/api/uploads/sessions/{uploadId}/chunks/{chunkIndex}", "up_abc123", 3)
                .file(chunk("file", "lesson-01.mp4", bytes(8)))
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.UPLOAD_INVALID_CHUNK.code()));
    }

    private static MockMultipartFile chunk(String name, String originalFilename, byte[] content) {
        return new MockMultipartFile(name, originalFilename, MediaType.APPLICATION_OCTET_STREAM_VALUE, content);
    }

    private static byte[] bytes(int size) {
        byte[] content = new byte[size];
        for (int i = 0; i < size; i++) {
            content[i] = (byte) i;
        }
        return content;
    }
}
