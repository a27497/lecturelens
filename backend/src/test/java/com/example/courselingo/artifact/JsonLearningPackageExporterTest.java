package com.example.courselingo.artifact;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.artifact.service.JsonLearningPackageExporter;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.learning.dto.LearningPackageView;
import com.example.courselingo.subtitle.dto.SubtitleSegmentView;
import com.example.courselingo.subtitle.dto.SubtitleTranslationSegmentView;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;

class JsonLearningPackageExporterTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final JsonLearningPackageExporter exporter = new JsonLearningPackageExporter(objectMapper);

    @Test
    void exportsStableJsonPayloadWithSortedSubtitlesAndLearningPackage() throws Exception {
        String json = exporter.export(
            "task_1",
            "zh-CN",
            List.of(
                source(1, 3_000, 6_000, "Second source"),
                source(0, 0, 3_000, "First\nsource")
            ),
            List.of(
                translation(1, 3_000, 6_000, "Second translation"),
                translation(0, 0, 3_000, "First\ttranslation")
            ),
            learningPackage(
                "Course\u0000 Title",
                "Course\r\nsummary",
                "[{\"index\":2,\"text\":\"Second point\"},{\"index\":1,\"text\":\"First point\"}]",
                "[{\"term\":\"Term\",\"definition\":\"Definition\",\"translation\":\"Translation\"}]",
                "[{\"question\":\"Question?\",\"answer\":\"Answer.\"}]"
            )
        );

        JsonNode root = objectMapper.readTree(json);
        assertThat(root.fieldNames()).toIterable().containsExactly(
            "schemaVersion",
            "taskId",
            "targetLanguage",
            "subtitles",
            "learningPackage"
        );
        assertThat(root.get("schemaVersion").asText()).isEqualTo("1.0");
        assertThat(root.get("taskId").asText()).isEqualTo("task_1");
        assertThat(root.get("targetLanguage").asText()).isEqualTo("zh-CN");
        assertThat(root.get("subtitles")).hasSize(2);
        assertThat(root.get("subtitles").get(0).fieldNames()).toIterable().containsExactly(
            "index",
            "startMillis",
            "endMillis",
            "sourceText",
            "translatedText"
        );
        assertThat(root.get("subtitles").get(0).get("index").asInt()).isEqualTo(0);
        assertThat(root.get("subtitles").get(0).get("sourceText").asText()).isEqualTo("First source");
        assertThat(root.get("subtitles").get(0).get("translatedText").asText()).isEqualTo("First translation");
        JsonNode learningPackage = root.get("learningPackage");
        assertThat(learningPackage.fieldNames()).toIterable().containsExactly(
            "title",
            "summary",
            "keyPoints",
            "glossary",
            "qa"
        );
        assertThat(learningPackage.get("title").asText()).isEqualTo("Course Title");
        assertThat(learningPackage.get("summary").asText()).isEqualTo("Course summary");
        assertThat(learningPackage.get("keyPoints").get(0).get("index").asInt()).isEqualTo(1);
        assertThat(learningPackage.get("glossary").get(0).get("term").asText()).isEqualTo("Term");
        assertThat(learningPackage.get("qa").get(0).get("question").asText()).isEqualTo("Question?");
        assertThat(json)
            .doesNotContain("userId")
            .doesNotContain("objectKey")
            .doesNotContain("token")
            .doesNotContain("secret")
            .doesNotContain("api key")
            .doesNotContain("Authorization")
            .doesNotContain("C:\\Users\\")
            .doesNotContain("\u0000", "\t", "\r");
    }

    @Test
    void rejectsEmptyInputsMismatchedSegmentsInvalidLearningPackageAndSensitiveText() {
        assertThatThrownBy(() -> exporter.export(
            "task_1",
            "zh-CN",
            List.of(),
            List.of(translation(0, 0, 1_000, "Translated")),
            validLearningPackage()
        ))
            .isInstanceOf(BusinessException.class)
            .hasMessage("JSON source subtitles are required");

        String fallbackJson = exporter.export(
            "task_1",
            "zh-CN",
            List.of(source(0, 0, 1_000, "Source")),
            List.of(),
            validLearningPackage()
        );
        assertThat(fallbackJson).contains("\"translatedText\":\"\"");

        assertThatThrownBy(() -> exporter.export(
            "task_1",
            "zh-CN",
            List.of(source(0, 0, 1_000, "Source")),
            List.of(translation(1, 0, 1_000, "Translated")),
            validLearningPackage()
        ))
            .isInstanceOf(BusinessException.class)
            .hasMessage("JSON subtitle segments are inconsistent");

        assertThatThrownBy(() -> exporter.export(
            "task_1",
            "zh-CN",
            List.of(source(0, 0, 1_000, "Source")),
            List.of(translation(0, 0, 1_000, "Translated"), translation(1, 1_000, 2_000, "Extra")),
            validLearningPackage()
        ))
            .isInstanceOf(BusinessException.class)
            .hasMessage("JSON subtitle segments are inconsistent");

        assertThatThrownBy(() -> exporter.export(
            "task_1",
            "zh-CN",
            List.of(source(0, 0, 1_000, "Source")),
            List.of(translation(0, 0, 1_000, "Translated")),
            learningPackage("Title", "Summary", "not-json", "[]", "[]")
        ))
            .isInstanceOf(BusinessException.class)
            .hasMessage("JSON learning package content is invalid");

        assertThatThrownBy(() -> exporter.export(
            "task_1",
            "zh-CN",
            List.of(source(0, 0, 1_000, "token abc123")),
            List.of(translation(0, 0, 1_000, "Translated")),
            validLearningPackage()
        ))
            .isInstanceOf(BusinessException.class)
            .hasMessage("JSON artifact content is invalid")
            .satisfies(error -> assertThat(error.getMessage().toLowerCase())
                .doesNotContain("token", "secret", "api key", "authorization", "c:\\"));
    }

    @Test
    void exportsJsonWhenGlossaryTranslationIsMissingAndSkipsFullyEmptyGlossaryItems() throws Exception {
        String json = exporter.export(
            "task_1",
            "zh-CN",
            List.of(source(0, 0, 1_000, "Source")),
            List.of(),
            learningPackage(
                "Course Title",
                "Course summary",
                "[{\"index\":1,\"text\":\"Point\"}]",
                "[{\"term\":\"HTTP\",\"definition\":\"Network protocol\",\"translation\":\"\"},"
                    + "{\"term\":\"API\",\"definition\":\"\",\"translation\":\"接口\"},"
                    + "{\"term\":\"\",\"definition\":\"\",\"translation\":\"\"}]",
                "[]"
            )
        );

        JsonNode glossary = objectMapper.readTree(json).get("learningPackage").get("glossary");
        assertThat(glossary).hasSize(2);
        assertThat(glossary.get(0).get("term").asText()).isEqualTo("HTTP");
        assertThat(glossary.get(0).get("definition").asText()).isEqualTo("Network protocol");
        assertThat(glossary.get(0).get("translation").asText()).isEmpty();
        assertThat(glossary.get(1).get("term").asText()).isEqualTo("API");
        assertThat(glossary.get(1).get("definition").asText()).isEmpty();
        assertThat(glossary.get(1).get("translation").asText()).isEqualTo("接口");
    }

    private static LearningPackageView validLearningPackage() {
        return learningPackage(
            "Course Title",
            "Course summary",
            "[{\"index\":1,\"text\":\"Point\"}]",
            "[]",
            "[]"
        );
    }

    private static LearningPackageView learningPackage(
        String title,
        String summary,
        String keyPointsJson,
        String glossaryJson,
        String qaJson
    ) {
        return new LearningPackageView(
            "task_1",
            "en",
            "zh-CN",
            title,
            summary,
            keyPointsJson,
            glossaryJson,
            qaJson,
            "fake",
            "learning-package.v1",
            LocalDateTime.parse("2026-06-28T00:00:00"),
            LocalDateTime.parse("2026-06-28T00:00:00")
        );
    }

    private static SubtitleSegmentView source(int index, long startMillis, long endMillis, String text) {
        return new SubtitleSegmentView(
            "task_1",
            index,
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
        int index,
        long startMillis,
        long endMillis,
        String translatedText
    ) {
        return new SubtitleTranslationSegmentView(
            "task_1",
            index,
            startMillis,
            endMillis,
            "en",
            "zh-CN",
            translatedText,
            "fake",
            LocalDateTime.parse("2026-06-28T00:00:00"),
            LocalDateTime.parse("2026-06-28T00:00:00")
        );
    }
}
