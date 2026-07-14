package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.artifact.service.GenerateJsonArtifactCommand;
import com.example.courselingo.artifact.service.GenerateMarkdownArtifactCommand;
import com.example.courselingo.artifact.service.GenerateSrtArtifactCommand;
import com.example.courselingo.artifact.service.GenerateVttArtifactCommand;
import com.example.courselingo.artifact.service.JsonArtifactService;
import com.example.courselingo.artifact.service.MarkdownArtifactService;
import com.example.courselingo.artifact.service.SrtArtifactService;
import com.example.courselingo.artifact.service.VttArtifactService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class GenerateArtifactsStepTest {

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private SrtArtifactService srtArtifactService;

    @Mock
    private VttArtifactService vttArtifactService;

    @Mock
    private MarkdownArtifactService markdownArtifactService;

    @Mock
    private JsonArtifactService jsonArtifactService;

    private GenerateArtifactsStep step;

    @BeforeEach
    void setUp() {
        step = new GenerateArtifactsStep(
            analysisTaskMapper,
            srtArtifactService,
            vttArtifactService,
            markdownArtifactService,
            jsonArtifactService
        );
    }

    @Test
    void generateArtifactsUsesOwnerScopedTaskAndTargetLanguage() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());

        step.execute(context(7L));

        ArgumentCaptor<GenerateSrtArtifactCommand> srtCaptor =
            ArgumentCaptor.forClass(GenerateSrtArtifactCommand.class);
        ArgumentCaptor<GenerateVttArtifactCommand> vttCaptor =
            ArgumentCaptor.forClass(GenerateVttArtifactCommand.class);
        ArgumentCaptor<GenerateMarkdownArtifactCommand> markdownCaptor =
            ArgumentCaptor.forClass(GenerateMarkdownArtifactCommand.class);
        ArgumentCaptor<GenerateJsonArtifactCommand> jsonCaptor =
            ArgumentCaptor.forClass(GenerateJsonArtifactCommand.class);

        verify(srtArtifactService).generateSrtArtifact(srtCaptor.capture());
        verify(vttArtifactService).generateVttArtifact(vttCaptor.capture());
        verify(markdownArtifactService).generateMarkdownArtifact(markdownCaptor.capture());
        verify(jsonArtifactService).generateJsonArtifact(jsonCaptor.capture());

        assertThat(srtCaptor.getValue()).isEqualTo(new GenerateSrtArtifactCommand("task_1", 7L, "zh-CN"));
        assertThat(vttCaptor.getValue()).isEqualTo(new GenerateVttArtifactCommand("task_1", 7L, "zh-CN"));
        assertThat(markdownCaptor.getValue()).isEqualTo(
            new GenerateMarkdownArtifactCommand("task_1", 7L, "zh-CN")
        );
        assertThat(jsonCaptor.getValue()).isEqualTo(new GenerateJsonArtifactCommand("task_1", 7L, "zh-CN"));
    }

    @Test
    void generateArtifactsRejectsOwnerMismatchBeforeWritingArtifacts() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 8L)).thenReturn(null);

        assertThatThrownBy(() -> step.execute(context(8L)))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(srtArtifactService, never()).generateSrtArtifact(any());
        verify(vttArtifactService, never()).generateVttArtifact(any());
        verify(markdownArtifactService, never()).generateMarkdownArtifact(any());
        verify(jsonArtifactService, never()).generateJsonArtifact(any());
    }

    private static PipelineAnalysisTaskStepContext context(Long userId) {
        return new PipelineAnalysisTaskStepContext(
            new AnalysisTaskExecutionContext("task_1", "up_1", userId, "zh-CN", "req_1")
        );
    }

    private static AnalysisTask task() {
        AnalysisTask task = new AnalysisTask();
        task.setId("task_1");
        task.setUserId(7L);
        return task;
    }
}
