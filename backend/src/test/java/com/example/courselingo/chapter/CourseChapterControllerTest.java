package com.example.courselingo.chapter;

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

import com.example.courselingo.chapter.controller.CourseChapterController;
import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import com.example.courselingo.chapter.dto.CourseChapterResponse;
import com.example.courselingo.chapter.dto.CourseChapterUsage;
import com.example.courselingo.chapter.service.CourseChapterService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
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

@WebMvcTest(CourseChapterController.class)
@Import({GlobalExceptionHandler.class, CourseChapterControllerTest.TestConfig.class})
class CourseChapterControllerTest {

    private final MockMvc mockMvc;

    @Autowired
    private CourseChapterService courseChapterService;

    @Autowired
    CourseChapterControllerTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @BeforeEach
    void resetMocks() {
        Mockito.reset(courseChapterService);
    }

    @TestConfiguration
    static class TestConfig {
        @Bean
        CourseChapterService courseChapterService() {
            return Mockito.mock(CourseChapterService.class);
        }
    }

    @Test
    void listReturnsChaptersWithoutSensitiveFields() throws Exception {
        when(courseChapterService.list("task_1", "Bearer demo")).thenReturn(chapters());

        mockMvc.perform(get("/api/tasks/{taskId}/chapters", "task_1").header("Authorization", "Bearer demo"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data[0].title").value("什么是大语言模型"))
            .andExpect(jsonPath("$.data[0].startTimeMillis").value(0))
            .andExpect(jsonPath("$.data[0].keywords[0]").value("语言模型"))
            .andExpect(content().string(not(containsString("object" + "Key"))))
            .andExpect(content().string(not(containsString("raw" + "Prompt"))))
            .andExpect(content().string(not(containsString("raw" + "Response"))))
            .andExpect(content().string(not(containsString("token"))));

        verify(courseChapterService).list("task_1", "Bearer demo");
    }

    @Test
    void generateReturnsChaptersAndMapsTaskNotFound() throws Exception {
        when(courseChapterService.generate("task_1", "Bearer demo")).thenReturn(chapters());

        mockMvc.perform(post("/api/tasks/{taskId}/chapters/generate", "task_1").header("Authorization", "Bearer demo"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data[0].title").value("什么是大语言模型"));

        doThrow(new BusinessException(ErrorCode.TASK_NOT_FOUND))
            .when(courseChapterService)
            .generate("task_missing", "Bearer demo");

        mockMvc.perform(post("/api/tasks/{taskId}/chapters/generate", "task_missing").header("Authorization", "Bearer demo"))
            .andExpect(status().isNotFound())
            .andExpect(content().string(containsString(ErrorCode.TASK_NOT_FOUND.code())));
    }

    private static List<CourseChapterResponse> chapters() {
        return List.of(new CourseChapterResponse(
            1L,
            0,
            "什么是大语言模型",
            "本章介绍基本概念。",
            List.of("语言模型"),
            0L,
            240000L,
            "00:00:00 - 00:04:00",
            List.of(new CourseChapterEvidenceItem(0, 0L, 240000L, "00:00:00 - 00:04:00", "本段语音原文：Intro")),
            new CourseChapterUsage("openai-compatible", "chapter-model", 10, 20, 30, 1000L)
        ));
    }
}
