package com.example.courselingo.artifact;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.artifact.service.SrtCue;
import com.example.courselingo.artifact.service.SrtFormatter;
import com.example.courselingo.common.exception.BusinessException;
import java.util.List;
import org.junit.jupiter.api.Test;

class SrtFormatterTest {

    private final SrtFormatter formatter = new SrtFormatter();

    @Test
    void formatsSingleCueWithStandardSrtShape() {
        String srt = formatter.format(List.of(new SrtCue(0, 0, 3_000, "Hello 你好")));

        assertThat(srt).isEqualTo(
            "1\n"
                + "00:00:00,000 --> 00:00:03,000\n"
                + "Hello 你好\n\n"
        );
    }

    @Test
    void formatsMultipleCuesWithContinuousOneBasedNumbersAndSortedSegmentIndex() {
        String srt = formatter.format(List.of(
            new SrtCue(2, 6_000, 9_000, "third"),
            new SrtCue(0, 0, 3_000, "first"),
            new SrtCue(1, 3_000, 6_000, "second")
        ));

        assertThat(srt).isEqualTo(
            "1\n"
                + "00:00:00,000 --> 00:00:03,000\n"
                + "first\n\n"
                + "2\n"
                + "00:00:03,000 --> 00:00:06,000\n"
                + "second\n\n"
                + "3\n"
                + "00:00:06,000 --> 00:00:09,000\n"
                + "third\n\n"
        );
    }

    @Test
    void formatsHourAndMillisecondValuesWithThreeMillisecondDigits() {
        String srt = formatter.format(List.of(new SrtCue(0, 3_723_004, 3_724_015, "timed")));

        assertThat(srt).contains("01:02:03,004 --> 01:02:04,015");
    }

    @Test
    void rejectsEmptyCueList() {
        assertThatThrownBy(() -> formatter.format(List.of()))
            .isInstanceOf(BusinessException.class)
            .hasMessage("SRT subtitles are required");
    }

    @Test
    void rejectsInvalidTimesAndBlankText() {
        assertThatThrownBy(() -> formatter.format(List.of(new SrtCue(0, -1, 1_000, "text"))))
            .isInstanceOf(BusinessException.class)
            .hasMessage("SRT subtitle time range is invalid");
        assertThatThrownBy(() -> formatter.format(List.of(new SrtCue(0, 2_000, 1_000, "text"))))
            .isInstanceOf(BusinessException.class)
            .hasMessage("SRT subtitle time range is invalid");
        assertThatThrownBy(() -> formatter.format(List.of(new SrtCue(0, 0, 1_000, " "))))
            .isInstanceOf(BusinessException.class)
            .hasMessage("SRT subtitle text is required");
    }

    @Test
    void normalizesControlCharactersAndMultilineTextToSpaces() {
        String srt = formatter.format(List.of(new SrtCue(0, 0, 1_000, "Hello\u0000\r\nWorld\t!")));

        assertThat(srt).contains("Hello World !");
        assertThat(srt).doesNotContain("\u0000", "\t");
    }

    @Test
    void rejectsSensitiveTextWithoutLeakingSensitiveValue() {
        assertSanitizedFailure("Authorization Bearer abc123");
        assertSanitizedFailure("token abc123");
        assertSanitizedFailure("secret abc123");
        assertSanitizedFailure("api key abc123");
        assertSanitizedFailure("C:\\Users\\demo\\secret.srt");
        assertSanitizedFailure("/home/demo/secret.srt");
    }

    private void assertSanitizedFailure(String text) {
        assertThatThrownBy(() -> formatter.format(List.of(new SrtCue(0, 0, 1_000, text))))
            .isInstanceOf(BusinessException.class)
            .hasMessage("SRT subtitle text is invalid")
            .satisfies(error -> assertThat(error.getMessage().toLowerCase())
                .doesNotContain("authorization", "token", "secret", "api key", "c:\\", "/home/"));
    }
}
