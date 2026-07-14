package com.example.courselingo.upload;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.any;
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
import com.example.courselingo.upload.dto.CreateUploadSessionResponse;
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
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(UploadSessionController.class)
@Import(GlobalExceptionHandler.class)
class UploadSessionControllerTest {

    private static final String VALID_REQUEST = """
        {
          "filename": "lesson-01.mp4",
          "sizeBytes": 524288000,
          "chunkSizeBytes": 5242880,
          "totalChunks": 100,
          "fileMd5": "d41d8cd98f00b204e9800998ecf8427e"
        }
        """;

    private final MockMvc mockMvc;

    @Autowired
    private UploadSessionService uploadSessionService;

    @Autowired
    private UploadChunkService uploadChunkService;

    @Autowired
    private MissingChunksService missingChunksService;

    @Autowired
    UploadSessionControllerTest(MockMvc mockMvc) {
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
    void createSessionReturnsApiResponseSuccessForValidBearerAccessTokenAndRequest() throws Exception {
        when(uploadSessionService.create(eq("Bearer access-token"), any()))
            .thenReturn(new CreateUploadSessionResponse("up_abc123", "CREATED"));

        mockMvc.perform(post("/api/uploads/sessions")
                .header("Authorization", "Bearer access-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_REQUEST))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("0"))
            .andExpect(jsonPath("$.message").value("ok"))
            .andExpect(jsonPath("$.data.uploadId").value("up_abc123"))
            .andExpect(jsonPath("$.data.status").value("CREATED"))
            .andExpect(jsonPath("$.data.objectKey").doesNotExist())
            .andExpect(jsonPath("$.data.userId").doesNotExist())
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("raw/"))));
    }

    @Test
    void createSessionReturnsUnauthorizedWhenAuthorizationHeaderMissing() throws Exception {
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(uploadSessionService).create(isNull(), requestAny());

        mockMvc.perform(post("/api/uploads/sessions")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_REQUEST))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_UNAUTHORIZED.code()));
    }

    @Test
    void createSessionRejectsRefreshOrNonAccessToken() throws Exception {
        doThrow(new BusinessException(ErrorCode.AUTH_TOKEN_INVALID))
            .when(uploadSessionService).create(eq("Bearer refresh-token"), requestAny());

        mockMvc.perform(post("/api/uploads/sessions")
                .header("Authorization", "Bearer refresh-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_REQUEST))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value(ErrorCode.AUTH_TOKEN_INVALID.code()));
    }

    @Test
    void createSessionReturnsValidationErrorWhenFilenameBlank() throws Exception {
        mockMvc.perform(post("/api/uploads/sessions")
                .header("Authorization", "Bearer access-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "filename": "",
                      "sizeBytes": 524288000,
                      "chunkSizeBytes": 5242880,
                      "totalChunks": 100,
                      "fileMd5": "d41d8cd98f00b204e9800998ecf8427e"
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_VALIDATION_FAILED.code()))
            .andExpect(jsonPath("$.data.filename").exists());
    }

    @Test
    void createSessionRejectsFilenameContainingSlash() throws Exception {
        doThrow(new BusinessException(ErrorCode.UPLOAD_INVALID_FILENAME))
            .when(uploadSessionService).create(eq("Bearer access-token"), requestAny());

        mockMvc.perform(post("/api/uploads/sessions")
                .header("Authorization", "Bearer access-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_REQUEST.replace("lesson-01.mp4", "course/lesson-01.mp4")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.UPLOAD_INVALID_FILENAME.code()));
    }

    @Test
    void createSessionRejectsFilenameContainingBackslash() throws Exception {
        doThrow(new BusinessException(ErrorCode.UPLOAD_INVALID_FILENAME))
            .when(uploadSessionService).create(eq("Bearer access-token"), requestAny());

        mockMvc.perform(post("/api/uploads/sessions")
                .header("Authorization", "Bearer access-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_REQUEST.replace("lesson-01.mp4", "course\\\\lesson-01.mp4")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.UPLOAD_INVALID_FILENAME.code()));
    }

    @Test
    void createSessionRejectsWindowsDriveStyleFilename() throws Exception {
        doThrow(new BusinessException(ErrorCode.UPLOAD_INVALID_FILENAME))
            .when(uploadSessionService).create(eq("Bearer access-token"), requestAny());

        mockMvc.perform(post("/api/uploads/sessions")
                .header("Authorization", "Bearer access-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_REQUEST.replace("lesson-01.mp4", "C:\\\\lesson-01.mp4")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.UPLOAD_INVALID_FILENAME.code()));
    }

    @Test
    void createSessionRejectsUnsupportedExtension() throws Exception {
        doThrow(new BusinessException(ErrorCode.UPLOAD_INVALID_EXTENSION))
            .when(uploadSessionService).create(eq("Bearer access-token"), requestAny());

        mockMvc.perform(post("/api/uploads/sessions")
                .header("Authorization", "Bearer access-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_REQUEST.replace("lesson-01.mp4", "lesson-01.exe")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.UPLOAD_INVALID_EXTENSION.code()));
    }

    @Test
    void createSessionRejectsInvalidMd5() throws Exception {
        doThrow(new BusinessException(ErrorCode.UPLOAD_INVALID_MD5))
            .when(uploadSessionService).create(eq("Bearer access-token"), requestAny());

        mockMvc.perform(post("/api/uploads/sessions")
                .header("Authorization", "Bearer access-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_REQUEST.replace("d41d8cd98f00b204e9800998ecf8427e", "not-md5")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value(ErrorCode.UPLOAD_INVALID_MD5.code()));
    }

    private static com.example.courselingo.upload.dto.CreateUploadSessionRequest requestAny() {
        return any(com.example.courselingo.upload.dto.CreateUploadSessionRequest.class);
    }
}
