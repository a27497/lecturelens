package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.example.courselingo.task.entity.TaskLog;
import com.example.courselingo.task.mapper.TaskLogMapper;
import com.example.courselingo.vision.analysis.VisionAnalysisProperties;
import com.example.courselingo.vision.analysis.VisionAnalysisScanResult;
import com.example.courselingo.vision.analysis.VisionAnalysisService;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;

class AnalyzeKeyframesStepTest {

    @Test
    void skipsWhenVisionAnalysisIsDisabled() {
        VisionAnalysisProperties properties = new VisionAnalysisProperties();
        properties.setEnabled(false);
        VisionAnalysisService service = (taskId, userId) -> {
            throw new AssertionError("VLM must not run when disabled");
        };
        TaskLogMapper taskLogMapper = Mockito.mock(TaskLogMapper.class);

        new AnalyzeKeyframesStep(service, properties, taskLogMapper, clock()).execute(context());

        verify(taskLogMapper, never()).insert(Mockito.any(TaskLog.class));
    }

    @Test
    void serviceFailureWritesSanitizedWarningAndDoesNotBlockPipeline() {
        VisionAnalysisProperties properties = new VisionAnalysisProperties();
        properties.setEnabled(true);
        TaskLogMapper taskLogMapper = Mockito.mock(TaskLogMapper.class);
        VisionAnalysisService service = (taskId, userId) -> {
            throw new IllegalStateException(
                "failed objectKey=keyframes/42/task_1/frame.jpg C:\\Users\\demo\\private token=abc raw response=bad"
            );
        };

        new AnalyzeKeyframesStep(service, properties, taskLogMapper, clock()).execute(context());

        ArgumentCaptor<TaskLog> captor = ArgumentCaptor.forClass(TaskLog.class);
        verify(taskLogMapper).insert(captor.capture());
        TaskLog log = captor.getValue();
        assertThat(log.getTaskId()).isEqualTo("task_1");
        assertThat(log.getUserId()).isEqualTo(42L);
        assertThat(log.getLevel()).isEqualTo("WARN");
        assertThat(log.getStage()).isEqualTo("ANALYZE_KEYFRAMES");
        assertThat(log.getMessage()).contains("Keyframe visual analysis skipped");
        assertThat(log.getCreatedAt()).isEqualTo(LocalDateTime.of(2026, 7, 6, 10, 0));
        assertThat(log.getDetail())
            .doesNotContain("objectKey")
            .doesNotContain("keyframes/42")
            .doesNotContain("C:\\Users")
            .doesNotContain("demo")
            .doesNotContain("token")
            .doesNotContain("raw response")
            .doesNotContain("abc");
    }

    @Test
    void successRunsAgainstCurrentTaskScope() {
        VisionAnalysisProperties properties = new VisionAnalysisProperties();
        properties.setEnabled(true);
        final String[] captured = new String[2];
        VisionAnalysisService service = (taskId, userId) -> {
            captured[0] = taskId;
            captured[1] = String.valueOf(userId);
            return new VisionAnalysisScanResult(1, 1, 0, 0, 0);
        };

        new AnalyzeKeyframesStep(service, properties, Mockito.mock(TaskLogMapper.class), clock()).execute(context());

        assertThat(captured).containsExactly("task_1", "42");
    }

    private static Clock clock() {
        return Clock.fixed(Instant.parse("2026-07-06T10:00:00Z"), ZoneOffset.UTC);
    }

    private static PipelineAnalysisTaskStepContext context() {
        return new PipelineAnalysisTaskStepContext(
            new AnalysisTaskExecutionContext("task_1", "up_1", 42L, "zh-CN", "req_1"),
            PipelineAnalysisTaskStepName.ordered()
        );
    }
}
