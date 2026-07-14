package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.asr.SpeechToTextProvider;
import com.example.courselingo.ai.asr.SpeechToTextRequest;
import com.example.courselingo.ai.asr.SpeechToTextResult;
import com.example.courselingo.ai.asr.TranscribedSegment;
import com.example.courselingo.artifact.dto.ArtifactFileView;
import com.example.courselingo.artifact.service.GenerateSrtArtifactCommand;
import com.example.courselingo.artifact.service.SrtArtifactService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.dispatch.BoundedTaskExecutor;
import com.example.courselingo.learning.service.GenerateLearningPackageCommand;
import com.example.courselingo.learning.service.LearningPackageService;
import com.example.courselingo.media.AudioExtractionResult;
import com.example.courselingo.mq.AnalysisTaskMessage;
import com.example.courselingo.subtitle.service.SaveTranscriptionSegmentsCommand;
import com.example.courselingo.subtitle.service.SubtitleSegmentPersistenceService;
import com.example.courselingo.subtitle.service.SubtitleTranslationService;
import com.example.courselingo.subtitle.service.TranslateSubtitleCommand;
import com.example.courselingo.task.claim.TaskClaimResult;
import com.example.courselingo.task.claim.TaskClaimService;
import com.example.courselingo.task.dto.AnalysisTaskStateChangeCommand;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.mapper.TaskLogMapper;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.task.progress.NoopTaskProgressSnapshotService;
import com.example.courselingo.task.service.AnalysisTaskStateMachine;
import com.example.courselingo.task.service.AnalysisTaskStateService;
import com.example.courselingo.task.service.AnalysisTaskStateServiceImpl;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PipelineAnalysisTaskRunnerFailureTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(
        Instant.parse("2026-06-28T12:00:00Z"),
        ZoneOffset.UTC
    );

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private TaskLogMapper taskLogMapper;

    @Mock
    private BoundedTaskExecutor boundedTaskExecutor;

    @Mock
    private TaskClaimService taskClaimService;

    @TempDir
    private Path tempDir;

    private final List<AnalysisTaskStateChangeCommand> stateChanges = new ArrayList<>();

    @BeforeEach
    void setUp() {
        lenient().when(analysisTaskMapper.updateStateByIdAndUserId(any(AnalysisTask.class))).thenAnswer(invocation -> {
            AnalysisTask task = invocation.getArgument(0, AnalysisTask.class);
            stateChanges.add(AnalysisTaskStateChangeCommand.builder()
                .taskId(task.getId())
                .userId(task.getUserId())
                .targetStatus(AnalysisTaskStatus.fromDatabaseValue(task.getStatus()))
                .progressPercent(task.getProgressPercent())
                .errorCode(task.getErrorCode())
                .errorMessage(task.getErrorMessage())
                .build());
            return 1;
        });
        lenient().doAnswer(invocation -> {
            Callable<?> callable = invocation.getArgument(2, Callable.class);
            return callable.call();
        }).when(boundedTaskExecutor).submitAndWait(any(), any(), any());
        lenient().when(taskClaimService.tryAcquire("task_1", "req_1")).thenReturn(TaskClaimResult.acquiredResult());
    }

    @Test
    void pipelineStepFailureIsPropagatedSoRunnerMarksTaskFailed() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        AnalysisTaskRunner runner = new AnalysisTaskRunnerImpl(
            analysisTaskMapper,
            stateService(),
            failingPipelineExecutor(),
            boundedTaskExecutor,
            taskClaimService
        );

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED);

        assertThat(stateChanges)
            .extracting(AnalysisTaskStateChangeCommand::getTargetStatus)
            .containsExactly(AnalysisTaskStatus.RUNNING, AnalysisTaskStatus.FAILED);
        AnalysisTaskStateChangeCommand failed = stateChanges.get(1);
        assertThat(failed.getErrorCode()).isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED.code());
        assertSafe(failed.getErrorMessage());
    }

    @Test
    void ffmpegFailureIsPropagatedSoRunnerMarksTaskFailedWithSanitizedError() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        AnalysisTaskRunner runner = new AnalysisTaskRunnerImpl(
            analysisTaskMapper,
            stateService(),
            ffmpegFailingPipelineExecutor(),
            boundedTaskExecutor,
            taskClaimService
        );

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED);

        assertThat(stateChanges)
            .extracting(AnalysisTaskStateChangeCommand::getTargetStatus)
            .containsExactly(AnalysisTaskStatus.RUNNING, AnalysisTaskStatus.FAILED);
        AnalysisTaskStateChangeCommand failed = stateChanges.get(1);
        assertThat(failed.getErrorCode()).isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED.code());
        assertSafe(failed.getErrorMessage());
    }

    @Test
    void asrProviderFailureIsPropagatedSoRunnerMarksTaskFailedWithSanitizedError() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        AnalysisTaskRunner runner = new AnalysisTaskRunnerImpl(
            analysisTaskMapper,
            stateService(),
            asrFailingPipelineExecutor(),
            boundedTaskExecutor,
            taskClaimService
        );

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED);

        assertThat(stateChanges)
            .extracting(AnalysisTaskStateChangeCommand::getTargetStatus)
            .containsExactly(AnalysisTaskStatus.RUNNING, AnalysisTaskStatus.FAILED);
        AnalysisTaskStateChangeCommand failed = stateChanges.get(1);
        assertThat(failed.getErrorCode()).isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED.code());
        assertSafe(failed.getErrorMessage());
    }

    @Test
    void subtitlePersistenceFailureIsPropagatedSoRunnerMarksTaskFailedWithSanitizedError() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        AnalysisTaskRunner runner = new AnalysisTaskRunnerImpl(
            analysisTaskMapper,
            stateService(),
            subtitlePersistenceFailingPipelineExecutor(),
            boundedTaskExecutor,
            taskClaimService
        );

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED);

        assertThat(stateChanges)
            .extracting(AnalysisTaskStateChangeCommand::getTargetStatus)
            .containsExactly(AnalysisTaskStatus.RUNNING, AnalysisTaskStatus.FAILED);
        AnalysisTaskStateChangeCommand failed = stateChanges.get(1);
        assertThat(failed.getErrorCode()).isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED.code());
        assertSafe(failed.getErrorMessage());
    }

    @Test
    void translationFailureIsPropagatedSoRunnerMarksTaskFailedWithSanitizedError() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        AnalysisTaskRunner runner = new AnalysisTaskRunnerImpl(
            analysisTaskMapper,
            stateService(),
            translationFailingPipelineExecutor(),
            boundedTaskExecutor,
            taskClaimService
        );

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED);

        assertThat(stateChanges)
            .extracting(AnalysisTaskStateChangeCommand::getTargetStatus)
            .containsExactly(AnalysisTaskStatus.RUNNING, AnalysisTaskStatus.FAILED);
        AnalysisTaskStateChangeCommand failed = stateChanges.get(1);
        assertThat(failed.getErrorCode()).isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED.code());
        assertSafe(failed.getErrorMessage());
    }

    @Test
    void learningPackageFailureIsPropagatedSoRunnerMarksTaskFailedWithSanitizedError() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        AnalysisTaskRunner runner = new AnalysisTaskRunnerImpl(
            analysisTaskMapper,
            stateService(),
            learningPackageFailingPipelineExecutor(),
            boundedTaskExecutor,
            taskClaimService
        );

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED);

        assertThat(stateChanges)
            .extracting(AnalysisTaskStateChangeCommand::getTargetStatus)
            .containsExactly(AnalysisTaskStatus.RUNNING, AnalysisTaskStatus.FAILED);
        AnalysisTaskStateChangeCommand failed = stateChanges.get(1);
        assertThat(failed.getErrorCode()).isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED.code());
        assertSafe(failed.getErrorMessage());
    }

    @Test
    void artifactGenerationFailureIsPropagatedSoRunnerMarksTaskFailedWithSanitizedError() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        AnalysisTaskRunner runner = new AnalysisTaskRunnerImpl(
            analysisTaskMapper,
            stateService(),
            artifactGenerationFailingPipelineExecutor(),
            boundedTaskExecutor,
            taskClaimService
        );

        assertThatThrownBy(() -> runner.run(message()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED);

        assertThat(stateChanges)
            .extracting(AnalysisTaskStateChangeCommand::getTargetStatus)
            .containsExactly(AnalysisTaskStatus.RUNNING, AnalysisTaskStatus.FAILED);
        AnalysisTaskStateChangeCommand failed = stateChanges.get(1);
        assertThat(failed.getErrorCode()).isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED.code());
        assertSafe(failed.getErrorMessage());
    }

    private AnalysisTaskStateService stateService() {
        return new AnalysisTaskStateServiceImpl(
            analysisTaskMapper,
            taskLogMapper,
            new AnalysisTaskStateMachine(),
            FIXED_CLOCK,
            new NoopTaskProgressSnapshotService()
        );
    }

    private static PipelineAnalysisTaskWorkExecutor failingPipelineExecutor() {
        List<PipelineAnalysisTaskStep> steps = PipelineAnalysisTaskStepName.ordered().stream()
            .map(name -> (PipelineAnalysisTaskStep) new RecordingPipelineStep(name))
            .toList();
        return new PipelineAnalysisTaskWorkExecutor(steps);
    }

    private PipelineAnalysisTaskWorkExecutor ffmpegFailingPipelineExecutor() {
        List<PipelineAnalysisTaskStep> steps = List.of(
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.VALIDATE_TASK),
            new SourceResolvingStep(tempDir.resolve("source.mp4")),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES),
            new ExtractAudioStep(request -> {
                throw new IllegalStateException(
                    "ffmpeg failed token=raw secret=raw api key=raw objectKey=raw C:\\Users\\demo\\video.mp4"
                );
            }, new PipelineRunnerWorkspace(new AnalysisTaskRunnerProperties(tempDir.resolve("runner")))),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.TRANSCRIBE),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.PERSIST_SUBTITLES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.OCR_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.UPDATE_TASK_PROGRESS_STATUS)
        );
        return new PipelineAnalysisTaskWorkExecutor(steps);
    }

    private PipelineAnalysisTaskWorkExecutor asrFailingPipelineExecutor() {
        List<PipelineAnalysisTaskStep> steps = List.of(
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.VALIDATE_TASK),
            new SourceResolvingStep(tempDir.resolve("source.mp4")),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES),
            new ExtractAudioStep(request ->
                new AudioExtractionResult(request.outputDirectory().resolve(request.outputFileName()), "wav", 16000, 1),
                new PipelineRunnerWorkspace(new AnalysisTaskRunnerProperties(tempDir.resolve("runner")))),
            new TranscribeAudioStep(new FailingSpeechToTextProvider()),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.PERSIST_SUBTITLES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.OCR_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.UPDATE_TASK_PROGRESS_STATUS)
        );
        return new PipelineAnalysisTaskWorkExecutor(steps);
    }

    private PipelineAnalysisTaskWorkExecutor subtitlePersistenceFailingPipelineExecutor() {
        List<PipelineAnalysisTaskStep> steps = List.of(
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.VALIDATE_TASK),
            new SourceResolvingStep(tempDir.resolve("source.mp4")),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES),
            new ExtractAudioStep(request ->
                new AudioExtractionResult(request.outputDirectory().resolve(request.outputFileName()), "wav", 16000, 1),
                new PipelineRunnerWorkspace(new AnalysisTaskRunnerProperties(tempDir.resolve("runner")))),
            new TranscribeAudioStep(new FixedSpeechToTextProvider()),
            new PersistSubtitleSegmentsStep(analysisTaskMapper, new FailingSubtitlePersistenceService()),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.OCR_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.UPDATE_TASK_PROGRESS_STATUS)
        );
        return new PipelineAnalysisTaskWorkExecutor(steps);
    }

    private PipelineAnalysisTaskWorkExecutor translationFailingPipelineExecutor() {
        List<PipelineAnalysisTaskStep> steps = List.of(
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.VALIDATE_TASK),
            new SourceResolvingStep(tempDir.resolve("source.mp4")),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES),
            new ExtractAudioStep(request ->
                new AudioExtractionResult(request.outputDirectory().resolve(request.outputFileName()), "wav", 16000, 1),
                new PipelineRunnerWorkspace(new AnalysisTaskRunnerProperties(tempDir.resolve("runner")))),
            new TranscribeAudioStep(new FixedSpeechToTextProvider()),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.PERSIST_SUBTITLES),
            new TranslateSubtitleSegmentsStep(analysisTaskMapper, new FailingSubtitleTranslationService()),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.OCR_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.UPDATE_TASK_PROGRESS_STATUS)
        );
        return new PipelineAnalysisTaskWorkExecutor(steps);
    }

    private PipelineAnalysisTaskWorkExecutor learningPackageFailingPipelineExecutor() {
        List<PipelineAnalysisTaskStep> steps = List.of(
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.VALIDATE_TASK),
            new SourceResolvingStep(tempDir.resolve("source.mp4")),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES),
            new ExtractAudioStep(request ->
                new AudioExtractionResult(request.outputDirectory().resolve(request.outputFileName()), "wav", 16000, 1),
                new PipelineRunnerWorkspace(new AnalysisTaskRunnerProperties(tempDir.resolve("runner")))),
            new TranscribeAudioStep(new FixedSpeechToTextProvider()),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.PERSIST_SUBTITLES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES),
            new GenerateLearningPackageStep(analysisTaskMapper, new FailingLearningPackageService()),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.OCR_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.UPDATE_TASK_PROGRESS_STATUS)
        );
        return new PipelineAnalysisTaskWorkExecutor(steps);
    }

    private PipelineAnalysisTaskWorkExecutor artifactGenerationFailingPipelineExecutor() {
        List<PipelineAnalysisTaskStep> steps = List.of(
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.VALIDATE_TASK),
            new SourceResolvingStep(tempDir.resolve("source.mp4")),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES),
            new ExtractAudioStep(request ->
                new AudioExtractionResult(request.outputDirectory().resolve(request.outputFileName()), "wav", 16000, 1),
                new PipelineRunnerWorkspace(new AnalysisTaskRunnerProperties(tempDir.resolve("runner")))),
            new TranscribeAudioStep(new FixedSpeechToTextProvider()),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.PERSIST_SUBTITLES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE),
            new GenerateArtifactsStep(
                analysisTaskMapper,
                new FailingSrtArtifactService(),
                mock(com.example.courselingo.artifact.service.VttArtifactService.class),
                mock(com.example.courselingo.artifact.service.MarkdownArtifactService.class),
                mock(com.example.courselingo.artifact.service.JsonArtifactService.class)
            ),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.OCR_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.UPDATE_TASK_PROGRESS_STATUS)
        );
        return new PipelineAnalysisTaskWorkExecutor(steps);
    }

    private static AnalysisTask task() {
        AnalysisTask task = new AnalysisTask();
        task.setId("task_1");
        task.setUserId(7L);
        task.setUploadId("up_1");
        task.setTargetLanguage("zh-CN");
        task.setStatus(AnalysisTaskStatus.QUEUED.name());
        task.setProgressPercent(0);
        task.setRetryCount(0);
        task.setMaxRetryCount(3);
        return task;
    }

    private static AnalysisTaskMessage message() {
        return new AnalysisTaskMessage(
            "task_1",
            "up_1",
            7L,
            "zh-CN",
            "req_1",
            "trace_1",
            Instant.parse("2026-06-28T10:00:00Z")
        );
    }

    private static void assertSafe(String value) {
        assertThat(value).doesNotContainIgnoringCase("token");
        assertThat(value).doesNotContainIgnoringCase("secret");
        assertThat(value).doesNotContainIgnoringCase("api key");
        assertThat(value).doesNotContainIgnoringCase("objectKey");
        assertThat(value).doesNotContain("C:\\Users");
    }

    private record RecordingPipelineStep(PipelineAnalysisTaskStepName name) implements PipelineAnalysisTaskStep {

        @Override
        public void execute(PipelineAnalysisTaskStepContext context) {
            if (name == PipelineAnalysisTaskStepName.TRANSCRIBE) {
                throw new IllegalStateException(
                    "transcribe failed token=raw secret=raw api key=raw objectKey=raw C:\\Users\\demo\\video.mp4"
                );
            }
        }
    }

    private record SourceResolvingStep(Path sourcePath) implements PipelineAnalysisTaskStep {

        @Override
        public PipelineAnalysisTaskStepName name() {
            return PipelineAnalysisTaskStepName.RESOLVE_UPLOADED_SOURCE;
        }

        @Override
        public void execute(PipelineAnalysisTaskStepContext context) {
            context.setUploadedSourcePath(sourcePath);
        }
    }

    private static final class FailingSpeechToTextProvider implements SpeechToTextProvider {

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            throw new IllegalStateException(
                "asr failed token=raw secret=raw api key=raw objectKey=raw C:\\Users\\demo\\audio.wav"
            );
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static final class FixedSpeechToTextProvider implements SpeechToTextProvider {

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            return new SpeechToTextResult(
                "fake-asr",
                "zh-CN",
                "hello",
                List.of(new TranscribedSegment(0, 0, 1000, "hello")),
                Duration.ofMillis(10),
                1000,
                Map.of("safe", "metadata")
            );
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static final class FailingSubtitlePersistenceService implements SubtitleSegmentPersistenceService {

        @Override
        public int saveTranscriptionResult(SaveTranscriptionSegmentsCommand command) {
            throw new IllegalStateException(
                "subtitle failed token=raw secret=raw api key=raw objectKey=raw C:\\Users\\demo\\subtitle.txt"
            );
        }

        @Override
        public int deleteByTaskId(String taskId, Long userId) {
            throw new UnsupportedOperationException("not used");
        }
    }

    private static final class FailingSubtitleTranslationService implements SubtitleTranslationService {

        @Override
        public int translateTaskSubtitles(TranslateSubtitleCommand command) {
            throw new IllegalStateException(
                "translation failed token=raw secret=raw api key=raw objectKey=raw C:\\Users\\demo\\translation.json"
            );
        }

        @Override
        public int deleteTranslations(String taskId, Long userId, String targetLanguage) {
            throw new UnsupportedOperationException("not used");
        }
    }

    private static final class FailingLearningPackageService implements LearningPackageService {

        @Override
        public int generateLearningPackage(GenerateLearningPackageCommand command) {
            throw new IllegalStateException(
                "learning package failed token=raw secret=raw api key=raw objectKey=raw C:\\Users\\demo\\package.json"
            );
        }

        @Override
        public int deleteLearningPackage(String taskId, Long userId, String targetLanguage) {
            throw new UnsupportedOperationException("not used");
        }
    }

    private static final class FailingSrtArtifactService implements SrtArtifactService {

        @Override
        public ArtifactFileView generateSrtArtifact(GenerateSrtArtifactCommand command) {
            throw new IllegalStateException(
                "artifact failed token=raw secret=raw api key=raw objectKey=raw C:\\Users\\demo\\artifact.srt"
            );
        }
    }
}
