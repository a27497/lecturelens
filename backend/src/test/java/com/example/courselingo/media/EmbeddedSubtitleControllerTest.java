package com.example.courselingo.media;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.common.web.GlobalExceptionHandler;
import java.nio.charset.StandardCharsets;
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

@WebMvcTest(EmbeddedSubtitleController.class)
@Import({GlobalExceptionHandler.class, EmbeddedSubtitleControllerTest.TestConfig.class})
class EmbeddedSubtitleControllerTest {

    private final MockMvc mockMvc;

    @Autowired
    private EmbeddedSubtitleService embeddedSubtitleService;

    @Autowired
    EmbeddedSubtitleControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @BeforeEach
    void resetMocks() {
        Mockito.reset(embeddedSubtitleService);
    }

    @TestConfiguration
    static class TestConfig {

        @Bean
        EmbeddedSubtitleService embeddedSubtitleService() {
            return Mockito.mock(EmbeddedSubtitleService.class);
        }
    }

    @Test
    void probeUploadReturnsSelectedEmbeddedSubtitleTrack() throws Exception {
        when(embeddedSubtitleService.probeUpload(eq("Bearer access-token"), eq("up_abc123")))
            .thenReturn(new EmbeddedSubtitleProbeResponse(
                EmbeddedSubtitleStatus.FOUND,
                List.of(new EmbeddedSubtitleTrackResponse(3, "subrip", "zho", "Chinese", true, true, "")),
                3
            ));

        mockMvc.perform(get("/api/uploads/{uploadId}/embedded-subtitles", "up_abc123")
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("0"))
            .andExpect(jsonPath("$.data.status").value("FOUND"))
            .andExpect(jsonPath("$.data.selectedStreamIndex").value(3))
            .andExpect(jsonPath("$.data.tracks[0].codecName").value("subrip"));
    }

    @Test
    void downloadTaskSubtitleReturnsTextVttWithoutStorageDetails() throws Exception {
        byte[] bytes = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n字幕\n".getBytes(StandardCharsets.UTF_8);
        when(embeddedSubtitleService.downloadTask(eq("Bearer access-token"), eq("task_abc123"), eq(3)))
            .thenReturn(new EmbeddedSubtitleFileResponse(bytes, "text/vtt;charset=utf-8", "embedded-subtitle-3.vtt"));

        mockMvc.perform(get("/api/tasks/{taskId}/embedded-subtitles/{streamIndex}/download", "task_abc123", 3)
                .header("Authorization", "Bearer access-token"))
            .andExpect(status().isOk())
            .andExpect(header().string("Content-Type", "text/vtt;charset=utf-8"))
            .andExpect(header().string("Content-Disposition", "inline; filename=\"embedded-subtitle-3.vtt\""))
            .andExpect(content().bytes(bytes))
            .andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("raw/42"))))
            .andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("localPath"))));
    }
}
