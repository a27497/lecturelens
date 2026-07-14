package com.example.courselingo.video.context;

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
import com.example.courselingo.video.context.controller.CourseVideoContextController;
import com.example.courselingo.video.context.dto.CourseVideoContextChunkResponse;
import com.example.courselingo.video.context.dto.CourseVideoContextEvidenceItem;
import com.example.courselingo.video.context.dto.CourseVideoContextRebuildResponse;
import com.example.courselingo.video.context.dto.CourseVideoContextResponse;
import com.example.courselingo.video.context.dto.CourseVideoContextSourceStats;
import com.example.courselingo.video.context.service.CourseVideoContextService;
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

@WebMvcTest(CourseVideoContextController.class)
@Import({GlobalExceptionHandler.class, CourseVideoContextControllerTest.TestConfig.class})
class CourseVideoContextControllerTest {

    private final MockMvc mockMvc;

    @Autowired
    private CourseVideoContextService courseVideoContextService;

    @Autowired
    CourseVideoContextControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @BeforeEach
    void resetMocks() {
        Mockito.reset(courseVideoContextService);
    }

    @TestConfiguration
    static class TestConfig {
        @Bean
        CourseVideoContextService courseVideoContextService() {
            return Mockito.mock(CourseVideoContextService.class);
        }
    }

    @Test
    void getReturnsContextWithoutSensitiveFields() throws Exception {
        when(courseVideoContextService.get("task_1", "Bearer demo")).thenReturn(contextResponse());

        mockMvc.perform(get("/api/tasks/{taskId}/video-context", "task_1").header("Authorization", "Bearer demo"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.taskId").value("task_1"))
            .andExpect(jsonPath("$.data.targetLanguage").value("zh-CN"))
            .andExpect(jsonPath("$.data.chunks[0].summary").value("语言模型基础"))
            .andExpect(jsonPath("$.data.chunks[0].evidence[0].sourceType").value("SUBTITLE"))
            .andExpect(content().string(not(containsString("userId"))))
            .andExpect(content().string(not(containsString("object" + "Key"))))
            .andExpect(content().string(not(containsString("raw" + "Prompt"))))
            .andExpect(content().string(not(containsString("raw" + "Response"))))
            .andExpect(content().string(not(containsString("token"))));

        verify(courseVideoContextService).get("task_1", "Bearer demo");
    }

    @Test
    void rebuildReturnsSummaryAndMapsTaskNotFound() throws Exception {
        when(courseVideoContextService.rebuild("task_1", "Bearer demo"))
            .thenReturn(new CourseVideoContextRebuildResponse(
                "task_1",
                "zh-CN",
                1,
                "VIDEO_CONTEXT_R1",
                LocalDateTime.parse("2026-07-09T00:00:00")
            ));

        mockMvc.perform(post("/api/tasks/{taskId}/video-context/rebuild", "task_1").header("Authorization", "Bearer demo"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.chunkCount").value(1))
            .andExpect(jsonPath("$.data.buildVersion").value("VIDEO_CONTEXT_R1"));

        doThrow(new BusinessException(ErrorCode.TASK_NOT_FOUND))
            .when(courseVideoContextService)
            .rebuild("task_missing", "Bearer demo");

        mockMvc.perform(post("/api/tasks/{taskId}/video-context/rebuild", "task_missing").header("Authorization", "Bearer demo"))
            .andExpect(status().isNotFound())
            .andExpect(content().string(containsString(ErrorCode.TASK_NOT_FOUND.code())));
    }

    private static CourseVideoContextResponse contextResponse() {
        return new CourseVideoContextResponse(
            "task_1",
            "zh-CN",
            240000L,
            240,
            "VIDEO_CONTEXT_R1",
            new CourseVideoContextSourceStats(1, 1, 0, 1, true, true, LocalDateTime.parse("2026-07-09T00:00:00")),
            "全局总结",
            List.of("语言模型"),
            List.of(),
            List.of(new CourseVideoContextChunkResponse(
                0,
                0L,
                240000L,
                "00:00:00 - 00:04:00",
                "语言模型基础",
                List.of("语言模型"),
                "source preview",
                "translated preview",
                List.of(new CourseVideoContextEvidenceItem("SUBTITLE", 0, 0L, 60000L, "00:00:00 - 00:01:00", "source", "translated"))
            ))
        );
    }
}
