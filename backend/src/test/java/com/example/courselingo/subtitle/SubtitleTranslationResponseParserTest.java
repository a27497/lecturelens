package com.example.courselingo.subtitle;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.service.SubtitleTranslationResponseParser;
import java.util.List;
import org.junit.jupiter.api.Test;

class SubtitleTranslationResponseParserTest {

    private final SubtitleTranslationResponseParser parser = new SubtitleTranslationResponseParser();

    @Test
    void parsesStrictJsonSegmentsBySourceIndex() {
        List<SubtitleTranslationResponseParser.ParsedTranslationSegment> parsed = parser.parse(
            """
                {"segments":[{"index":0,"text":"你好"},{"index":1,"text":"世界"}]}
                """,
            sourceSegments()
        );

        assertThat(parsed).extracting(SubtitleTranslationResponseParser.ParsedTranslationSegment::segmentIndex)
            .containsExactly(0, 1);
        assertThat(parsed).extracting(SubtitleTranslationResponseParser.ParsedTranslationSegment::text)
            .containsExactly("你好", "世界");
    }

    @Test
    void parsesJsonWrappedInMarkdownCodeFence() {
        List<SubtitleTranslationResponseParser.ParsedTranslationSegment> parsed = parser.parse(
            """
                ```json
                {"segments":[{"index":0,"text":"hello"},{"index":1,"text":"world"}]}
                ```
                """,
            sourceSegments()
        );

        assertThat(parsed).extracting(SubtitleTranslationResponseParser.ParsedTranslationSegment::text)
            .containsExactly("hello", "world");
    }

    @Test
    void parsesEscapedJsonStringContent() {
        List<SubtitleTranslationResponseParser.ParsedTranslationSegment> parsed = parser.parse(
            "\"{\\\"segments\\\":[{\\\"index\\\":0,\\\"text\\\":\\\"hello\\\"},{\\\"index\\\":1,\\\"text\\\":\\\"world\\\"}]}\"",
            sourceSegments()
        );

        assertThat(parsed).extracting(SubtitleTranslationResponseParser.ParsedTranslationSegment::text)
            .containsExactly("hello", "world");
    }

    @Test
    void nonJsonContentReportsJsonParseError() {
        assertTranslationFailure("not-json", "JSON_PARSE_ERROR");
    }

    @Test
    void emptySegmentsReportsUnexpectedSchema() {
        assertTranslationFailure("{\"segments\":[]}", "UNEXPECTED_SCHEMA");
    }

    @Test
    void rejectsInvalidJsonEmptySegmentsDuplicateUnknownMissingAndEmptyText() {
        assertTranslationFailure("{not-json");
        assertTranslationFailure("{\"notSegments\":[]}");
        assertTranslationFailure("{\"segments\":[]}");
        assertTranslationFailure("{\"segments\":[{\"index\":0,\"text\":\"你好\"},{\"index\":0,\"text\":\"重复\"}]}");
        assertTranslationFailure("{\"segments\":[{\"index\":0,\"text\":\"你好\"},{\"index\":2,\"text\":\"多余\"}]}");
        assertTranslationFailure("{\"segments\":[{\"index\":0,\"text\":\"你好\"}]}");
        assertTranslationFailure("{\"segments\":[{\"index\":0,\"text\":\" \"},{\"index\":1,\"text\":\"世界\"}]}");
    }

    @Test
    void parserErrorsAreSanitized() {
        assertThatThrownBy(() -> parser.parse(
            "{\"segments\":[{\"index\":0,\"text\":\"token secret api key Authorization C:\\\\Users\\\\demo\"}]}",
            List.of(sourceSegment(0))
        ))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                assertThat(((BusinessException) error).errorCode()).isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
                assertSafe(error.getMessage());
            });
    }

    private void assertTranslationFailure(String json) {
        assertTranslationFailure(json, null);
    }

    private void assertTranslationFailure(String json, String expectedMessage) {
        assertThatThrownBy(() -> parser.parse(json, sourceSegments()))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                assertThat(((BusinessException) error).errorCode()).isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
                if (expectedMessage != null) {
                    assertThat(error.getMessage()).contains(expectedMessage);
                }
                assertSafe(error.getMessage());
            });
    }

    private static List<SubtitleSegment> sourceSegments() {
        return List.of(sourceSegment(0), sourceSegment(1));
    }

    private static SubtitleSegment sourceSegment(int index) {
        SubtitleSegment segment = new SubtitleSegment();
        segment.setTaskId("task_1");
        segment.setUserId(42L);
        segment.setSegmentIndex(index);
        segment.setStartMillis(index * 1000L);
        segment.setEndMillis(index * 1000L + 900L);
        segment.setLanguage("en");
        segment.setText("source " + index);
        return segment;
    }

    private static void assertSafe(String message) {
        assertThat(message).doesNotContain("C:\\");
        assertThat(message.toLowerCase()).doesNotContain("token", "secret", "api key", "authorization");
    }
}
