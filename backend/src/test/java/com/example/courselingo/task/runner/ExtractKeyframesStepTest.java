package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.example.courselingo.task.entity.TaskLog;
import com.example.courselingo.task.mapper.TaskLogMapper;
import com.example.courselingo.vision.keyframe.VideoKeyframeProperties;
import com.example.courselingo.vision.keyframe.VideoKeyframeScanCommand;
import com.example.courselingo.vision.keyframe.VideoKeyframeScanResult;
import com.example.courselingo.vision.keyframe.VideoKeyframeScanService;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;

class ExtractKeyframesStepTest {

    @TempDir
    private Path tempDir;

    @Test
    void skipsWhenKeyframeScanningIsDisabled() throws Exception {
        VideoKeyframeProperties properties = new VideoKeyframeProperties();
        properties.setEnabled(false);
        VideoKeyframeScanService service = command -> {
            throw new AssertionError("keyframe scan must not run when disabled");
        };
        TaskLogMapper taskLogMapper = Mockito.mock(TaskLogMapper.class);

        new ExtractKeyframesStep(service, workspace(), properties, taskLogMapper, clock())
            .execute(contextWithSource(source()));

        verify(taskLogMapper, never()).insert(Mockito.any(TaskLog.class));
    }

    @Test
    void scansResolvedSourceAndDoesNotStorePathsInContextString() throws Exception {
        VideoKeyframeProperties properties = new VideoKeyframeProperties();
        AtomicReference<VideoKeyframeScanCommand> captured = new AtomicReference<>();
        VideoKeyframeScanService service = command -> {
            captured.set(command);
            return new VideoKeyframeScanResult(2);
        };
        PipelineAnalysisTaskStepContext context = contextWithSource(source());

        new ExtractKeyframesStep(service, workspace(), properties, Mockito.mock(TaskLogMapper.class), clock())
            .execute(context);

        assertThat(captured.get()).isNotNull();
        assertThat(captured.get().sourceVideo()).isEqualTo(context.requireUploadedSourcePath());
        assertThat(captured.get().outputDirectory())
            .startsWith(tempDir.resolve("runner").toAbsolutePath().normalize());
        assertThat(context.toString()).doesNotContain(captured.get().outputDirectory().toString());
    }

    @Test
    void scanFailureWritesSanitizedWarningAndDoesNotBlockPipeline() throws Exception {
        VideoKeyframeProperties properties = new VideoKeyframeProperties();
        TaskLogMapper taskLogMapper = Mockito.mock(TaskLogMapper.class);
        VideoKeyframeScanService service = command -> {
            throw new IllegalStateException(
                "failed objectKey=keyframes/42/task_1/frame.jpg C:\\Users\\demo\\private token=abc"
            );
        };

        new ExtractKeyframesStep(service, workspace(), properties, taskLogMapper, clock())
            .execute(contextWithSource(source()));

        ArgumentCaptor<TaskLog> captor = ArgumentCaptor.forClass(TaskLog.class);
        verify(taskLogMapper).insert(captor.capture());
        TaskLog log = captor.getValue();
        assertThat(log.getTaskId()).isEqualTo("task_1");
        assertThat(log.getUserId()).isEqualTo(42L);
        assertThat(log.getLevel()).isEqualTo("WARN");
        assertThat(log.getStage()).isEqualTo("EXTRACT_KEYFRAMES");
        assertThat(log.getMessage()).contains("Keyframe scan skipped");
        assertThat(log.getDetail())
            .doesNotContain("objectKey")
            .doesNotContain("keyframes/42")
            .doesNotContain("C:\\Users")
            .doesNotContain("demo")
            .doesNotContain("token")
            .doesNotContain("abc");
    }

    private PipelineRunnerWorkspace workspace() {
        return new PipelineRunnerWorkspace(new AnalysisTaskRunnerProperties(tempDir.resolve("runner")));
    }

    private Path source() throws Exception {
        return Files.writeString(tempDir.resolve("source.mp4"), "video", StandardCharsets.UTF_8);
    }

    private static Clock clock() {
        return Clock.fixed(Instant.parse("2026-07-06T10:00:00Z"), ZoneOffset.UTC);
    }

    private static PipelineAnalysisTaskStepContext contextWithSource(Path source) {
        PipelineAnalysisTaskStepContext context = new PipelineAnalysisTaskStepContext(
            new AnalysisTaskExecutionContext("task_1", "up_1", 42L, "zh-CN", "req_1"),
            List.of(PipelineAnalysisTaskStepName.RESOLVE_UPLOADED_SOURCE)
        );
        context.setUploadedSourcePath(source);
        return context;
    }
}
