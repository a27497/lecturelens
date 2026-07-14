package com.example.courselingo.artifact;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.dto.ArtifactFileView;
import com.example.courselingo.artifact.service.ArtifactFileService;
import com.example.courselingo.artifact.service.GenerateSrtArtifactCommand;
import com.example.courselingo.artifact.service.SaveArtifactFileCommand;
import com.example.courselingo.artifact.service.SrtArtifactService;
import com.example.courselingo.artifact.service.SrtArtifactServiceImpl;
import com.example.courselingo.artifact.service.SrtFormatter;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.subtitle.dto.SubtitleTranslationSegmentView;
import com.example.courselingo.subtitle.dto.SubtitleSegmentView;
import com.example.courselingo.subtitle.service.SubtitleSegmentQueryService;
import com.example.courselingo.subtitle.service.SubtitleTranslationQueryService;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class SrtArtifactServiceTest {

    private FakeSubtitleTranslationQueryService subtitleQueryService;
    private FakeSubtitleSegmentQueryService sourceSubtitleQueryService;
    private FakeArtifactFileService artifactFileService;
    private SrtArtifactService service;

    @BeforeEach
    void setUp() {
        subtitleQueryService = new FakeSubtitleTranslationQueryService();
        sourceSubtitleQueryService = new FakeSubtitleSegmentQueryService();
        artifactFileService = new FakeArtifactFileService();
        service = new SrtArtifactServiceImpl(subtitleQueryService, artifactFileService, new SrtFormatter());
    }

    @Test
    void generatesSrtArtifactFromCurrentUsersTranslatedSubtitles() {
        subtitleQueryService.views = List.of(
            translation("task_1", 1, 3_000, 6_000, "en", "zh-CN", "第二句"),
            translation("task_1", 0, 0, 3_000, "en", "zh-CN", "第一句")
        );

        ArtifactFileView view = service.generateSrtArtifact(new GenerateSrtArtifactCommand("task_1", 42L, "zh-CN"));

        assertThat(subtitleQueryService.queries).containsExactly(new SubtitleQuery("task_1", 42L, "zh-CN"));
        SaveArtifactFileCommand saved = artifactFileService.commands.getFirst();
        assertThat(saved.taskId()).isEqualTo("task_1");
        assertThat(saved.userId()).isEqualTo(42L);
        assertThat(saved.artifactType()).isEqualTo(ArtifactType.SRT);
        assertThat(saved.language()).isEqualTo("zh-CN");
        assertThat(saved.fileName()).isEqualTo("task-task_1-zh-CN.srt");
        assertThat(saved.fileName()).doesNotContain("/", "\\", "..", ":");
        assertThat(saved.contentType()).isEqualTo("application/x-subrip");
        assertThat(new String(saved.contentBytes(), StandardCharsets.UTF_8)).isEqualTo(
            "1\n"
                + "00:00:00,000 --> 00:00:03,000\n"
                + "第一句\n\n"
                + "2\n"
                + "00:00:03,000 --> 00:00:06,000\n"
                + "第二句\n\n"
        );
        assertThat(view.fileName()).isEqualTo("task-task_1-zh-CN.srt");
        assertThat(view.toString()).doesNotContain("objectKey", "userId");
    }

    @Test
    void rejectsInvalidCommandFields() {
        assertValidationFailure(new GenerateSrtArtifactCommand("", 42L, "zh-CN"));
        assertValidationFailure(new GenerateSrtArtifactCommand("task_1", null, "zh-CN"));
        assertValidationFailure(new GenerateSrtArtifactCommand("task_1", 0L, "zh-CN"));
        assertValidationFailure(new GenerateSrtArtifactCommand("task_1", 42L, ""));
        assertValidationFailure(new GenerateSrtArtifactCommand("task_1", 42L, "x".repeat(33)));
        assertValidationFailure(new GenerateSrtArtifactCommand("task/1", 42L, "zh-CN"));
        assertValidationFailure(new GenerateSrtArtifactCommand("task_1", 42L, "..\\zh-CN"));
    }

    @Test
    void failsWhenTranslatedSubtitlesAreEmpty() {
        subtitleQueryService.views = List.of();

        assertThatThrownBy(() -> service.generateSrtArtifact(new GenerateSrtArtifactCommand("task_1", 42L, "zh-CN")))
            .isInstanceOf(BusinessException.class)
            .hasMessage("SRT subtitles are required");
        assertThat(artifactFileService.commands).isEmpty();
    }

    @Test
    void fallsBackToSourceSubtitlesWhenTranslatedSubtitlesAreEmpty() {
        service = new SrtArtifactServiceImpl(
            subtitleQueryService,
            sourceSubtitleQueryService,
            artifactFileService,
            new SrtFormatter()
        );
        subtitleQueryService.views = List.of();
        sourceSubtitleQueryService.views = List.of(source("task_1", 0, 0, 1_000, "Source line"));

        service.generateSrtArtifact(new GenerateSrtArtifactCommand("task_1", 42L, "zh-CN"));

        String content = new String(artifactFileService.commands.getFirst().contentBytes(), StandardCharsets.UTF_8);
        assertThat(content).contains("Source line");
        assertThat(sourceSubtitleQueryService.queries).containsExactly(new SourceQuery("task_1", 42L));
    }

    @Test
    void keepsUserAndLanguageScopesIsolated() {
        subtitleQueryService.views = List.of(translation("task_1", 0, 0, 1_000, "en", "ja-JP", "こんにちは"));

        service.generateSrtArtifact(new GenerateSrtArtifactCommand("task_1", 7L, "ja-JP"));

        assertThat(subtitleQueryService.queries).containsExactly(new SubtitleQuery("task_1", 7L, "ja-JP"));
        SaveArtifactFileCommand saved = artifactFileService.commands.getFirst();
        assertThat(saved.userId()).isEqualTo(7L);
        assertThat(saved.language()).isEqualTo("ja-JP");
        assertThat(saved.fileName()).isEqualTo("task-task_1-ja-JP.srt");
    }

    @Test
    void boundariesDoNotUseStorageMapperRunnerMqAiOrOtherArtifactFormats() throws Exception {
        String source = java.nio.file.Files.readString(java.nio.file.Path.of(
            "src/main/java/com/example/courselingo/artifact/service/SrtArtifactServiceImpl.java"
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
            .doesNotContain("VTT")
            .doesNotContain("MARKDOWN")
            .doesNotContain("JSON");
    }

    private void assertValidationFailure(GenerateSrtArtifactCommand command) {
        assertThatThrownBy(() -> service.generateSrtArtifact(command))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("SRT");
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

    private record SubtitleQuery(String taskId, Long userId, String language) {
    }

    private record SourceQuery(String taskId, Long userId) {
    }

    private static final class FakeSubtitleTranslationQueryService implements SubtitleTranslationQueryService {
        private final List<SubtitleQuery> queries = new ArrayList<>();
        private List<SubtitleTranslationSegmentView> views = List.of();

        @Override
        public List<SubtitleTranslationSegmentView> listTranslations(String taskId, Long userId, String targetLanguage) {
            queries.add(new SubtitleQuery(taskId, userId, targetLanguage));
            return views;
        }

        @Override
        public long countByTaskIdAndLanguage(String taskId, Long userId, String targetLanguage) {
            return views.size();
        }
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
