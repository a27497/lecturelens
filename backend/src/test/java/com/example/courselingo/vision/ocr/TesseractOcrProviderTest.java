package com.example.courselingo.vision.ocr;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class TesseractOcrProviderTest {

    @Test
    void recognizesTextByCallingTesseractWithoutShellAndParsingTsvConfidence() {
        RecordingExecutor executor = new RecordingExecutor(new OcrProcessResult(
            0,
            """
            level	page_num	block_num	par_num	line_num	word_num	left	top	width	height	conf	text
            5	1	1	1	1	1	10	10	20	10	91.5	Course
            5	1	1	1	1	2	35	10	20	10	82.5	Intro
            """,
            "",
            false
        ));
        VisionOcrProperties properties = new VisionOcrProperties();
        properties.setCommand("tesseract");
        properties.setLanguage("chi_sim+eng");
        properties.setTimeoutSeconds(12);

        OcrResult result = new TesseractOcrProvider(properties, executor)
            .recognize(new OcrRequest(Path.of("frame.jpg")));

        assertThat(result.status()).isEqualTo(OcrStatus.SUCCEEDED);
        assertThat(result.text()).isEqualTo("Course Intro");
        assertThat(result.confidence()).isEqualTo(0.87);
        assertThat(executor.commands).containsExactly(List.of(
            "tesseract",
            "frame.jpg",
            "stdout",
            "-l",
            "chi_sim+eng",
            "--psm",
            "6",
            "tsv"
        ));
        assertThat(executor.timeouts).containsExactly(Duration.ofSeconds(12));
    }

    @Test
    void returnsEmptyWhenTesseractFindsNoText() {
        RecordingExecutor executor = new RecordingExecutor(new OcrProcessResult(
            0,
            "level\tconf\ttext\n5\t-1\t\n",
            "",
            false
        ));

        OcrResult result = new TesseractOcrProvider(new VisionOcrProperties(), executor)
            .recognize(new OcrRequest(Path.of("frame.jpg")));

        assertThat(result.status()).isEqualTo(OcrStatus.EMPTY);
        assertThat(result.text()).isEmpty();
    }

    @Test
    void returnsSanitizedFailureWithoutLocalPathOrObjectKey() {
        RecordingExecutor executor = new RecordingExecutor(new OcrProcessResult(
            1,
            "",
            "failed C:\\Users\\demo\\private\\frame.jpg objectKey=keyframes/42/task_1/frame.jpg token=abc",
            false
        ));

        OcrResult result = new TesseractOcrProvider(new VisionOcrProperties(), executor)
            .recognize(new OcrRequest(Path.of("C:\\Users\\demo\\private\\frame.jpg")));

        assertThat(result.status()).isEqualTo(OcrStatus.FAILED);
        assertThat(result.errorCode()).isEqualTo("OCR_PROVIDER_FAILED");
        assertThat(result.errorMessage())
            .doesNotContain("C:\\Users")
            .doesNotContain("demo")
            .doesNotContain("objectKey")
            .doesNotContain("keyframes/42")
            .doesNotContain("token")
            .doesNotContain("abc");
    }

    private static final class RecordingExecutor implements OcrProcessExecutor {

        private final OcrProcessResult result;
        private final List<List<String>> commands = new ArrayList<>();
        private final List<Duration> timeouts = new ArrayList<>();

        private RecordingExecutor(OcrProcessResult result) {
            this.result = result;
        }

        @Override
        public OcrProcessResult execute(List<String> command, Duration timeout) {
            commands.add(List.copyOf(command));
            timeouts.add(timeout);
            return result;
        }
    }
}
