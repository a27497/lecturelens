package com.example.courselingo.artifact;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.eq;
import static org.mockito.Mockito.isNull;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.artifact.controller.ArtifactFileDownloadController;
import com.example.courselingo.artifact.service.ArtifactFileDownloadResponse;
import com.example.courselingo.artifact.service.ArtifactFileDownloadService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ArtifactFileDownloadController.class)
@Import({GlobalExceptionHandler.class, ArtifactFileDownloadControllerTest.TestConfig.class})
class ArtifactFileDownloadControllerTest {

    private static final String AUTHORIZATION = "test-authorization";
    private static final String TASK_ID = "task_fixture";
    private static final String VTT_CONTENT = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n你好\n";

    private final MockMvc mockMvc;

    @Autowired
    private ArtifactFileDownloadService artifactFileDownloadService;

    @Autowired
    ArtifactFileDownloadControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @BeforeEach
    void resetMocks() {
        Mockito.reset(artifactFileDownloadService);
    }

    @TestConfiguration
    static class TestConfig {

        @Bean
        ArtifactFileDownloadService artifactFileDownloadService() {
            return Mockito.mock(ArtifactFileDownloadService.class);
        }
    }

    @Test
    void downloadReturnsTextVttWithoutLeakingStorageDetails() throws Exception {
        byte[] bytes = VTT_CONTENT.getBytes(StandardCharsets.UTF_8);
        when(artifactFileDownloadService.download(
            eq(AUTHORIZATION),
            eq(TASK_ID),
            eq("VTT"),
            eq("zh-CN")
        )).thenReturn(new ArtifactFileDownloadResponse(
            "fixture.vtt",
            "text/vtt; charset=utf-8",
            bytes.length,
            new ByteArrayInputStream(bytes)
        ));

        mockMvc.perform(get("/api/tasks/{taskId}/artifacts/{artifactType}/{language}/download", TASK_ID, "VTT", "zh-CN")
                .header("Authorization", AUTHORIZATION)
                .param("objectKey", "fixture-forged-object-key"))
            .andExpect(status().isOk())
            .andExpect(header().string("Content-Type", containsString("text/vtt")))
            .andExpect(header().string("Content-Disposition", containsString("inline")))
            .andExpect(header().longValue("Content-Length", bytes.length))
            .andExpect(content().string(VTT_CONTENT))
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("fixture-forged-object-key"))));
    }

    @Test
    void downloadReturnsSanitizedNotFoundWhenTaskGuardRejectsTask() throws Exception {
        doThrow(new BusinessException(ErrorCode.TASK_NOT_FOUND))
            .when(artifactFileDownloadService)
            .download(eq(AUTHORIZATION), eq(TASK_ID), eq("VTT"), eq("zh-CN"));

        mockMvc.perform(get("/api/tasks/{taskId}/artifacts/{artifactType}/{language}/download", TASK_ID, "VTT", "zh-CN")
                .header("Authorization", AUTHORIZATION)
                .param("objectKey", "fixture-forged-object-key"))
            .andExpect(status().isNotFound())
            .andExpect(content().string(containsString(ErrorCode.TASK_NOT_FOUND.code())))
            .andExpect(content().string(not(containsString("objectKey"))))
            .andExpect(content().string(not(containsString("localPath"))))
            .andExpect(content().string(not(containsString("MINIO"))))
            .andExpect(content().string(not(containsString("fixture-forged-object-key"))));
    }

    @Test
    void downloadRequiresAuthorization() throws Exception {
        doThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED))
            .when(artifactFileDownloadService).download(isNull(), eq(TASK_ID), eq("VTT"), eq("zh-CN"));

        mockMvc.perform(get("/api/tasks/{taskId}/artifacts/{artifactType}/{language}/download", TASK_ID, "VTT", "zh-CN"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string(containsString(ErrorCode.COMMON_UNAUTHORIZED.code())));
    }
}
