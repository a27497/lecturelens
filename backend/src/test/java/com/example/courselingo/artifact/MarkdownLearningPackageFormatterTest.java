package com.example.courselingo.artifact;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.artifact.service.MarkdownLearningPackageFormatter;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.learning.dto.LearningPackageView;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;

class MarkdownLearningPackageFormatterTest {

    private final MarkdownLearningPackageFormatter formatter = new MarkdownLearningPackageFormatter(new ObjectMapper());

    @Test
    void formatsCompleteLearningPackageWithStableMarkdownSections() {
        String markdown = formatter.format(learningPackage(
            "Course Title",
            "Course summary",
            "[{\"index\":1,\"text\":\"First point\"},{\"index\":2,\"text\":\"Second point\"}]",
            "[{\"term\":\"Term\",\"definition\":\"Definition\",\"translation\":\"Translation\"}]",
            "[{\"question\":\"Question?\",\"answer\":\"Answer.\"}]"
        ));

        assertThat(markdown).isEqualTo(
            "# Course Title\n\n"
                + "## \u6458\u8981\n\n"
                + "Course summary\n\n"
                + "## \u91cd\u70b9\n\n"
                + "1. First point\n"
                + "2. Second point\n\n"
                + "## \u672f\u8bed\u8868\n\n"
                + "| \u672f\u8bed | \u89e3\u91ca | \u8bd1\u540d |\n"
                + "| --- | --- | --- |\n"
                + "| Term | Definition | Translation |\n\n"
                + "## \u95ee\u7b54\n\n"
                + "### Q1: Question?\n\n"
                + "Answer.\n"
        );
    }

    @Test
    void formatsEmptyGlossaryAndQaWithStableEmptyStateText() {
        String markdown = formatter.format(learningPackage(
            "Course Title",
            "Course summary",
            "[{\"index\":1,\"text\":\"First point\"}]",
            "[]",
            "[]"
        ));

        assertThat(markdown)
            .contains("## \u672f\u8bed\u8868\n\n\u6682\u65e0\u672f\u8bed\n\n")
            .contains("## \u95ee\u7b54\n\n\u6682\u65e0\u95ee\u7b54\n");
    }

    @Test
    void escapesTablePipesAndNormalizesControlCharacters() {
        String markdown = formatter.format(learningPackage(
            "Course\u0000 Title",
            "Course\r\nsummary\ttext",
            "[{\"index\":1,\"text\":\"First\\u0000 point\"}]",
            "[{\"term\":\"A|B\",\"definition\":\"C|D\",\"translation\":\"E|F\"}]",
            "[{\"question\":\"Question\\ntext?\",\"answer\":\"Answer\\ttext.\"}]"
        ));

        assertThat(markdown)
            .contains("# Course Title")
            .contains("Course summary text")
            .contains("First point")
            .contains("| A\\|B | C\\|D | E\\|F |")
            .contains("### Q1: Question text?")
            .contains("Answer text.");
        assertThat(markdown).doesNotContain("\u0000", "\t", "\r");
    }

    @Test
    void rejectsInvalidJsonMissingRequiredContentAndSensitiveValuesWithoutLeakage() {
        assertThatThrownBy(() -> formatter.format(learningPackage(
            "Course Title",
            "Course summary",
            "not-json",
            "[]",
            "[]"
        )))
            .isInstanceOf(BusinessException.class)
            .hasMessage("Markdown learning package content is invalid");

        assertThatThrownBy(() -> formatter.format(learningPackage(
            " ",
            "Course summary",
            "[{\"index\":1,\"text\":\"First point\"}]",
            "[]",
            "[]"
        )))
            .isInstanceOf(BusinessException.class)
            .hasMessage("Markdown title is required");

        assertThatThrownBy(() -> formatter.format(learningPackage(
            "Course Title",
            "Course summary",
            "[]",
            "[]",
            "[]"
        )))
            .isInstanceOf(BusinessException.class)
            .hasMessage("Markdown key points are required");

        assertSanitizedFailure("token abc123");
        assertSanitizedFailure("secret abc123");
        assertSanitizedFailure("api key abc123");
        assertSanitizedFailure("Authorization Bearer abc123");
        assertSanitizedFailure("C:\\Users\\demo\\secret.md");
        assertSanitizedFailure("/home/demo/secret.md");
    }

    private void assertSanitizedFailure(String sensitiveText) {
        assertThatThrownBy(() -> formatter.format(learningPackage(
            "Course Title",
            sensitiveText,
            "[{\"index\":1,\"text\":\"First point\"}]",
            "[]",
            "[]"
        )))
            .isInstanceOf(BusinessException.class)
            .hasMessage("Markdown learning package content is invalid")
            .satisfies(error -> assertThat(error.getMessage().toLowerCase())
                .doesNotContain("authorization", "token", "secret", "api key", "c:\\", "/home/"));
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
}
