package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.courselingo.artifact.domain.ArtifactFile;
import com.example.courselingo.artifact.service.ArtifactFileServiceImpl;
import com.example.courselingo.artifact.service.ArtifactObjectKeyGenerator;
import com.example.courselingo.artifact.service.GenerateSrtArtifactCommand;
import com.example.courselingo.artifact.service.JsonArtifactServiceImpl;
import com.example.courselingo.artifact.service.JsonLearningPackageExporter;
import com.example.courselingo.artifact.service.MarkdownArtifactServiceImpl;
import com.example.courselingo.artifact.service.MarkdownLearningPackageFormatter;
import com.example.courselingo.artifact.service.SrtArtifactService;
import com.example.courselingo.artifact.service.SrtArtifactServiceImpl;
import com.example.courselingo.artifact.service.SrtFormatter;
import com.example.courselingo.artifact.service.VttArtifactServiceImpl;
import com.example.courselingo.artifact.service.VttFormatter;
import com.example.courselingo.artifact.mapper.ArtifactFileMapper;
import com.example.courselingo.learning.dto.LearningPackageView;
import com.example.courselingo.learning.service.LearningPackageQueryService;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.subtitle.dto.SubtitleSegmentView;
import com.example.courselingo.subtitle.dto.SubtitleTranslationSegmentView;
import com.example.courselingo.subtitle.service.SubtitleSegmentQueryService;
import com.example.courselingo.subtitle.service.SubtitleTranslationQueryService;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;

