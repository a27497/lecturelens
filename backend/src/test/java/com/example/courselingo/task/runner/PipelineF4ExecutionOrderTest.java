package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.asr.SpeechToTextProvider;
import com.example.courselingo.ai.asr.SpeechToTextRequest;
import com.example.courselingo.ai.asr.SpeechToTextResult;
import com.example.courselingo.ai.asr.TranscribedSegment;
import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResult;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.learning.domain.LearningPackage;
import com.example.courselingo.learning.mapper.LearningPackageMapper;
import com.example.courselingo.learning.service.GenerateLearningPackageCommand;
import com.example.courselingo.learning.service.LearningPackageResponseParser;
import com.example.courselingo.learning.service.LearningPackageService;
import com.example.courselingo.learning.service.LearningPackageServiceImpl;
import com.example.courselingo.media.AudioExtractionResult;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import com.example.courselingo.subtitle.service.SaveTranscriptionSegmentsCommand;
import com.example.courselingo.subtitle.service.SubtitleSegmentPersistenceServiceImpl;
import com.example.courselingo.subtitle.service.SubtitleTranslationResponseParser;
import com.example.courselingo.subtitle.service.SubtitleTranslationService;
import com.example.courselingo.subtitle.service.SubtitleTranslationServiceImpl;
import com.example.courselingo.subtitle.service.TranslateSubtitleCommand;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class PipelineF4ExecutionOrderTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(
        Instant.parse("2026-06-28T10:00:00Z"),
        ZoneOffset.UTC
    );

    @TempDir
    private Path tempDir;

    @Test
    void pipelineExecutesThroughTranslationAndLearningPackageWithIdempotentPersistence() throws Exception {
        Path source = tempDir.resolve("source.mp4");
        Files.writeString(source, "video", StandardCharsets.UTF_8);
        AnalysisTaskMapper analysisTaskMapper = mock(AnalysisTaskMapper.class);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        SubtitleSegmentMapper subtitleSegmentMapper = mock(SubtitleSegmentMapper.class);
        SubtitleTranslationSegmentMapper translationMapper = mock(SubtitleTranslationSegmentMapper.class);
        LearningPackageMapper learningPackageMapper = mock(LearningPackageMapper.class);
        List<SubtitleSegment> storedSubtitles = new ArrayList<>();
        List<SubtitleTranslationSegment> storedTranslations = new ArrayList<>();
        List<LearningPackage> storedPackages = new ArrayList<>();
        AtomicInteger translationDeleteCount = new AtomicInteger();
        AtomicInteger learningDeleteCount = new AtomicInteger();
        stubSubtitleMapper(subtitleSegmentMapper, storedSubtitles);
        stubTranslationMapper(translationMapper, storedTranslations, translationDeleteCount);
        stubLearningPackageMapper(learningPackageMapper, storedPackages, learningDeleteCount);
        List<PipelineAnalysisTaskStepName> executed = new ArrayList<>();
        FakeLlmProvider fakeLlmProvider = new FakeLlmProvider();
        fakeLlmProvider.enqueue("Hello translated");
        fakeLlmProvider.enqueue("World translated");
        fakeLlmProvider.enqueue("""
            {"title":"Course Title","summary":"Course summary","keyPoints":[{"index":1,"text":"Point"}],"glossary":[{"term":"Term","definition":"Definition","translation":"Term translated"}],"qa":[{"question":"Question","answer":"Answer"}]}
            """);
        fakeLlmProvider.enqueue("Hello translated");
        fakeLlmProvider.enqueue("World translated");
        fakeLlmProvider.enqueue("""
            {"title":"Course Title","summary":"Course summary","keyPoints":[{"index":1,"text":"Point"}],"glossary":[{"term":"Term","definition":"Definition","translation":"Term translated"}],"qa":[{"question":"Question","answer":"Answer"}]}
            """);

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
                new RecordingSubtitlePersistenceService(
                    executed,
                    new SubtitleSegmentPersistenceServiceImpl(subtitleSegmentMapper)
                )
            ),
            new TranslateSubtitleSegmentsStep(
                analysisTaskMapper,
                new RecordingSubtitleTranslationService(
                    executed,
                    new SubtitleTranslationServiceImpl(
                        subtitleSegmentMapper,
                        translationMapper,
                        fakeLlmProvider,
                        FIXED_CLOCK,
                        new SubtitleTranslationResponseParser()
                    )
                )
            ),
            new GenerateLearningPackageStep(
                analysisTaskMapper,
                new RecordingLearningPackageService(
                    executed,
                    new LearningPackageServiceImpl(
                        subtitleSegmentMapper,
                        translationMapper,
                        learningPackageMapper,
                        fakeLlmProvider,
                        FIXED_CLOCK,
                        new LearningPackageResponseParser()
                    )
                )
            ),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.OCR_KEYFRAMES, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.UPDATE_TASK_PROGRESS_STATUS, executed)
        ));

        executor.execute(context());
        executor.execute(context());

        assertThat(executed)
            .containsSubsequence(
                PipelineAnalysisTaskStepName.VALIDATE_TASK,
                PipelineAnalysisTaskStepName.RESOLVE_UPLOADED_SOURCE,
                PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES,
                PipelineAnalysisTaskStepName.EXTRACT_AUDIO,
                PipelineAnalysisTaskStepName.TRANSCRIBE,
                PipelineAnalysisTaskStepName.PERSIST_SUBTITLES,
                PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES,
                PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE
            );
        assertThat(storedSubtitles).hasSize(2);
        assertThat(storedTranslations).hasSize(2);
        assertThat(storedTranslations).extracting(SubtitleTranslationSegment::getTaskId).containsOnly("task_1");
        assertThat(storedTranslations).extracting(SubtitleTranslationSegment::getUserId).containsOnly(7L);
        assertThat(storedTranslations).extracting(SubtitleTranslationSegment::getSegmentIndex).containsExactly(0, 1);
        assertThat(storedTranslations).extracting(SubtitleTranslationSegment::getSourceLanguage).containsOnly("en");
        assertThat(storedTranslations).extracting(SubtitleTranslationSegment::getTargetLanguage).containsOnly("zh-CN");
        assertThat(storedTranslations).extracting(SubtitleTranslationSegment::getTranslatedText)
            .containsExactly("Hello translated", "World translated");
        assertThat(storedPackages).hasSize(1);
        LearningPackage learningPackage = storedPackages.getFirst();
        assertThat(learningPackage.getTaskId()).isEqualTo("task_1");
        assertThat(learningPackage.getUserId()).isEqualTo(7L);
        assertThat(learningPackage.getTargetLanguage()).isEqualTo("zh-CN");
        assertThat(learningPackage.getSummary()).isEqualTo("Course summary");
        assertThat(learningPackage.getGlossaryJson()).contains("Term");
        assertThat(learningPackage.getQaJson()).contains("Question");
        assertThat(fakeLlmProvider.requests).hasSize(6);
        assertThat(translationDeleteCount).hasValue(2);
        assertThat(learningDeleteCount).hasValue(2);
    }

    @Test
    void missingSubtitleSegmentsMakeTranslationStepFailWithSanitizedError() {
        AnalysisTaskMapper analysisTaskMapper = mock(AnalysisTaskMapper.class);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        SubtitleSegmentMapper subtitleSegmentMapper = mock(SubtitleSegmentMapper.class);
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 7L)).thenReturn(List.of());

        TranslateSubtitleSegmentsStep step = new TranslateSubtitleSegmentsStep(
            analysisTaskMapper,
            new SubtitleTranslationServiceImpl(
                subtitleSegmentMapper,
                mock(SubtitleTranslationSegmentMapper.class),
                new FakeLlmProvider(),
                FIXED_CLOCK,
                new SubtitleTranslationResponseParser()
            )
        );

        assertThatThrownBy(() -> step.execute(contextWithAsrResult()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
    }

    @Test
    void missingTranslatedSegmentsMakeLearningPackageStepFailWithSanitizedError() {
        AnalysisTaskMapper analysisTaskMapper = mock(AnalysisTaskMapper.class);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        SubtitleSegmentMapper subtitleSegmentMapper = mock(SubtitleSegmentMapper.class);
        SubtitleTranslationSegmentMapper translationMapper = mock(SubtitleTranslationSegmentMapper.class);
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 7L)).thenReturn(sourceSegments());
        when(translationMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 7L, "zh-CN")).thenReturn(List.of());

        GenerateLearningPackageStep step = new GenerateLearningPackageStep(
            analysisTaskMapper,
            new LearningPackageServiceImpl(
                subtitleSegmentMapper,
                translationMapper,
                mock(LearningPackageMapper.class),
                new FakeLlmProvider(),
                FIXED_CLOCK,
                new LearningPackageResponseParser()
            )
        );

        assertThatThrownBy(() -> step.execute(contextWithAsrResult()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
    }

    private static AnalysisTaskExecutionContext context() {
        return new AnalysisTaskExecutionContext("task_1", "up_1", 7L, "zh-CN", "req_1");
    }

    private static PipelineAnalysisTaskStepContext contextWithAsrResult() {
        PipelineAnalysisTaskStepContext context = new PipelineAnalysisTaskStepContext(context());
        context.setSpeechToTextResult(result());
        return context;
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
            "en",
            "hello world",
            List.of(
                new TranscribedSegment(0, 0, 1200, "hello"),
                new TranscribedSegment(1, 1200, 2400, "world")
            ),
            Duration.ofMillis(10),
            2400,
            Map.of("safe", "metadata")
        );
    }

    private static List<SubtitleSegment> sourceSegments() {
        return List.of(sourceSegment(0, 0, 1200, "hello"), sourceSegment(1, 1200, 2400, "world"));
    }

    private static void writeAudioFile(Path audio) {
        try {
            Files.writeString(audio, "audio", StandardCharsets.UTF_8);
        } catch (java.io.IOException exception) {
            throw new IllegalStateException("test audio fixture write failed", exception);
        }
    }

    private static SubtitleSegment sourceSegment(int index, long startMillis, long endMillis, String text) {
        SubtitleSegment segment = new SubtitleSegment();
        segment.setTaskId("task_1");
        segment.setUserId(7L);
        segment.setSegmentIndex(index);
        segment.setStartMillis(startMillis);
        segment.setEndMillis(endMillis);
        segment.setLanguage("en");
        segment.setText(text);
        segment.setProvider("fake-asr");
        return segment;
    }

    private static void stubSubtitleMapper(SubtitleSegmentMapper mapper, List<SubtitleSegment> stored) {
        when(mapper.deleteByTaskIdAndUserId("task_1", 7L)).thenAnswer(invocation -> {
            int size = stored.size();
            stored.clear();
            return size;
        });
        when(mapper.insert(any(SubtitleSegment.class))).thenAnswer(invocation -> {
            stored.add(invocation.getArgument(0, SubtitleSegment.class));
            return 1;
        });
        when(mapper.selectByTaskIdAndUserId("task_1", 7L)).thenAnswer(invocation -> stored.stream()
            .sorted(Comparator.comparing(SubtitleSegment::getSegmentIndex))
            .toList());
    }

    private static void stubTranslationMapper(
        SubtitleTranslationSegmentMapper mapper,
        List<SubtitleTranslationSegment> stored,
        AtomicInteger deleteCount
    ) {
        when(mapper.deleteByTaskIdUserIdAndTargetLanguage("task_1", 7L, "zh-CN")).thenAnswer(invocation -> {
            deleteCount.incrementAndGet();
            int size = stored.size();
            stored.clear();
            return size;
        });
        when(mapper.insert(any(SubtitleTranslationSegment.class))).thenAnswer(invocation -> {
            stored.add(invocation.getArgument(0, SubtitleTranslationSegment.class));
            return 1;
        });
        when(mapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 7L, "zh-CN")).thenAnswer(invocation -> stored.stream()
            .sorted(Comparator.comparing(SubtitleTranslationSegment::getSegmentIndex))
            .toList());
    }

    private static void stubLearningPackageMapper(
        LearningPackageMapper mapper,
        List<LearningPackage> stored,
        AtomicInteger deleteCount
    ) {
        when(mapper.deleteByTaskIdUserIdAndTargetLanguage("task_1", 7L, "zh-CN")).thenAnswer(invocation -> {
            deleteCount.incrementAndGet();
            int size = stored.size();
            stored.clear();
            return size;
        });
        when(mapper.insert(any(LearningPackage.class))).thenAnswer(invocation -> {
            stored.add(invocation.getArgument(0, LearningPackage.class));
            return 1;
        });
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

    private record RecordingSubtitlePersistenceService(
        List<PipelineAnalysisTaskStepName> executed,
        SubtitleSegmentPersistenceServiceImpl delegate
    ) implements com.example.courselingo.subtitle.service.SubtitleSegmentPersistenceService {

        @Override
        public int saveTranscriptionResult(SaveTranscriptionSegmentsCommand command) {
            executed.add(PipelineAnalysisTaskStepName.PERSIST_SUBTITLES);
            return delegate.saveTranscriptionResult(command);
        }

        @Override
        public int deleteByTaskId(String taskId, Long userId) {
            return delegate.deleteByTaskId(taskId, userId);
        }
    }

    private record RecordingSubtitleTranslationService(
        List<PipelineAnalysisTaskStepName> executed,
        SubtitleTranslationService delegate
    ) implements SubtitleTranslationService {

        @Override
        public int translateTaskSubtitles(TranslateSubtitleCommand command) {
            executed.add(PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES);
            return delegate.translateTaskSubtitles(command);
        }

        @Override
        public int deleteTranslations(String taskId, Long userId, String targetLanguage) {
            return delegate.deleteTranslations(taskId, userId, targetLanguage);
        }
    }

    private record RecordingLearningPackageService(
        List<PipelineAnalysisTaskStepName> executed,
        LearningPackageService delegate
    ) implements LearningPackageService {

        @Override
        public int generateLearningPackage(GenerateLearningPackageCommand command) {
            executed.add(PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE);
            return delegate.generateLearningPackage(command);
        }

        @Override
        public int deleteLearningPackage(String taskId, Long userId, String targetLanguage) {
            return delegate.deleteLearningPackage(taskId, userId, targetLanguage);
        }
    }

    private static final class FakeLlmProvider implements LlmProvider {

        private final List<String> responses = new ArrayList<>();
        private final List<LlmRequest> requests = new ArrayList<>();

        void enqueue(String response) {
            responses.add(response);
        }

        @Override
        public LlmResult generate(LlmRequest request) {
            requests.add(request);
            String content = responses.isEmpty() ? "{}" : responses.removeFirst();
            return new LlmResult("fake-llm", "fake-model", content, "stop", null, Duration.ofMillis(1), Map.of());
        }

        @Override
        public String providerName() {
            return "fake-llm";
        }
    }
}
