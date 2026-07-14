package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.asr.SpeechToTextProvider;
import com.example.courselingo.ai.asr.SpeechToTextRequest;
import com.example.courselingo.ai.asr.SpeechToTextResult;
import com.example.courselingo.ai.asr.TranscribedSegment;
import com.example.courselingo.media.AudioExtractionResult;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.service.SaveTranscriptionSegmentsCommand;
import com.example.courselingo.subtitle.service.SubtitleSegmentPersistenceService;
import com.example.courselingo.subtitle.service.SubtitleSegmentPersistenceServiceImpl;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class PipelineF3ExecutionOrderTest {

    @TempDir
    private Path tempDir;

    @Test
    void pipelineExecutesThroughTranscribeAndSubtitlePersistenceInOrder() throws Exception {
        Path source = tempDir.resolve("source.mp4");
        Files.writeString(source, "video", StandardCharsets.UTF_8);
        AnalysisTaskMapper analysisTaskMapper = mock(AnalysisTaskMapper.class);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        List<PipelineAnalysisTaskStepName> executed = new ArrayList<>();
        AtomicReference<SaveTranscriptionSegmentsCommand> savedCommand = new AtomicReference<>();

        PipelineAnalysisTaskWorkExecutor executor = new PipelineAnalysisTaskWorkExecutor(List.of(
            new RecordingNoopStep(PipelineAnalysisTaskStepName.VALIDATE_TASK, executed),
            new SourceResolvingStep(source, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES, executed),
            new ExtractAudioStep(request -> {
                executed.add(PipelineAnalysisTaskStepName.EXTRACT_AUDIO);
                Path audio = request.outputDirectory().resolve(request.outputFileName());
                writeAudioFile(audio);
                return new AudioExtractionResult(audio, "wav", 16000, 1);
            }, new PipelineRunnerWorkspace(new AnalysisTaskRunnerProperties(tempDir.resolve("runner")))),
            new TranscribeAudioStep(new RecordingSpeechToTextProvider(executed), ignored -> 2400L),
            new PersistSubtitleSegmentsStep(
                analysisTaskMapper,
                new RecordingSubtitlePersistenceService(executed, savedCommand)
            ),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.OCR_KEYFRAMES, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.UPDATE_TASK_PROGRESS_STATUS, executed)
        ));

        AnalysisTaskWorkResult result = executor.execute(context());

        assertThat(result.success()).isTrue();
        assertThat(executed)
            .containsSubsequence(
                PipelineAnalysisTaskStepName.VALIDATE_TASK,
                PipelineAnalysisTaskStepName.RESOLVE_UPLOADED_SOURCE,
                PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES,
                PipelineAnalysisTaskStepName.EXTRACT_AUDIO,
                PipelineAnalysisTaskStepName.TRANSCRIBE,
                PipelineAnalysisTaskStepName.PERSIST_SUBTITLES
            );
        SaveTranscriptionSegmentsCommand command = savedCommand.get();
        assertThat(command.taskId()).isEqualTo("task_1");
        assertThat(command.userId()).isEqualTo(7L);
        assertThat(command.result().segments())
            .extracting(TranscribedSegment::text)
            .containsExactly("hello course", "world");
    }

    @Test
    void repeatedPipelineExecutionDoesNotDuplicatePersistedSubtitleSegments() throws Exception {
        Path source = tempDir.resolve("source.mp4");
        Files.writeString(source, "video", StandardCharsets.UTF_8);
        AnalysisTaskMapper analysisTaskMapper = mock(AnalysisTaskMapper.class);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        SubtitleSegmentMapper subtitleSegmentMapper = mock(SubtitleSegmentMapper.class);
        List<SubtitleSegment> storedSegments = new ArrayList<>();
        when(subtitleSegmentMapper.deleteByTaskIdAndUserId("task_1", 7L)).thenAnswer(invocation -> {
            int removed = storedSegments.size();
            storedSegments.clear();
            return removed;
        });
        when(subtitleSegmentMapper.insert(any(SubtitleSegment.class))).thenAnswer(invocation -> {
            storedSegments.add(invocation.getArgument(0, SubtitleSegment.class));
            return 1;
        });

        PipelineAnalysisTaskWorkExecutor executor = new PipelineAnalysisTaskWorkExecutor(List.of(
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.VALIDATE_TASK),
            new SourceResolvingStep(source, new ArrayList<>()),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES),
            new ExtractAudioStep(request -> {
                Path audio = request.outputDirectory().resolve(request.outputFileName());
                writeAudioFile(audio);
                return new AudioExtractionResult(audio, "wav", 16000, 1);
            }, new PipelineRunnerWorkspace(new AnalysisTaskRunnerProperties(tempDir.resolve("runner")))),
            new TranscribeAudioStep(new FixedSpeechToTextProvider(), ignored -> 2400L),
            new PersistSubtitleSegmentsStep(
                analysisTaskMapper,
                new SubtitleSegmentPersistenceServiceImpl(subtitleSegmentMapper)
            ),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.OCR_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.UPDATE_TASK_PROGRESS_STATUS)
        ));

        executor.execute(context());
        executor.execute(context());

        assertThat(storedSegments).hasSize(2);
        assertThat(storedSegments).extracting(SubtitleSegment::getSegmentIndex).containsExactly(0, 1);
        assertThat(storedSegments).extracting(SubtitleSegment::getTaskId).containsOnly("task_1");
        assertThat(storedSegments).extracting(SubtitleSegment::getUserId).containsOnly(7L);
        verify(subtitleSegmentMapper, times(2)).deleteByTaskIdAndUserId("task_1", 7L);
        verify(subtitleSegmentMapper, times(4)).insert(any(SubtitleSegment.class));
    }

    private static AnalysisTaskExecutionContext context() {
        return new AnalysisTaskExecutionContext("task_1", "up_1", 7L, "zh-CN", "req_1");
    }

    private static AnalysisTask task() {
        AnalysisTask task = new AnalysisTask();
        task.setId("task_1");
        task.setUserId(7L);
        return task;
    }

    private static SpeechToTextResult result() {
        return new SpeechToTextResult(
            "fake-asr",
            "zh-CN",
            "hello course world",
            List.of(
                new TranscribedSegment(0, 0, 1200, "hello course"),
                new TranscribedSegment(1, 1200, 2400, "world")
            ),
            Duration.ofMillis(10),
            2400,
            Map.of("safe", "metadata")
        );
    }

    private static void writeAudioFile(Path audio) {
        try {
            Files.writeString(audio, "audio", StandardCharsets.UTF_8);
        } catch (java.io.IOException exception) {
            throw new IllegalStateException("test audio fixture write failed", exception);
        }
    }

    private record RecordingNoopStep(
        PipelineAnalysisTaskStepName name,
        List<PipelineAnalysisTaskStepName> executed
    ) implements PipelineAnalysisTaskStep {

        @Override
        public void execute(PipelineAnalysisTaskStepContext context) {
            executed.add(name);
        }
    }

    private record SourceResolvingStep(
        Path sourcePath,
        List<PipelineAnalysisTaskStepName> executed
    ) implements PipelineAnalysisTaskStep {

        @Override
        public PipelineAnalysisTaskStepName name() {
            return PipelineAnalysisTaskStepName.RESOLVE_UPLOADED_SOURCE;
        }

        @Override
        public void execute(PipelineAnalysisTaskStepContext context) {
            executed.add(name());
            context.setUploadedSourcePath(sourcePath);
        }
    }

    private record RecordingSpeechToTextProvider(
        List<PipelineAnalysisTaskStepName> executed
    ) implements SpeechToTextProvider {

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            executed.add(PipelineAnalysisTaskStepName.TRANSCRIBE);
            return result();
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static final class FixedSpeechToTextProvider implements SpeechToTextProvider {

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            return result();
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private record RecordingSubtitlePersistenceService(
        List<PipelineAnalysisTaskStepName> executed,
        AtomicReference<SaveTranscriptionSegmentsCommand> savedCommand
    ) implements SubtitleSegmentPersistenceService {

        @Override
        public int saveTranscriptionResult(SaveTranscriptionSegmentsCommand command) {
            executed.add(PipelineAnalysisTaskStepName.PERSIST_SUBTITLES);
            savedCommand.set(command);
            return command.result().segments().size();
        }

        @Override
        public int deleteByTaskId(String taskId, Long userId) {
            throw new UnsupportedOperationException("not used");
        }
    }
}
