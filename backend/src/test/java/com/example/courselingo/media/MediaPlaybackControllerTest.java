package com.example.courselingo.media;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import java.io.ByteArrayInputStream;
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(MediaPlaybackController.class)
@Import({GlobalExceptionHandler.class, MediaPlaybackControllerTest.TestConfig.class})
class MediaPlaybackControllerTest {

    private final MockMvc mockMvc;

    @Autowired
    private MediaPlaybackService mediaPlaybackService;

    @Autowired
    MediaPlaybackControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @BeforeEach
    void resetMocks() {
        Mockito.reset(mediaPlaybackService);
    }

    @TestConfiguration
    static class TestConfig {

        @Bean
        MediaPlaybackService mediaPlaybackService() {
            return Mockito.mock(MediaPlaybackService.class);
        }
    }

    @Test
    void uploadPlaybackTokenResponseDoesNotExposeStorageDetails() throws Exception {
        when(mediaPlaybackService.requestUploadPlaybackToken(eq("Bearer access-token"), eq("up_abc123")))
            .thenReturn(new PlaybackTokenResponse(
                "playback-token",
                Instant.parse("2026-07-04T12:15:00Z"),
                "/api/media/uploads/up_abc123/stream?token=playback-token"
            ));

        mockMvc.perform(post("/api/uploads/{uploadId}/playback-token", "up_abc123")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("0"))
            .andExpect(jsonPath("$.data.token").value("playback-token"))
            .andExpect(jsonPath("$.data.expiresAt").value("2026-07-04T12:15:00Z"))
            .andExpect(jsonPath("$.data.playbackUrl").value("/api/media/uploads/up_abc123/stream?token=playback-token"))
            .andExpect(jsonPath("$.data.objectKey").doesNotExist())
            .andExpect(jsonPath("$.data.localPath").doesNotExist())
            .andExpect(jsonPath("$.data.userId").doesNotExist())
            .andExpect(content().string(not(containsString("raw/42"))))
            .andExpect(content().string(not(containsString("localPath"))));
    }

    @Test
    void taskPlaybackTokenUsesBearerAuthentication() throws Exception {
        when(mediaPlaybackService.requestTaskPlaybackToken(eq("Bearer access-token"), eq("task_abc123")))
            .thenReturn(new PlaybackTokenResponse(
                "playback-token",
                Instant.parse("2026-07-04T12:15:00Z"),
                "/api/media/uploads/up_abc123/stream?token=playback-token"
            ));

        mockMvc.perform(post("/api/tasks/{taskId}/playback-token", "task_abc123")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.playbackUrl").value("/api/media/uploads/up_abc123/stream?token=playback-token"));
    }

    @Test
    void uploadPlaybackTokenRejectsMissingAuthorization() throws Exception {
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(mediaPlaybackService).requestUploadPlaybackToken(isNull(), eq("up_abc123"));

        mockMvc.perform(post("/api/uploads/{uploadId}/playback-token", "up_abc123"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value(ErrorCode.COMMON_UNAUTHORIZED.code()));
    }

    @Test
    void streamReturnsPartialContentWithRangeHeaders() throws Exception {
        when(mediaPlaybackService.stream(eq("up_abc123"), eq("playback-token"), eq("bytes=0-9")))
            .thenReturn(new MediaStreamResponse(
                206,
                "video/mp4",
                10,
                "bytes 0-9/36",
                new ByteArrayInputStream("0123456789".getBytes(java.nio.charset.StandardCharsets.UTF_8))
            ));

        mockMvc.perform(get("/api/media/uploads/{uploadId}/stream", "up_abc123")
                .queryParam("token", "playback-token")
                .header("Range", "bytes=0-9"))
            .andExpect(status().isPartialContent())
            .andExpect(header().string("Accept-Ranges", "bytes"))
            .andExpect(header().string("Content-Range", "bytes 0-9/36"))
            .andExpect(header().longValue("Content-Length", 10))
            .andExpect(header().string("Content-Type", "video/mp4"))
            .andExpect(header().string("Content-Disposition", "inline"))
            .andExpect(content().bytes("0123456789".getBytes(java.nio.charset.StandardCharsets.UTF_8)));
    }

    @Test
    void streamRejectsInvalidRangeWithContentRangeHeader() throws Exception {
        doThrow(new MediaRangeNotSatisfiableException(36))
            .when(mediaPlaybackService).stream(eq("up_abc123"), eq("playback-token"), eq("bytes=999-1000"));

        mockMvc.perform(get("/api/media/uploads/{uploadId}/stream", "up_abc123")
                .queryParam("token", "playback-token")
                .header("Range", "bytes=999-1000"))
            .andExpect(status().isRequestedRangeNotSatisfiable())
            .andExpect(header().string("Accept-Ranges", "bytes"))
            .andExpect(header().string("Content-Range", "bytes */36"))
            .andExpect(jsonPath("$.code").value(ErrorCode.MEDIA_RANGE_NOT_SATISFIABLE.code()));
    }
}
