package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.progress.TaskProgressSnapshot;
import com.example.courselingo.task.progress.TaskProgressSnapshotService;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;

class PipelineAnalysisTaskWorkExecutorTest {

    @Test
    void executesConfiguredFakeStepsInOrder() {
        List<PipelineAnalysisTaskStepName> executed = new ArrayList<>();
        List<PipelineAnalysisTaskStep> steps = PipelineAnalysisTaskStepName.ordered().stream()
            .map(name -> (PipelineAnalysisTaskStep) new RecordingStep(name, executed))
            .toList();

        AnalysisTaskWorkResult result = new PipelineAnalysisTaskWorkExecutor(steps).execute(context());

        assertThat(result.success()).isTrue();
        assertThat(result.errorCode()).isNull();
        assertThat(result.errorMessage()).isNull();
        assertThat(executed).containsExactlyElementsOf(PipelineAnalysisTaskStepName.ordered());
    }

    @Test
    void reportsEachStepStartAndCompletionForProgressSnapshots() {
        List<PipelineAnalysisTaskStepName> executed = new ArrayList<>();
        List<PipelineAnalysisTaskStep> steps = PipelineAnalysisTaskStepName.ordered().stream()
            .map(name -> (PipelineAnalysisTaskStep) new RecordingStep(name, executed))
            .toList();
        RecordingPipelineTaskProgressReporter reporter = new RecordingPipelineTaskProgressReporter();

        new PipelineAnalysisTaskWorkExecutor(steps, reporter).execute(context());

        List<String> expected = new ArrayList<>();
        PipelineAnalysisTaskStepName.ordered().forEach(name -> {
            expected.add("started:" + name.name());
            expected.add("completed:" + name.name());
        });
        assertThat(reporter.events).containsExactlyElementsOf(expected);
    }

    @Test
    void defaultProgressReporterUpdatesMysqlAndSnapshotWhenStepStarts() {
        AnalysisTaskMapper taskMapper = mock(AnalysisTaskMapper.class);
        TaskProgressSnapshotService snapshotService = mock(TaskProgressSnapshotService.class);
        DefaultPipelineTaskProgressReporter reporter = new DefaultPipelineTaskProgressReporter(
            taskMapper,
            snapshotService,
            Clock.fixed(Instant.parse("2026-07-03T12:00:00Z"), ZoneOffset.UTC)
        );
        when(taskMapper.updateRunningProgressByIdAndUserId("task_1", 7L, 88, "GENERATE_ARTIFACTS"))
            .thenReturn(1);

        reporter.stepStarted(PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS, new PipelineAnalysisTaskStepContext(context()));

        InOrder order = inOrder(taskMapper, snapshotService);
        order.verify(taskMapper).updateRunningProgressByIdAndUserId("task_1", 7L, 88, "GENERATE_ARTIFACTS");
        order.verify(snapshotService).save(any(TaskProgressSnapshot.class));
    }

    @Test
    void defaultProgressReporterSkipsSnapshotWhenMysqlUpdatesNoRows() {
        AnalysisTaskMapper taskMapper = mock(AnalysisTaskMapper.class);
        TaskProgressSnapshotService snapshotService = mock(TaskProgressSnapshotService.class);
        DefaultPipelineTaskProgressReporter reporter = defaultReporter(taskMapper, snapshotService);
        when(taskMapper.updateRunningProgressByIdAndUserId("task_1", 7L, 88, "GENERATE_ARTIFACTS"))
            .thenReturn(0);

        assertThatCode(() -> reporter.stepStarted(
            PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS,
            new PipelineAnalysisTaskStepContext(context())
        )).doesNotThrowAnyException();

        verify(snapshotService, never()).save(any(TaskProgressSnapshot.class));
    }

    @Test
    void defaultProgressReporterSkipsSnapshotWhenMysqlUpdatesUnexpectedRows() {
        AnalysisTaskMapper taskMapper = mock(AnalysisTaskMapper.class);
        TaskProgressSnapshotService snapshotService = mock(TaskProgressSnapshotService.class);
        DefaultPipelineTaskProgressReporter reporter = defaultReporter(taskMapper, snapshotService);
        when(taskMapper.updateRunningProgressByIdAndUserId("task_1", 7L, 88, "GENERATE_ARTIFACTS"))
            .thenReturn(2);

        assertThatCode(() -> reporter.stepStarted(
            PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS,
            new PipelineAnalysisTaskStepContext(context())
        )).doesNotThrowAnyException();

        verify(snapshotService, never()).save(any(TaskProgressSnapshot.class));
    }

