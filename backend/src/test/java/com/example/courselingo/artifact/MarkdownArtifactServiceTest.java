package com.example.courselingo.artifact;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.dto.ArtifactFileView;
import com.example.courselingo.artifact.service.ArtifactFileService;
import com.example.courselingo.artifact.service.GenerateMarkdownArtifactCommand;
import com.example.courselingo.artifact.service.MarkdownArtifactService;
import com.example.courselingo.artifact.service.MarkdownArtifactServiceImpl;
import com.example.courselingo.artifact.service.MarkdownLearningPackageFormatter;
import com.example.courselingo.artifact.service.SaveArtifactFileCommand;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.learning.dto.LearningPackageView;
import com.example.courselingo.learning.service.LearningPackageQueryService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class MarkdownArtifactServiceTest {

    private FakeLearningPackageQueryService learningPackageQueryService;
    private FakeArtifactFileService artifactFileService;
    private MarkdownArtifactService service;

    @BeforeEach
    void setUp() {
        learningPackageQueryService = new FakeLearningPackageQueryService();
        artifactFileService = new FakeArtifactFileService();
        service = new MarkdownArtifactServiceImpl(
            learningPackageQueryService,
            artifactFileService,
            new MarkdownLearningPackageFormatter(new ObjectMapper())
        );
    }

    @Test
    void generatesMarkdownArtifactFromCurrentUsersLearningPackage() {
        learningPackageQueryService.view = Optional.of(learningPackage("task_1", "zh-CN"));

        ArtifactFileView view = service.generateMarkdownArtifact(
            new GenerateMarkdownArtifactCommand("task_1", 42L, "zh-CN")
        );

        assertThat(learningPackageQueryService.queries).containsExactly(new LearningPackageQuery("task_1", 42L, "zh-CN"));
        SaveArtifactFileCommand saved = artifactFileService.commands.getFirst();
        assertThat(saved.taskId()).isEqualTo("task_1");
        assertThat(saved.userId()).isEqualTo(42L);
        assertThat(saved.artifactType()).isEqualTo(ArtifactType.MARKDOWN);
        assertThat(saved.language()).isEqualTo("zh-CN");
        assertThat(saved.fileName()).isEqualTo("task-task_1-zh-CN-learning-package.md");
        assertThat(saved.fileName()).endsWith(".md").doesNotContain("/", "\\", "..", ":");
        assertThat(saved.contentType()).isEqualTo("text/markdown; charset=utf-8");
        assertThat(new String(saved.contentBytes(), StandardCharsets.UTF_8))
            .startsWith("# Course Title\n\n")
            .contains("## \u6458\u8981")
            .contains("## \u91cd\u70b9")
            .contains("## \u672f\u8bed\u8868")
            .contains("## \u95ee\u7b54")
            .contains("| Term | Definition | Translation |");
        assertThat(view.fileName()).isEqualTo("task-task_1-zh-CN-learning-package.md");
        assertThat(view.toString()).doesNotContain("objectKey", "userId");
    }

    @Test
    void generatesMarkdownWhenGlossaryOptionalFieldsAreMissingAndSkipsEmptyItems() {
        learningPackageQueryService.view = Optional.of(learningPackage(
            "task_1",
            "zh-CN",
            "[{\"term\":\"HTTP\",\"definition\":\"网络协议\",\"translation\":\"\"},"
                + "{\"term\":\"API\",\"definition\":\"\",\"translation\":\"接口\"},"
                + "{\"term\":\"\",\"definition\":\"\",\"translation\":\"\"}]"
        ));

        service.generateMarkdownArtifact(new GenerateMarkdownArtifactCommand("task_1", 42L, "zh-CN"));

        String content = new String(artifactFileService.commands.getFirst().contentBytes(), StandardCharsets.UTF_8);
        assertThat(content)
            .contains("| HTTP | 网络协议 |  |")
            .contains("| API |  | 接口 |");
        assertThat(content).doesNotContain("|  |  |  |");
    }

    @Test
    void rejectsInvalidCommandFields() {
        assertValidationFailure(new GenerateMarkdownArtifactCommand("", 42L, "zh-CN"));
        assertValidationFailure(new GenerateMarkdownArtifactCommand("task_1", null, "zh-CN"));
        assertValidationFailure(new GenerateMarkdownArtifactCommand("task_1", 0L, "zh-CN"));
        assertValidationFailure(new GenerateMarkdownArtifactCommand("task_1", 42L, ""));
        assertValidationFailure(new GenerateMarkdownArtifactCommand("task_1", 42L, "x".repeat(33)));
        assertValidationFailure(new GenerateMarkdownArtifactCommand("task/1", 42L, "zh-CN"));
        assertValidationFailure(new GenerateMarkdownArtifactCommand("task_1", 42L, "..\\zh-CN"));
    }

    @Test
    void failsWhenLearningPackageDoesNotExist() {
        learningPackageQueryService.view = Optional.empty();

        assertThatThrownBy(() -> service.generateMarkdownArtifact(
            new GenerateMarkdownArtifactCommand("task_1", 42L, "zh-CN")
        ))
            .isInstanceOf(BusinessException.class)
            .hasMessage("Markdown learning package is required");
        assertThat(artifactFileService.commands).isEmpty();
    }

    @Test
    void keepsUserAndLanguageScopesIsolated() {
        learningPackageQueryService.view = Optional.of(learningPackage("task_1", "ja-JP"));

        service.generateMarkdownArtifact(new GenerateMarkdownArtifactCommand("task_1", 7L, "ja-JP"));

        assertThat(learningPackageQueryService.queries).containsExactly(new LearningPackageQuery("task_1", 7L, "ja-JP"));
        SaveArtifactFileCommand saved = artifactFileService.commands.getFirst();
        assertThat(saved.userId()).isEqualTo(7L);
        assertThat(saved.language()).isEqualTo("ja-JP");
        assertThat(saved.fileName()).isEqualTo("task-task_1-ja-JP-learning-package.md");
    }

    @Test
    void boundariesDoNotUseStorageMapperRunnerMqAiOrOtherArtifactFormats() throws Exception {
        String source = java.nio.file.Files.readString(java.nio.file.Path.of(
            "src/main/java/com/example/courselingo/artifact/service/MarkdownArtifactServiceImpl.java"
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
            .doesNotContain("JSON");
    }

    private void assertValidationFailure(GenerateMarkdownArtifactCommand command) {
        assertThatThrownBy(() -> service.generateMarkdownArtifact(command))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("Markdown");
    }

    private static LearningPackageView learningPackage(String taskId, String targetLanguage) {
        return learningPackage(
            taskId,
            targetLanguage,
            "[{\"term\":\"Term\",\"definition\":\"Definition\",\"translation\":\"Translation\"}]"
        );
    }

    private static LearningPackageView learningPackage(String taskId, String targetLanguage, String glossaryJson) {
        return new LearningPackageView(
            taskId,
            "en",
            targetLanguage,
            "Course Title",
            "Course summary",
            "[{\"index\":1,\"text\":\"Point\"}]",
            glossaryJson,
            "[{\"question\":\"Question?\",\"answer\":\"Answer.\"}]",
            "fake",
            "learning-package.v1",
            LocalDateTime.parse("2026-06-28T00:00:00"),
            LocalDateTime.parse("2026-06-28T00:00:00")
        );
    }

    private record LearningPackageQuery(String taskId, Long userId, String targetLanguage) {
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
