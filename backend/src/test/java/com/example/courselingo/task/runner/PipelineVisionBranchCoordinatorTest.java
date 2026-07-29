package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.example.courselingo.ai.asr.SpeechToTextResult;
import com.example.courselingo.ai.asr.TranscribedSegment;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.entity.TaskLog;
import com.example.courselingo.task.mapper.TaskLogMapper;
import com.example.courselingo.vision.keyframe.VideoKeyframeProperties;
import com.example.courselingo.vision.keyframe.VideoKeyframeScanResult;
import com.example.courselingo.vision.ocr.VideoKeyframeOcrScanService;
import com.example.courselingo.vision.ocr.VisionOcrProperties;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class PipelineVisionBranchCoordinatorTest {

    @TempDir
    private Path tempDir;

    @Test
    void asrAndVisionPreprocessingOverlapAndAdaptiveOcrDoesNotRunLegacyScan() throws Exception {
        try (VisionPipelineBranchCoordinator coordinator = new VisionPipelineBranchCoordinator(1, 2)) {
            CountDownLatch visionStarted = new CountDownLatch(1);
            CountDownLatch releaseVision = new CountDownLatch(1);
            VideoKeyframeOcrScanService legacyOcr = mock(VideoKeyframeOcrScanService.class);
            PipelineRunnerWorkspace workspace = workspace();
            ExtractKeyframesStep extract = new ExtractKeyframesStep(command -> {
                visionStarted.countDown();
                try {
                    assertThat(releaseVision.await(2, TimeUnit.SECONDS)).isTrue();
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("vision fixture interrupted", exception);
                }
                return new VideoKeyframeScanResult(1);
            }, workspace, new VideoKeyframeProperties(), mock(TaskLogMapper.class), Clock.systemUTC(), coordinator);

            AnalysisTaskWorkResult result = executor(workspace, name -> switch (name) {
                case RESOLVE_UPLOADED_SOURCE -> sourceStep();
                case EXTRACT_KEYFRAMES -> extract;
                case TRANSCRIBE -> step(name, context -> {
                    assertThat(visionStarted.await(2, TimeUnit.SECONDS)).isTrue();
                    releaseVision.countDown();
                    context.setSpeechToTextResult(asrResult());
                });
                case OCR_KEYFRAMES -> new OcrKeyframesStep(
                    legacyOcr,
                    new VisionOcrProperties(),
                    mock(TaskLogMapper.class),
                    Clock.systemUTC()
                );
                default -> new NoopPipelineAnalysisTaskStep(name);
            }).execute(taskContext());

            assertThat(result.success()).isTrue();
            assertThat(result.errorCode()).isNull();
            verify(legacyOcr, never()).scan("task_1", 7L);
        }
    }

    @Test
    void deadlineCancelsFutureAndWaitsForBranchExit() throws Exception {
        try (VisionPipelineBranchCoordinator coordinator = new VisionPipelineBranchCoordinator(1, 1)) {
            CountDownLatch started = new CountDownLatch(1);
            AtomicBoolean interrupted = new AtomicBoolean(false);
            var handle = coordinator.submit(() -> {
                started.countDown();
                try {
                    Thread.sleep(10_000L);
                } catch (InterruptedException exception) {
                    interrupted.set(true);
                    Thread.currentThread().interrupt();
                }
                return null;
            }, Duration.ofMillis(50));

            assertThat(started.await(1, TimeUnit.SECONDS)).isTrue();
            VisionPipelineBranchResult result = handle.await();

            assertThat(result.status()).isEqualTo(VisionPipelineBranchResult.Status.TIMED_OUT);
            assertThat(interrupted).isTrue();
        }
    }

    @Test
    void visualFailureDegradesToAsrOnlyAndWritesSafeWarning() {
        try (VisionPipelineBranchCoordinator coordinator = new VisionPipelineBranchCoordinator(1, 1)) {
            TaskLogMapper logs = mock(TaskLogMapper.class);
            PipelineRunnerWorkspace workspace = workspace();
            AnalysisTaskWorkResult result = executor(workspace, name -> switch (name) {
                case RESOLVE_UPLOADED_SOURCE -> sourceStep();
                case EXTRACT_KEYFRAMES -> new ExtractKeyframesStep(command -> {
                    throw new IllegalStateException("token=secret C:\\Users\\private\\frame.png");
                }, workspace, new VideoKeyframeProperties(), logs, Clock.systemUTC(), coordinator);
                case TRANSCRIBE -> step(name, context -> context.setSpeechToTextResult(asrResult()));
                case OCR_KEYFRAMES -> new OcrKeyframesStep(
                    mock(VideoKeyframeOcrScanService.class),
                    new VisionOcrProperties(),
                    logs,
                    Clock.systemUTC()
                );
                default -> new NoopPipelineAnalysisTaskStep(name);
            }).execute(taskContext());

            assertThat(result.success()).isTrue();
            assertThat(result.errorCode()).isEqualTo(AnalysisTaskWorkResult.DEGRADED_ASR_ONLY);
            var captor = org.mockito.ArgumentCaptor.forClass(TaskLog.class);
            verify(logs).insert(captor.capture());
            assertThat(captor.getValue().getDetail())
                .doesNotContainIgnoringCase("token")
                .doesNotContain("secret")
                .doesNotContain("C:\\Users");
        }
    }

    @Test
    void asrFailureUsesVisualOnlyResultWithoutFabricatingSubtitles() {
        try (VisionPipelineBranchCoordinator coordinator = new VisionPipelineBranchCoordinator(1, 1)) {
            PipelineRunnerWorkspace workspace = workspace();
            AtomicBoolean persisted = new AtomicBoolean(false);
            AtomicBoolean translated = new AtomicBoolean(false);
            AnalysisTaskWorkResult result = executor(workspace, name -> switch (name) {
                case RESOLVE_UPLOADED_SOURCE -> sourceStep();
                case EXTRACT_KEYFRAMES -> successfulExtract(workspace, coordinator);
                case TRANSCRIBE -> step(name, context -> {
                    throw new IllegalStateException("ASR unavailable");
                });
                case PERSIST_SUBTITLES -> step(name, context -> persisted.set(true));
                case TRANSLATE_SUBTITLES -> step(name, context -> translated.set(true));
                case OCR_KEYFRAMES -> adaptiveJoinStep();
                default -> new NoopPipelineAnalysisTaskStep(name);
            }).execute(taskContext());

            assertThat(result.success()).isTrue();
            assertThat(result.errorCode()).isEqualTo(AnalysisTaskWorkResult.DEGRADED_VISUAL_ONLY);
            assertThat(persisted).isTrue();
            assertThat(translated).isTrue();
        }
    }

    @Test
    void bothBranchFailuresFailThePipeline() {
        try (VisionPipelineBranchCoordinator coordinator = new VisionPipelineBranchCoordinator(1, 1)) {
            PipelineRunnerWorkspace workspace = workspace();
            PipelineAnalysisTaskWorkExecutor executor = executor(workspace, name -> switch (name) {
                case RESOLVE_UPLOADED_SOURCE -> sourceStep();
                case EXTRACT_KEYFRAMES -> new ExtractKeyframesStep(command -> {
                    throw new IllegalStateException("vision unavailable");
                }, workspace, new VideoKeyframeProperties(), null, Clock.systemUTC(), coordinator);
                case TRANSCRIBE -> step(name, context -> {
                    throw new IllegalStateException("ASR unavailable");
                });
                case OCR_KEYFRAMES -> adaptiveJoinStep();
                default -> new NoopPipelineAnalysisTaskStep(name);
            });

            assertThatThrownBy(() -> executor.execute(taskContext()))
                .isInstanceOf(PipelineAnalysisTaskStepException.class)
                .hasMessageContaining("OCR_KEYFRAMES");
        }
    }

    @Test
    void cancellationWaitsForVisionExitBeforeWorkspaceCleanup() throws Exception {
        try (VisionPipelineBranchCoordinator coordinator = new VisionPipelineBranchCoordinator(1, 1)) {
            PipelineRunnerWorkspace workspace = workspace();
            Path keyframeDirectory = workspace.keyframeOutputDirectory(new PipelineAnalysisTaskStepContext(taskContext()));
            CountDownLatch visionStarted = new CountDownLatch(1);
            AtomicBoolean workspaceExistedAtBranchExit = new AtomicBoolean(false);
            PipelineAnalysisTaskWorkExecutor executor = executor(workspace, name -> switch (name) {
                case RESOLVE_UPLOADED_SOURCE -> sourceStep();
                case EXTRACT_KEYFRAMES -> new ExtractKeyframesStep(command -> {
                    visionStarted.countDown();
                    try {
                        Thread.sleep(10_000L);
                    } catch (InterruptedException exception) {
                        workspaceExistedAtBranchExit.set(Files.exists(command.outputDirectory()));
                        Thread.currentThread().interrupt();
                    }
                    return new VideoKeyframeScanResult(0);
                }, workspace, new VideoKeyframeProperties(), null, Clock.systemUTC(), coordinator);
                case EXTRACT_AUDIO -> step(name, context -> {
                    assertThat(visionStarted.await(2, TimeUnit.SECONDS)).isTrue();
                    throw new BusinessException(ErrorCode.TASK_INVALID_STATUS, "task cancelled");
                });
                default -> new NoopPipelineAnalysisTaskStep(name);
            });

            assertThatThrownBy(() -> executor.execute(taskContext()))
                .isInstanceOf(PipelineAnalysisTaskStepException.class);
            assertThat(workspaceExistedAtBranchExit).isTrue();
            assertThat(keyframeDirectory).doesNotExist();
            assertThat(keyframeDirectory.getParent()).doesNotExist();
            assertThat(keyframeDirectory.getParent().getParent()).doesNotExist();
            assertThat(keyframeDirectory.getParent().getParent().getParent()).doesNotExist();
        }
    }

    @Test
    void branchStatusesUseExplicitStateTransitions() {
        PipelineAnalysisTaskStepContext context = new PipelineAnalysisTaskStepContext(taskContext());

        assertThat(context.asrBranchStatus()).isEqualTo(PipelineBranchStatus.NOT_STARTED);
        assertThat(context.visionBranchStatus()).isEqualTo(PipelineBranchStatus.NOT_STARTED);

        context.markAsrBranchRunning();
        context.markAsrBranchSucceeded();
        context.setVisionBranchResult(VisionPipelineBranchResult.succeeded());
        context.markVisionBranchDegraded();

        assertThat(context.asrBranchStatus()).isEqualTo(PipelineBranchStatus.SUCCEEDED);
        assertThat(context.visionBranchStatus()).isEqualTo(PipelineBranchStatus.DEGRADED);
    }

    private ExtractKeyframesStep successfulExtract(
        PipelineRunnerWorkspace workspace,
        VisionPipelineBranchCoordinator coordinator
    ) {
        return new ExtractKeyframesStep(
            command -> new VideoKeyframeScanResult(1),
            workspace,
            new VideoKeyframeProperties(),
            null,
            Clock.systemUTC(),
            coordinator
        );
    }

    private OcrKeyframesStep adaptiveJoinStep() {
        return new OcrKeyframesStep(
            mock(VideoKeyframeOcrScanService.class),
            new VisionOcrProperties(),
            mock(TaskLogMapper.class),
            Clock.systemUTC()
        );
    }

    private PipelineAnalysisTaskWorkExecutor executor(
        PipelineRunnerWorkspace workspace,
        java.util.function.Function<PipelineAnalysisTaskStepName, PipelineAnalysisTaskStep> factory
    ) {
        List<PipelineAnalysisTaskStep> steps = PipelineAnalysisTaskStepName.ordered().stream()
            .map(factory)
            .toList();
        return new PipelineAnalysisTaskWorkExecutor(steps, PipelineTaskProgressReporter.NOOP, workspace);
    }

    private PipelineAnalysisTaskStep sourceStep() {
        return step(PipelineAnalysisTaskStepName.RESOLVE_UPLOADED_SOURCE, context -> {
            Path source = tempDir.resolve("source.mp4");
            Files.writeString(source, "video");
            context.setUploadedSourcePath(source);
        });
    }

    private static PipelineAnalysisTaskStep step(
        PipelineAnalysisTaskStepName name,
        ThrowingAction action
    ) {
        return new PipelineAnalysisTaskStep() {
            @Override
            public PipelineAnalysisTaskStepName name() {
                return name;
            }

            @Override
            public void execute(PipelineAnalysisTaskStepContext context) {
                try {
                    action.run(context);
                } catch (RuntimeException exception) {
                    throw exception;
                } catch (Exception exception) {
                    throw new IllegalStateException(exception);
                }
            }
        };
    }

    private PipelineRunnerWorkspace workspace() {
        return new PipelineRunnerWorkspace(new AnalysisTaskRunnerProperties(tempDir.resolve("runner")));
    }

    private static AnalysisTaskExecutionContext taskContext() {
        return new AnalysisTaskExecutionContext("task_1", "up_1", 7L, "zh-CN", "req_1");
    }

    private static SpeechToTextResult asrResult() {
        return new SpeechToTextResult(
            "fake-asr",
            "en",
            "lecture",
            List.of(new TranscribedSegment(0, 0, 1_000, "lecture")),
            Duration.ofMillis(1),
            1_000,
            Map.of()
        );
    }

    @FunctionalInterface
    private interface ThrowingAction {
        void run(PipelineAnalysisTaskStepContext context) throws Exception;
    }
}