    @Test
    void defaultProgressReporterKeepsMysqlFailureNonFatalAndSkipsSnapshot() {
        AnalysisTaskMapper taskMapper = mock(AnalysisTaskMapper.class);
        TaskProgressSnapshotService snapshotService = mock(TaskProgressSnapshotService.class);
        DefaultPipelineTaskProgressReporter reporter = defaultReporter(taskMapper, snapshotService);
        doThrow(new IllegalStateException("fixture database unavailable"))
            .when(taskMapper)
            .updateRunningProgressByIdAndUserId("task_1", 7L, 88, "GENERATE_ARTIFACTS");

        assertThatCode(() -> reporter.stepStarted(
            PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS,
            new PipelineAnalysisTaskStepContext(context())
        )).doesNotThrowAnyException();

        verify(snapshotService, never()).save(any(TaskProgressSnapshot.class));
    }

    @Test
    void defaultSkeletonStepsAreNoopAndKeepEveryBoundaryExplicit() {
        PipelineAnalysisTaskWorkExecutor executor = PipelineAnalysisTaskWorkExecutor.skeleton();

        AnalysisTaskWorkResult result = executor.execute(context());

        assertThat(result.success()).isTrue();
        assertThat(executor.stepNames()).containsExactlyElementsOf(PipelineAnalysisTaskStepName.ordered());
    }

    @Test
    void stepFailureIsWrappedWithSanitizedMessage() {
        List<PipelineAnalysisTaskStep> steps = PipelineAnalysisTaskStepName.ordered().stream()
            .map(name -> (PipelineAnalysisTaskStep) new FailingStep(name))
            .toList();

        assertThatThrownBy(() -> new PipelineAnalysisTaskWorkExecutor(steps).execute(context()))
            .isInstanceOf(PipelineAnalysisTaskStepException.class)
            .hasMessageContaining("TRANSCRIBE")
            .satisfies(error -> assertSafe(error.getMessage()));
    }

    @Test
    void pipelineDoesNotReferenceAsrLlmMqOrSecretIntegrations() throws IOException {
        String source = readRunnerSources();

        assertThat(source)
            .doesNotContain("SpeechToTextProvider")
            .doesNotContain("LlmProvider")
            .doesNotContain("SiliconFlow")
            .doesNotContain("OpenAi")
            .doesNotContain("LangChain4j")
            .doesNotContain("RocketMq")
            .doesNotContain("RocketMQ")
            .doesNotContain("MessageSender")
            .doesNotContain("apiKey")
            .doesNotContain("Authorization");
    }

    private static AnalysisTaskExecutionContext context() {
        return new AnalysisTaskExecutionContext("task_1", "up_1", 7L, "zh-CN", "req_1");
    }

    private static DefaultPipelineTaskProgressReporter defaultReporter(
        AnalysisTaskMapper taskMapper,
        TaskProgressSnapshotService snapshotService
    ) {
        return new DefaultPipelineTaskProgressReporter(
            taskMapper,
            snapshotService,
            Clock.fixed(Instant.parse("2026-07-03T12:00:00Z"), ZoneOffset.UTC)
        );
    }

    private static void assertSafe(String value) {
        assertThat(value).doesNotContainIgnoringCase("token");
        assertThat(value).doesNotContainIgnoringCase("secret");
        assertThat(value).doesNotContainIgnoringCase("api key");
        assertThat(value).doesNotContainIgnoringCase("objectKey");
        assertThat(value).doesNotContain("C:\\Users");
    }

    private static String readRunnerSources() throws IOException {
        Path runnerDir = Path.of("src/main/java/com/example/courselingo/task/runner");
        StringBuilder source = new StringBuilder();
        try (var paths = Files.walk(runnerDir)) {
            for (Path path : paths
                .filter(path -> path.getFileName().toString().startsWith("Pipeline"))
                .filter(path -> path.toString().endsWith(".java"))
                .toList()) {
                source.append(Files.readString(path)).append('\n');
            }
        }
        return source.toString();
    }

    private record FailingStep(PipelineAnalysisTaskStepName name) implements PipelineAnalysisTaskStep {

        @Override
        public void execute(PipelineAnalysisTaskStepContext context) {
            if (name == PipelineAnalysisTaskStepName.TRANSCRIBE) {
                throw new IllegalStateException(
                    "token=raw secret=raw api key=raw objectKey=raw Authorization: Bearer raw "
                        + "C:\\Users\\demo\\video.mp4"
                );
            }
        }
    }

    private record RecordingStep(
        PipelineAnalysisTaskStepName name,
        List<PipelineAnalysisTaskStepName> executed
    ) implements PipelineAnalysisTaskStep {

        @Override
        public void execute(PipelineAnalysisTaskStepContext context) {
            executed.add(name);
        }
    }

    private static final class RecordingPipelineTaskProgressReporter implements PipelineTaskProgressReporter {
        private final List<String> events = new ArrayList<>();

        @Override
        public void stepStarted(PipelineAnalysisTaskStepName stepName, PipelineAnalysisTaskStepContext context) {
            events.add("started:" + stepName.name());
        }

        @Override
        public void stepCompleted(
            PipelineAnalysisTaskStepName stepName,
            PipelineAnalysisTaskStepContext context,
            long durationMillis
        ) {
            events.add("completed:" + stepName.name());
        }
    }
}
