package com.example.courselingo.vision.keyframe;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import com.example.courselingo.vision.analysis.VideoKeyframeAnalysisView;
import com.example.courselingo.vision.analysis.VisionAnalysisStatus;
import com.example.courselingo.vision.ocr.OcrStatus;
import com.example.courselingo.vision.ocr.VideoKeyframeOcrView;
import java.io.ByteArrayInputStream;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(VideoKeyframeController.class)
@Import({GlobalExceptionHandler.class, VideoKeyframeControllerTest.TestConfig.class})
class VideoKeyframeControllerTest {

    private final MockMvc mockMvc;

    @Autowired
    private VideoKeyframeService service;

    @Autowired
    VideoKeyframeControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @BeforeEach
    void resetMocks() {
        Mockito.reset(service);
    }

    @TestConfiguration
    static class TestConfig {

        @Bean
        VideoKeyframeService videoKeyframeService() {
            return Mockito.mock(VideoKeyframeService.class);
        }
    }

    @Test
    void keyframeListEndpointReturnsSafePayload() throws Exception {
        when(service.listKeyframes("Bearer access-token", "task_1")).thenReturn(List.of(new VideoKeyframeView(
            9L,
            12_345L,
            "00:12.345",
            "/api/tasks/task_1/keyframes/9/image",
            0.42,
            KeyframeSelectionReason.SCENE_CHANGE.name(),
            LocalDateTime.of(2026, 7, 6, 10, 0),
            new VideoKeyframeOcrView(
                OcrStatus.SUCCEEDED.name(),
                "slide title",
                "tesseract",
                "chi_sim+eng",
                0.9,
                false,
                ""
            ),
            new VideoKeyframeAnalysisView(
                VisionAnalysisStatus.SUCCEEDED.name(),
                "PPT",
                "A slide about CourseLingo",
                List.of("title", "diagram"),
                "openai-compatible-vision",
                "qwen-vl",
                ""
            )
        )));

        mockMvc.perform(get("/api/tasks/{taskId}/keyframes", "task_1")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data[0].frameId").value(9))
            .andExpect(jsonPath("$.data[0].timeText").value("00:12.345"))
            .andExpect(jsonPath("$.data[0].imageUrl").value("/api/tasks/task_1/keyframes/9/image"))
            .andExpect(jsonPath("$.data[0].ocr.status").value("SUCCEEDED"))
            .andExpect(jsonPath("$.data[0].ocr.text").value("slide title"))
            .andExpect(jsonPath("$.data[0].visualAnalysis.status").value("SUCCEEDED"))
            .andExpect(jsonPath("$.data[0].visualAnalysis.screenType").value("PPT"))
            .andExpect(jsonPath("$.data[0].visualAnalysis.summary").value("A slide about CourseLingo"))
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("localPath"))))
            .andExpect(content().string(not(containsString("stderr"))))
            .andExpect(content().string(not(containsString("secret"))))
            .andExpect(content().string(not(containsString("token"))));

        verify(service).listKeyframes("Bearer access-token", "task_1");
    }

    @Test
    void keyframeImageEndpointStreamsOwnerScopedBlob() throws Exception {
        when(service.downloadKeyframeImage("Bearer access-token", "task_1", 9L))
            .thenReturn(new VideoKeyframeImage(
                "frame-000009.jpg",
                "image/jpeg",
                3L,
                new ByteArrayInputStream(new byte[] {1, 2, 3})
            ));

        mockMvc.perform(get("/api/tasks/{taskId}/keyframes/{frameId}/image", "task_1", 9L)
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(header().string("Content-Type", containsString("image/jpeg")))
            .andExpect(content().bytes(new byte[] {1, 2, 3}));
    }

    @Test
    void missingOrNonOwnerTaskReturnsNotFound() throws Exception {
        doThrow(new BusinessException(ErrorCode.TASK_NOT_FOUND))
            .when(service).listKeyframes("Bearer access-token", "task_missing");

        mockMvc.perform(get("/api/tasks/{taskId}/keyframes", "task_missing")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isNotFound())
            .andExpect(content().string(containsString(ErrorCode.TASK_NOT_FOUND.code())));
    }
}
