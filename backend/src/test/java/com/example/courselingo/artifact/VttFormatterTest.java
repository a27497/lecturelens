package com.example.courselingo.artifact;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.artifact.service.VttCue;
import com.example.courselingo.artifact.service.VttFormatter;
import com.example.courselingo.common.exception.BusinessException;
import java.util.List;
import org.junit.jupiter.api.Test;

class VttFormatterTest {

    private final VttFormatter formatter = new VttFormatter();

    @Test
    void formatsSingleCueWithStandardWebVttShape() {
        String vtt = formatter.format(List.of(new VttCue(0, 0, 3_000, "Hello \u4f60\u597d")));

        assertThat(vtt).isEqualTo(
            "WEBVTT\n\n"
                + "00:00:00.000 --> 00:00:03.000\n"
                + "Hello \u4f60\u597d\n\n"
        );
    }

    @Test
    void formatsMultipleCuesWithoutSrtNumbersAndSortedSegmentIndex() {
        String vtt = formatter.format(List.of(
            new VttCue(2, 6_000, 9_000, "third"),
            new VttCue(0, 0, 3_000, "first"),
            new VttCue(1, 3_000, 6_000, "second")
        ));

        assertThat(vtt).isEqualTo(
            "WEBVTT\n\n"
                + "00:00:00.000 --> 00:00:03.000\n"
                + "first\n\n"
                + "00:00:03.000 --> 00:00:06.000\n"
                + "second\n\n"
                + "00:00:06.000 --> 00:00:09.000\n"
                + "third\n\n"
        );
        assertThat(vtt).doesNotContain("00:00:00,000", "\n1\n", "\n2\n", "\n3\n");
    }

    @Test
    void formatsHourAndMillisecondValuesWithThreeMillisecondDigits() {
        String vtt = formatter.format(List.of(new VttCue(0, 3_723_004, 3_724_015, "timed")));

        assertThat(vtt).contains("01:02:03.004 --> 01:02:04.015");
    }

    @Test
    void rejectsEmptyCueList() {
        assertThatThrownBy(() -> formatter.format(List.of()))
            .isInstanceOf(BusinessException.class)
            .hasMessage("VTT subtitles are required");
    }

    @Test
    void rejectsInvalidTimesAndBlankText() {
        assertThatThrownBy(() -> formatter.format(List.of(new VttCue(0, -1, 1_000, "text"))))
            .isInstanceOf(BusinessException.class)
            .hasMessage("VTT subtitle time range is invalid");
        assertThatThrownBy(() -> formatter.format(List.of(new VttCue(0, 2_000, 1_000, "text"))))
            .isInstanceOf(BusinessException.class)
            .hasMessage("VTT subtitle time range is invalid");
        assertThatThrownBy(() -> formatter.format(List.of(new VttCue(0, 0, 1_000, " "))))
            .isInstanceOf(BusinessException.class)
            .hasMessage("VTT subtitle text is required");
    }

    @Test
    void normalizesControlCharactersMultilineTextAndCueArrowText() {
        String vtt = formatter.format(List.of(new VttCue(0, 0, 1_000, "Hello\u0000\r\nWorld\t! a --> b")));

        assertThat(vtt).contains("Hello World ! a -- > b");
        assertThat(vtt).doesNotContain("\u0000", "\t", "a --> b");
    }

    @Test
    void rejectsSensitiveTextWithoutLeakingSensitiveValue() {
        assertSanitizedFailure("Authorization Bearer abc123");
        assertSanitizedFailure("token abc123");
        assertSanitizedFailure("secret abc123");
        assertSanitizedFailure("api key abc123");
        assertSanitizedFailure("C:\\Users\\demo\\secret.vtt");
        assertSanitizedFailure("/home/demo/secret.vtt");
    }

    private void assertSanitizedFailure(String text) {
        assertThatThrownBy(() -> formatter.format(List.of(new VttCue(0, 0, 1_000, text))))
            .isInstanceOf(BusinessException.class)
            .hasMessage("VTT subtitle text is invalid")
            .satisfies(error -> assertThat(error.getMessage().toLowerCase())
                .doesNotContain("authorization", "token", "secret", "api key", "c:\\", "/home/"));
    }
}