class PipelineF5ExecutionOrderTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(
        Instant.parse("2026-06-28T14:00:00Z"),
        ZoneOffset.UTC
    );

    @Test
    void pipelineExecutesThroughArtifactGenerationWithIdempotentMetadata() {
        AnalysisTaskMapper analysisTaskMapper = mock(AnalysisTaskMapper.class);
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task());
        List<ArtifactFile> storedFiles = new ArrayList<>();
        FakeStorageService storageService = new FakeStorageService();
        ArtifactFileServiceImpl artifactFileService = new ArtifactFileServiceImpl(
            artifactFileMapper(storedFiles),
            storageService,
            FIXED_CLOCK,
            new ArtifactObjectKeyGenerator()
        );
        ArtifactQueryFixtures fixtures = new ArtifactQueryFixtures();
        List<PipelineAnalysisTaskStepName> executed = new ArrayList<>();

        PipelineAnalysisTaskWorkExecutor executor = new PipelineAnalysisTaskWorkExecutor(List.of(
            new RecordingNoopStep(PipelineAnalysisTaskStepName.VALIDATE_TASK, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.RESOLVE_UPLOADED_SOURCE, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.EXTRACT_AUDIO, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.TRANSCRIBE, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.PERSIST_SUBTITLES, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES, executed),
            new RecordingNoopStep(PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE, executed),
            new GenerateArtifactsStep(
                analysisTaskMapper,
                new RecordingSrtArtifactService(executed, srtArtifactService(fixtures, artifactFileService)),
                new VttArtifactServiceImpl(fixtures, artifactFileService, new VttFormatter()),
                new MarkdownArtifactServiceImpl(
                    fixtures,
                    artifactFileService,
                    new MarkdownLearningPackageFormatter(new ObjectMapper())
                ),
                new JsonArtifactServiceImpl(
                    fixtures,
                    fixtures,
                    fixtures,
                    artifactFileService,
                    new JsonLearningPackageExporter(new ObjectMapper())
                )
            ),
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
                PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE,
                PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS,
                PipelineAnalysisTaskStepName.OCR_KEYFRAMES,
                PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES,
                PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS,
                PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD
            );
        assertThat(storedFiles).hasSize(4);
        assertThat(storedFiles).extracting(ArtifactFile::getTaskId).containsOnly("task_1");
        assertThat(storedFiles).extracting(ArtifactFile::getUserId).containsOnly(7L);
        assertThat(storedFiles).extracting(ArtifactFile::getLanguage).containsOnly("zh-CN");
        assertThat(storedFiles).extracting(ArtifactFile::getArtifactType)
            .containsExactlyInAnyOrder("SRT", "VTT", "MARKDOWN", "JSON");
        assertThat(contentTypesByType(storedFiles))
            .containsEntry("SRT", "application/x-subrip")
            .containsEntry("VTT", "text/vtt; charset=utf-8")
            .containsEntry("MARKDOWN", "text/markdown; charset=utf-8")
            .containsEntry("JSON", "application/json; charset=utf-8");
        assertThat(storedFiles).allSatisfy(file -> {
            assertThat(file.getSizeBytes()).isPositive();
            assertThat(file.getObjectKey()).startsWith("artifacts/7/task_1/");
            assertThat(storageService.contents).containsKey(file.getObjectKey());
            assertThat(storageService.contents.get(file.getObjectKey())).hasSize(file.getSizeBytes().intValue());
        });
        assertThat(countsByType(storedFiles))
            .containsEntry("SRT", 1L)
            .containsEntry("VTT", 1L)
            .containsEntry("MARKDOWN", 1L)
            .containsEntry("JSON", 1L);
    }

    private static SrtArtifactService srtArtifactService(
        ArtifactQueryFixtures fixtures,
        ArtifactFileServiceImpl artifactFileService
    ) {
        return new SrtArtifactServiceImpl(fixtures, artifactFileService, new SrtFormatter());
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

    private static ArtifactFileMapper artifactFileMapper(List<ArtifactFile> storedFiles) {
        ArtifactFileMapper mapper = mock(ArtifactFileMapper.class);
        AtomicLong id = new AtomicLong(1);
        when(mapper.selectByScope(anyString(), anyLong(), anyString(), anyString())).thenAnswer(invocation -> {
            String taskId = invocation.getArgument(0, String.class);
            Long userId = invocation.getArgument(1, Long.class);
            String artifactType = invocation.getArgument(2, String.class);
            String language = invocation.getArgument(3, String.class);
            return storedFiles.stream()
                .filter(file -> file.getTaskId().equals(taskId)
                    && file.getUserId().equals(userId)
                    && file.getArtifactType().equals(artifactType)
                    && file.getLanguage().equals(language))
                .findFirst()
                .orElse(null);
        });
        when(mapper.deleteByScope(anyString(), anyLong(), anyString(), anyString())).thenAnswer(invocation -> {
            ArtifactFile old = mapper.selectByScope(
                invocation.getArgument(0, String.class),
                invocation.getArgument(1, Long.class),
                invocation.getArgument(2, String.class),
                invocation.getArgument(3, String.class)
            );
            if (old == null) {
                return 0;
            }
            storedFiles.remove(old);
            return 1;
        });
        when(mapper.insert(any(ArtifactFile.class))).thenAnswer(invocation -> {
            ArtifactFile file = invocation.getArgument(0, ArtifactFile.class);
            file.setId(id.getAndIncrement());
            storedFiles.add(file);
            storedFiles.sort(Comparator.comparing(ArtifactFile::getArtifactType));
            return 1;
        });
        return mapper;
    }

    private static Map<String, String> contentTypesByType(List<ArtifactFile> files) {
        Map<String, String> result = new HashMap<>();
        files.forEach(file -> result.put(file.getArtifactType(), file.getContentType()));
        return result;
    }

    private static Map<String, Long> countsByType(List<ArtifactFile> files) {
        Map<String, Long> result = new HashMap<>();
        files.forEach(file -> result.merge(file.getArtifactType(), 1L, Long::sum));
        return result;
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

    private static final class RecordingSrtArtifactService implements SrtArtifactService {

        private final List<PipelineAnalysisTaskStepName> executed;
        private final SrtArtifactService delegate;

        private RecordingSrtArtifactService(
            List<PipelineAnalysisTaskStepName> executed,
            SrtArtifactService delegate
        ) {
            this.executed = executed;
            this.delegate = delegate;
        }

        @Override
        public com.example.courselingo.artifact.dto.ArtifactFileView generateSrtArtifact(
            GenerateSrtArtifactCommand command
        ) {
            executed.add(PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS);
            return delegate.generateSrtArtifact(command);
        }
    }

    private static final class ArtifactQueryFixtures implements
        SubtitleSegmentQueryService,
        SubtitleTranslationQueryService,
        LearningPackageQueryService {

        @Override
        public List<SubtitleSegmentView> listByTaskId(String taskId, Long userId) {
            return List.of(
                new SubtitleSegmentView(
                    taskId,
                    0,
                    0,
                    1200,
                    "en",
                    "hello",
                    "fake-asr",
                    now(),
                    now()
                ),
                new SubtitleSegmentView(
                    taskId,
                    1,
                    1200,
                    2400,
                    "en",
                    "world",
                    "fake-asr",
                    now(),
                    now()
                )
            );
        }

        @Override
        public long countByTaskId(String taskId, Long userId) {
            return 2;
        }

        @Override
        public List<SubtitleTranslationSegmentView> listTranslations(
            String taskId,
            Long userId,
            String targetLanguage
        ) {
            return List.of(
                new SubtitleTranslationSegmentView(
                    taskId,
                    0,
                    0,
                    1200,
                    "en",
                    targetLanguage,
                    "Hello translated",
                    "fake-llm",
                    now(),
                    now()
                ),
                new SubtitleTranslationSegmentView(
                    taskId,
                    1,
                    1200,
                    2400,
                    "en",
                    targetLanguage,
                    "World translated",
                    "fake-llm",
                    now(),
                    now()
                )
            );
        }

        @Override
        public long countByTaskIdAndLanguage(String taskId, Long userId, String targetLanguage) {
            return 2;
        }

        @Override
        public Optional<LearningPackageView> getByTaskAndLanguage(
            String taskId,
            Long userId,
            String targetLanguage
        ) {
            return Optional.of(new LearningPackageView(
                taskId,
                "en",
                targetLanguage,
                "Course Title",
                "Course summary",
                "[{\"index\":1,\"text\":\"Point\"}]",
                "[{\"term\":\"Term\",\"definition\":\"Definition\",\"translation\":\"Translated Term\"}]",
                "[{\"question\":\"Question\",\"answer\":\"Answer\"}]",
                "fake-llm",
                "1.0",
                now(),
                now()
            ));
        }
    }

    private static LocalDateTime now() {
        return LocalDateTime.ofInstant(FIXED_CLOCK.instant(), FIXED_CLOCK.getZone());
    }

    private static final class FakeStorageService implements StorageService {

        private final Map<String, byte[]> contents = new HashMap<>();

        @Override
        public void putObject(String objectKey, Path sourceFile, long sizeBytes, String contentType) {
            try {
                byte[] bytes = Files.readAllBytes(sourceFile);
                assertThat(bytes).hasSize((int) sizeBytes);
                contents.put(objectKey, bytes);
            } catch (Exception exception) {
                throw new IllegalStateException("fake artifact storage write failed", exception);
            }
        }

        @Override
        public boolean objectExists(String objectKey) {
            return contents.containsKey(objectKey);
        }

        @Override
        public InputStream openObject(String objectKey) {
            byte[] bytes = contents.get(objectKey);
            if (bytes == null) {
                throw new IllegalStateException("fake artifact storage object missing");
            }
            return new ByteArrayInputStream(bytes);
        }

        @Override
        public void deleteObject(String objectKey) {
            contents.remove(objectKey);
        }
    }
}
