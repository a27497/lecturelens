package com.example.courselingo.fusion;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(VideoSegmentController.class)
@Import({GlobalExceptionHandler.class, VideoSegmentControllerTest.TestConfig.class})
class VideoSegmentControllerTest {

    private final MockMvc mockMvc;

    @Autowired
    private VideoSegmentService videoSegmentService;

    @Autowired
    VideoSegmentControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @BeforeEach
    void resetMocks() {
        Mockito.reset(videoSegmentService);
    }

    @TestConfiguration
    static class TestConfig {

        @Bean
        VideoSegmentService videoSegmentService() {
            return Mockito.mock(VideoSegmentService.class);
        }
    }

    @Test
    void videoSegmentsEndpointReturnsOwnerScopedSafePayload() throws Exception {
        when(videoSegmentService.listForCurrentUser("Bearer access-token", "task_1", 20, 0, "redis"))
            .thenReturn(List.of(response()));

        mockMvc.perform(get("/api/tasks/{taskId}/video-segments", "task_1")
                .header("Authorization", "Bearer access-token")
                .param("limit", "20")
                .param("offset", "0")
                .param("keyword", "redis")
                .param("userId", "999"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data[0].segmentId").value(1L))
            .andExpect(jsonPath("$.data[0].fusedSummary").value("Segment summary Redis"))
            .andExpect(jsonPath("$.data[0].keywords[0]").value("Redis"))
            .andExpect(jsonPath("$.data[0].evidence.counts.asr").value(1))
            .andExpect(content().string(not(containsString("userId"))))
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("localPath"))))
            .andExpect(content().string(not(containsString("token"))))
            .andExpect(content().string(not(containsString("secret"))));

        verify(videoSegmentService).listForCurrentUser("Bearer access-token", "task_1", 20, 0, "redis");
    }

    @Test
    void videoSegmentsEndpointRequiresOwnerScope() throws Exception {
        doThrow(new BusinessException(ErrorCode.TASK_NOT_FOUND))
            .when(videoSegmentService).listForCurrentUser("Bearer access-token", "task_missing", 100, 0, "");

        mockMvc.perform(get("/api/tasks/{taskId}/video-segments", "task_missing")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isNotFound())
            .andExpect(content().string(containsString(ErrorCode.TASK_NOT_FOUND.code())));
    }

    @Test
    void rebuildEndpointReturnsOnlySafeFusionCounts() throws Exception {
        when(videoSegmentService.rebuildForCurrentUser("Bearer access-token", "task_1"))
            .thenReturn(new VideoSegmentFusionResult(69, 68, 1, 0));

        mockMvc.perform(post("/api/tasks/{taskId}/video-segments/rebuild", "task_1")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.windows").value(69))
            .andExpect(jsonPath("$.data.saved").value(68))
            .andExpect(jsonPath("$.data.empty").value(1))
            .andExpect(jsonPath("$.data.skipped").value(0))
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("localPath"))))
            .andExpect(content().string(not(containsString("token"))));

        verify(videoSegmentService).rebuildForCurrentUser("Bearer access-token", "task_1");
    }

    @Test
    void rebuildEndpointMapsOwnerAndStatusGuards() throws Exception {
        doThrow(new BusinessException(ErrorCode.TASK_NOT_FOUND))
            .when(videoSegmentService).rebuildForCurrentUser("Bearer access-token", "task_missing");

        mockMvc.perform(post("/api/tasks/{taskId}/video-segments/rebuild", "task_missing")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code").value(ErrorCode.TASK_NOT_FOUND.code()));

        doThrow(new BusinessException(ErrorCode.TASK_INVALID_STATUS))
            .when(videoSegmentService).rebuildForCurrentUser("Bearer access-token", "task_running");

        mockMvc.perform(post("/api/tasks/{taskId}/video-segments/rebuild", "task_running")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value(ErrorCode.TASK_INVALID_STATUS.code()));
    }

    private static VideoSegmentResponse response() {
        return new VideoSegmentResponse(
            1L,
            0,
            0L,
            60_000L,
            "00:00:00 - 00:01:00",
            "Redis ASR",
            "Redis OCR",
            "Redis slide",
            "Segment summary Redis",
            List.of("Redis"),
            new VideoSegmentEvidence(List.of(11L), List.of(21L), List.of(31L), List.of(41L), Map.of("asr", 1, "ocr", 1)),
            VideoSegmentStatus.SUCCEEDED.name(),
            0.8
        );
    }
}
