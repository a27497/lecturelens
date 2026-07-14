package com.example.courselingo.artifact;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.dto.ArtifactFileView;
import com.example.courselingo.artifact.service.ArtifactFileService;
import com.example.courselingo.artifact.service.GenerateJsonArtifactCommand;
import com.example.courselingo.artifact.service.JsonArtifactService;
import com.example.courselingo.artifact.service.JsonArtifactServiceImpl;
import com.example.courselingo.artifact.service.JsonLearningPackageExporter;
import com.example.courselingo.artifact.service.SaveArtifactFileCommand;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.learning.dto.LearningPackageView;
import com.example.courselingo.learning.service.LearningPackageQueryService;
import com.example.courselingo.subtitle.dto.SubtitleSegmentView;
import com.example.courselingo.subtitle.dto.SubtitleTranslationSegmentView;
import com.example.courselingo.subtitle.service.SubtitleSegmentQueryService;
import com.example.courselingo.subtitle.service.SubtitleTranslationQueryService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class JsonArtifactServiceTest {

    private FakeSubtitleSegmentQueryService sourceQueryService;
    private FakeSubtitleTranslationQueryService translationQueryService;
    private FakeLearningPackageQueryService learningPackageQueryService;
    private FakeArtifactFileService artifactFileService;
    private JsonArtifactService service;

    @BeforeEach
    void setUp() {
        sourceQueryService = new FakeSubtitleSegmentQueryService();
        translationQueryService = new FakeSubtitleTranslationQueryService();
        learningPackageQueryService = new FakeLearningPackageQueryService();
        artifactFileService = new FakeArtifactFileService();
        service = new JsonArtifactServiceImpl(
            sourceQueryService,
            translationQueryService,
            learningPackageQueryService,
            artifactFileService,
            new JsonLearningPackageExporter(new ObjectMapper())
        );
    }

    @Test
    void generatesJsonArtifactFromCurrentUsersPersistedResults() {
        sourceQueryService.views = List.of(source("task_1", 0, 0, 1_000, "Source"));
        translationQueryService.views = List.of(translation("task_1", 0, 0, 1_000, "en", "zh-CN", "Translated"));
        learningPackageQueryService.view = Optional.of(learningPackage("task_1", "zh-CN"));

        ArtifactFileView view = service.generateJsonArtifact(new GenerateJsonArtifactCommand("task_1", 42L, "zh-CN"));

        assertThat(sourceQueryService.queries).containsExactly(new SourceQuery("task_1", 42L));
        assertThat(translationQueryService.queries).containsExactly(new TranslationQuery("task_1", 42L, "zh-CN"));
        assertThat(learningPackageQueryService.queries).containsExactly(new LearningPackageQuery("task_1", 42L, "zh-CN"));
        SaveArtifactFileCommand saved = artifactFileService.commands.getFirst();
        assertThat(saved.taskId()).isEqualTo("task_1");
        assertThat(saved.userId()).isEqualTo(42L);
        assertThat(saved.artifactType()).isEqualTo(ArtifactType.JSON);
        assertThat(saved.language()).isEqualTo("zh-CN");
        assertThat(saved.fileName()).isEqualTo("task-task_1-zh-CN-learning-package.json");
        assertThat(saved.fileName()).endsWith(".json").doesNotContain("/", "\\", "..", ":");
        assertThat(saved.contentType()).isEqualTo("application/json; charset=utf-8");
        String content = new String(saved.contentBytes(), StandardCharsets.UTF_8);
        assertThat(content)
            .contains("\"schemaVersion\":\"1.0\"")
            .contains("\"taskId\":\"task_1\"")
            .contains("\"targetLanguage\":\"zh-CN\"")
            .contains("\"subtitles\"")
            .contains("\"learningPackage\"")
            .doesNotContain("userId", "objectKey");
        assertThat(view.fileName()).isEqualTo("task-task_1-zh-CN-learning-package.json");
        assertThat(view.toString()).doesNotContain("objectKey", "userId");
    }

    @Test
    void rejectsInvalidCommandFields() {
        assertValidationFailure(new GenerateJsonArtifactCommand("", 42L, "zh-CN"));
        assertValidationFailure(new GenerateJsonArtifactCommand("task_1", null, "zh-CN"));
        assertValidationFailure(new GenerateJsonArtifactCommand("task_1", 0L, "zh-CN"));
        assertValidationFailure(new GenerateJsonArtifactCommand("task_1", 42L, ""));
        assertValidationFailure(new GenerateJsonArtifactCommand("task_1", 42L, "x".repeat(33)));
        assertValidationFailure(new GenerateJsonArtifactCommand("task/1", 42L, "zh-CN"));
        assertValidationFailure(new GenerateJsonArtifactCommand("task_1", 42L, "..\\zh-CN"));
    }

    @Test
    void failsWhenAnyRequiredPersistedResultIsMissingOrInconsistent() {
        translationQueryService.views = List.of(translation("task_1", 0, 0, 1_000, "en", "zh-CN", "Translated"));
        learningPackageQueryService.view = Optional.of(learningPackage("task_1", "zh-CN"));

        assertThatThrownBy(() -> service.generateJsonArtifact(new GenerateJsonArtifactCommand("task_1", 42L, "zh-CN")))
            .isInstanceOf(BusinessException.class)
            .hasMessage("JSON source subtitles are required");
        assertThat(artifactFileService.commands).isEmpty();

        sourceQueryService.views = List.of(source("task_1", 0, 0, 1_000, "Source"));
        translationQueryService.views = List.of();
        service.generateJsonArtifact(new GenerateJsonArtifactCommand("task_1", 42L, "zh-CN"));
        assertThat(artifactFileService.commands.getLast().contentBytes())
            .asString(java.nio.charset.StandardCharsets.UTF_8)
            .contains("\"translatedText\":\"\"");

        translationQueryService.views = List.of(translation("task_1", 1, 0, 1_000, "en", "zh-CN", "Translated"));
        assertThatThrownBy(() -> service.generateJsonArtifact(new GenerateJsonArtifactCommand("task_1", 42L, "zh-CN")))
            .isInstanceOf(BusinessException.class)
            .hasMessage("JSON subtitle segments are inconsistent");

        translationQueryService.views = List.of(translation("task_1", 0, 0, 1_000, "en", "zh-CN", "Translated"));
        learningPackageQueryService.view = Optional.empty();
        assertThatThrownBy(() -> service.generateJsonArtifact(new GenerateJsonArtifactCommand("task_1", 42L, "zh-CN")))
            .isInstanceOf(BusinessException.class)
            .hasMessage("JSON learning package is required");
    }

    @Test
    void keepsUserAndLanguageScopesIsolated() {
        sourceQueryService.views = List.of(source("task_1", 0, 0, 1_000, "Source"));
        translationQueryService.views = List.of(translation("task_1", 0, 0, 1_000, "en", "ja-JP", "Translated"));
        learningPackageQueryService.view = Optional.of(learningPackage("task_1", "ja-JP"));

        service.generateJsonArtifact(new GenerateJsonArtifactCommand("task_1", 7L, "ja-JP"));

        assertThat(sourceQueryService.queries).containsExactly(new SourceQuery("task_1", 7L));
        assertThat(translationQueryService.queries).containsExactly(new TranslationQuery("task_1", 7L, "ja-JP"));
        assertThat(learningPackageQueryService.queries).containsExactly(new LearningPackageQuery("task_1", 7L, "ja-JP"));
        SaveArtifactFileCommand saved = artifactFileService.commands.getFirst();
        assertThat(saved.userId()).isEqualTo(7L);
        assertThat(saved.language()).isEqualTo("ja-JP");
        assertThat(saved.fileName()).isEqualTo("task-task_1-ja-JP-learning-package.json");
    }

    @Test
    void boundariesDoNotUseStorageMapperRunnerMqAiOrOtherArtifactFormats() throws Exception {
        String source = java.nio.file.Files.readString(java.nio.file.Path.of(
            "src/main/java/com/example/courselingo/artifact/service/JsonArtifactServiceImpl.java"
        ));

        assertThat(source)
            .contains("ArtifactFileService")
            .doesNotContain("StorageService")
            .doesNotContain("ArtifactFileMapper")
            .doesNotContain("AnalysisTaskRunner")
            .doesNotContain("RocketMQ")
            .doesNotContain("LangChain4j")
            .doesNotContain("OpenAi")
            .doesNotContain("Ffmpeg")
            .doesNotContain("SpeechToTextProvider")
            .doesNotContain("SiliconFlow")
            .doesNotContain("MockAsr")
            .doesNotContain("ai_call_record")
            .doesNotContain("SRT")
            .doesNotContain("VTT")
            .doesNotContain("MARKDOWN");
    }

    private void assertValidationFailure(GenerateJsonArtifactCommand command) {
        assertThatThrownBy(() -> service.generateJsonArtifact(command))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("JSON");
    }

    private static LearningPackageView learningPackage(String taskId, String targetLanguage) {
        return new LearningPackageView(
            taskId,
            "en",
            targetLanguage,
            "Course Title",
            "Course summary",
            "[{\"index\":1,\"text\":\"Point\"}]",
            "[]",
            "[]",
            "fake",
            "learning-package.v1",
            LocalDateTime.parse("2026-06-28T00:00:00"),
            LocalDateTime.parse("2026-06-28T00:00:00")
        );
    }

    private static SubtitleSegmentView source(
        String taskId,
        int segmentIndex,
        long startMillis,
        long endMillis,
        String text
    ) {
        return new SubtitleSegmentView(
            taskId,
            segmentIndex,
            startMillis,
            endMillis,
            "en",
            text,
            "fake",
            LocalDateTime.parse("2026-06-28T00:00:00"),
            LocalDateTime.parse("2026-06-28T00:00:00")
        );
    }

    private static SubtitleTranslationSegmentView translation(
        String taskId,
        int segmentIndex,
        long startMillis,
        long endMillis,
        String sourceLanguage,
        String targetLanguage,
        String translatedText
    ) {
        return new SubtitleTranslationSegmentView(
            taskId,
            segmentIndex,
            startMillis,
            endMillis,
            sourceLanguage,
            targetLanguage,
            translatedText,
            "fake",
            LocalDateTime.parse("2026-06-28T00:00:00"),
            LocalDateTime.parse("2026-06-28T00:00:00")
        );
    }

    private record SourceQuery(String taskId, Long userId) {
    }

    private record TranslationQuery(String taskId, Long userId, String targetLanguage) {
    }

    private record LearningPackageQuery(String taskId, Long userId, String targetLanguage) {
    }

    private static final class FakeSubtitleSegmentQueryService implements SubtitleSegmentQueryService {
        private final List<SourceQuery> queries = new ArrayList<>();
        private List<SubtitleSegmentView> views = List.of();

        @Override
        public List<SubtitleSegmentView> listByTaskId(String taskId, Long userId) {
            queries.add(new SourceQuery(taskId, userId));
            return views;
        }

        @Override
        public long countByTaskId(String taskId, Long userId) {
            return views.size();
        }
    }

    private static final class FakeSubtitleTranslationQueryService implements SubtitleTranslationQueryService {
        private final List<TranslationQuery> queries = new ArrayList<>();
        private List<SubtitleTranslationSegmentView> views = List.of();

        @Override
        public List<SubtitleTranslationSegmentView> listTranslations(String taskId, Long userId, String targetLanguage) {
            queries.add(new TranslationQuery(taskId, userId, targetLanguage));
            return views;
        }

        @Override
        public long countByTaskIdAndLanguage(String taskId, Long userId, String targetLanguage) {
            return views.size();
        }
    }

    private static final class FakeLearningPackageQueryService implements LearningPackageQueryService {
        private final List<LearningPackageQuery> queries = new ArrayList<>();
        private Optional<LearningPackageView> view = Optional.empty();

        @Override
        public Optional<LearningPackageView> getByTaskAndLanguage(String taskId, Long userId, String targetLanguage) {
            queries.add(new LearningPackageQuery(taskId, userId, targetLanguage));
            return view;
        }

        @Override
        public long countByTaskIdAndLanguage(String taskId, Long userId, String targetLanguage) {
            return view.isPresent() ? 1 : 0;
        }
    }

    private static final class FakeArtifactFileService implements ArtifactFileService {
        private final List<SaveArtifactFileCommand> commands = new ArrayList<>();

        @Override
        public ArtifactFileView saveArtifactFile(SaveArtifactFileCommand command) {
            commands.add(command);
            return new ArtifactFileView(
                command.taskId(),
                command.artifactType(),
                command.language(),
                command.fileName(),
                command.contentType(),
                "FAKE",
                command.contentBytes().length,
                "0".repeat(64),
                LocalDateTime.parse("2026-06-28T00:00:00"),
                LocalDateTime.parse("2026-06-28T00:00:00")
            );
        }

        @Override
        public int deleteArtifact(String taskId, Long userId, ArtifactType artifactType, String language) {
            return 0;
        }
    }
}
