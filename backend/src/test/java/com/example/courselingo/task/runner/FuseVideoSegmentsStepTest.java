package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.example.courselingo.fusion.VideoSegmentFusionResult;
import com.example.courselingo.fusion.VideoSegmentFusionService;
import com.example.courselingo.fusion.VideoSegmentProperties;
import com.example.courselingo.task.entity.TaskLog;
import com.example.courselingo.task.mapper.TaskLogMapper;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;

class FuseVideoSegmentsStepTest {

    @Test
    void skipsWhenFusionIsDisabled() {
        VideoSegmentProperties properties = new VideoSegmentProperties();
        properties.setEnabled(false);
        VideoSegmentFusionService service = (taskId, userId) -> {
            throw new AssertionError("Fusion must not run when disabled");
        };
        TaskLogMapper taskLogMapper = Mockito.mock(TaskLogMapper.class);

        new FuseVideoSegmentsStep(service, properties, taskLogMapper, clock()).execute(context());

        verify(taskLogMapper, never()).insert(Mockito.any(TaskLog.class));
    }

    @Test
    void serviceFailureWritesWarningAndDoesNotBlockPipelineByDefault() {
        VideoSegmentProperties properties = new VideoSegmentProperties();
        properties.setEnabled(true);
        properties.setFailTaskOnError(false);
        TaskLogMapper taskLogMapper = Mockito.mock(TaskLogMapper.class);
        VideoSegmentFusionService service = (taskId, userId) -> {
            throw new IllegalStateException("objectKey=internal/key C:\\Users\\demo token=abc raw response=bad");
        };

        new FuseVideoSegmentsStep(service, properties, taskLogMapper, clock()).execute(context());

        ArgumentCaptor<TaskLog> captor = ArgumentCaptor.forClass(TaskLog.class);
        verify(taskLogMapper).insert(captor.capture());
        TaskLog log = captor.getValue();
        assertThat(log.getTaskId()).isEqualTo("task_1");
        assertThat(log.getUserId()).isEqualTo(42L);
        assertThat(log.getLevel()).isEqualTo("WARN");
        assertThat(log.getStage()).isEqualTo("FUSE_VIDEO_SEGMENTS");
        assertThat(log.getMessage()).contains("Video segment fusion skipped");
        assertThat(log.getCreatedAt()).isEqualTo(LocalDateTime.of(2026, 7, 6, 10, 0));
        assertThat(log.getDetail())
            .doesNotContain("objectKey")
            .doesNotContain("internal/key")
            .doesNotContain("C:\\Users")
            .doesNotContain("demo")
            .doesNotContain("token")
            .doesNotContain("raw response")
            .doesNotContain("abc");
    }

    @Test
    void successRunsAgainstCurrentTaskScope() {
        VideoSegmentProperties properties = new VideoSegmentProperties();
        properties.setEnabled(true);
        final String[] captured = new String[2];
        VideoSegmentFusionService service = (taskId, userId) -> {
            captured[0] = taskId;
            captured[1] = String.valueOf(userId);
            return new VideoSegmentFusionResult(2, 2, 0, 0);
        };

        new FuseVideoSegmentsStep(service, properties, Mockito.mock(TaskLogMapper.class), clock()).execute(context());

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
