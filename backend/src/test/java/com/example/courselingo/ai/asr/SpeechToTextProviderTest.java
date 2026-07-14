package com.example.courselingo.ai.asr;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SpeechToTextProviderTest {

    @TempDir
    Path tempDir;

    @Test
    void speechToTextProviderInterfaceExists() throws IOException {
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");
        SpeechToTextProvider provider = new SpeechToTextProvider() {
            @Override
            public SpeechToTextResult transcribe(SpeechToTextRequest request) {
                return new SpeechToTextResult(
                    providerName(),
                    request.language(),
                    "hello",
                    List.of(new TranscribedSegment(0, 0, 1_000, "hello")),
                    Duration.ofMillis(50),
                    1_000L,
                    Map.of()
                );
            }

            @Override
            public String providerName() {
                return "test-provider";
            }
        };

        SpeechToTextResult result = provider.transcribe(validRequest(audioFile));

        assertThat(provider.providerName()).isEqualTo("test-provider");
        assertThat(result.fullText()).isEqualTo("hello");
    }

    @Test
    void requestAudioFileNullFails() {
        SpeechToTextRequest request = new SpeechToTextRequest(
            null,
            "zh-CN",
            "req_1",
            "task_1",
            Duration.ofSeconds(30)
        );

        assertInvalidRequest(request, "audio file is required");
    }

    @Test
    void requestAudioFileMissingFails() {
        SpeechToTextRequest request = validRequest(tempDir.resolve("missing.wav"));

        assertInvalidRequest(request, "audio file does not exist");
    }

    @Test
    void requestAudioFileNotRegularFails() throws IOException {
        Path directory = Files.createDirectory(tempDir.resolve("audio-dir"));
        SpeechToTextRequest request = validRequest(directory);

        assertInvalidRequest(request, "audio file must be a regular file");
    }

    @Test
    void languageBlankFails() throws IOException {
        SpeechToTextRequest request = new SpeechToTextRequest(
            Files.writeString(tempDir.resolve("lecture.wav"), "audio"),
            " ",
            "req_1",
            "task_1",
            Duration.ofSeconds(30)
        );

        assertInvalidRequest(request, "language is required");
    }

    @Test
    void languageTooLongFails() throws IOException {
        SpeechToTextRequest request = new SpeechToTextRequest(
            Files.writeString(tempDir.resolve("lecture.wav"), "audio"),
            "x".repeat(33),
            "req_1",
            "task_1",
            Duration.ofSeconds(30)
        );

        assertInvalidRequest(request, "language is too long");
    }

    @Test
    void requestIdBlankFails() throws IOException {
        SpeechToTextRequest request = new SpeechToTextRequest(
            Files.writeString(tempDir.resolve("lecture.wav"), "audio"),
            "zh-CN",
            "",
            "task_1",
            Duration.ofSeconds(30)
        );

        assertInvalidRequest(request, "request id is required");
    }

    @Test
    void taskIdBlankFails() throws IOException {
        SpeechToTextRequest request = new SpeechToTextRequest(
            Files.writeString(tempDir.resolve("lecture.wav"), "audio"),
            "zh-CN",
            "req_1",
            " ",
            Duration.ofSeconds(30)
        );

        assertInvalidRequest(request, "task id is required");
    }

    @Test
    void timeoutNullOrNonPositiveFails() throws IOException {
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");

        assertInvalidRequest(
            new SpeechToTextRequest(audioFile, "zh-CN", "req_1", "task_1", null),
            "timeout must be positive"
        );
        assertInvalidRequest(
            new SpeechToTextRequest(audioFile, "zh-CN", "req_1", "task_1", Duration.ZERO),
            "timeout must be positive"
        );
        assertInvalidRequest(
            new SpeechToTextRequest(audioFile, "zh-CN", "req_1", "task_1", Duration.ofMillis(-1)),
            "timeout must be positive"
        );
    }

    @Test
    void validRequestPasses() throws IOException {
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");

        assertThatCode(() -> SpeechToTextRequestValidator.validate(validRequest(audioFile)))
            .doesNotThrowAnyException();
    }

    @Test
    void negativeSegmentIndexFails() {
        assertThatThrownBy(() -> new TranscribedSegment(-1, 0, 1_000, "hello"))
            .isInstanceOf(SpeechToTextProviderException.class)
            .hasMessageContaining("segment index must not be negative");
    }

    @Test
    void negativeSegmentStartFails() {
        assertThatThrownBy(() -> new TranscribedSegment(0, -1, 1_000, "hello"))
            .isInstanceOf(SpeechToTextProviderException.class)
            .hasMessageContaining("segment start must not be negative");
    }

    @Test
    void segmentEndBeforeStartFails() {
        assertThatThrownBy(() -> new TranscribedSegment(0, 1_000, 999, "hello"))
            .isInstanceOf(SpeechToTextProviderException.class)
            .hasMessageContaining("segment end must not be before start");
    }

    @Test
    void blankSegmentTextFails() {
        assertThatThrownBy(() -> new TranscribedSegment(0, 0, 1_000, " "))
            .isInstanceOf(SpeechToTextProviderException.class)
            .hasMessageContaining("segment text is required");
    }

    @Test
    void resultSegmentsNullFails() {
        assertThatThrownBy(() -> new SpeechToTextResult(
            "test-provider",
            "zh-CN",
            "hello",
            null,
            Duration.ofMillis(50),
            1_000L,
            Map.of()
        ))
            .isInstanceOf(SpeechToTextProviderException.class)
            .hasMessageContaining("segments are required");
    }

    @Test
    void validResultAndSegmentCreationSucceeds() {
        TranscribedSegment segment = new TranscribedSegment(0, 0, 1_000, "hello");
        SpeechToTextResult result = new SpeechToTextResult(
            "test-provider",
            "zh-CN",
            "hello",
            List.of(segment),
            Duration.ofMillis(50),
            1_000L,
            Map.of("model", "placeholder")
        );

        assertThat(result.segments()).containsExactly(segment);
        assertThat(result.metadata()).containsEntry("model", "placeholder");
    }

    @Test
    void errorMessagesAreSanitized() {
        SpeechToTextProviderException error = new SpeechToTextProviderException(
            "failed token=abc secret=def apiKey=ghi API_KEY=jkl api key mno "
                + "C:\\Users\\demo\\private\\lecture.wav"
        );

        assertThat(error.getMessage()).doesNotContain("abc", "def", "ghi", "jkl", "mno", "C:\\Users", "demo");
        assertThat(error.getMessage().toLowerCase()).doesNotContain("token", "secret", "apikey", "api_key", "api key");
    }

    @Test
    void asrAbstractionDoesNotReferenceForbiddenIntegrations() throws IOException {
        Path asrSource = Path.of("src/main/java/com/example/courselingo/ai/asr");

        String source = readJavaSources(asrSource);

        assertThat(source)
            .doesNotContain("WebClient")
            .doesNotContain("RestTemplate")
            .doesNotContain("OkHttp")
            .doesNotContain("LangChain4j")
            .doesNotContain("AnalysisTaskRunner")
            .doesNotContain("RocketMQ")
            .doesNotContain("Jdbc")
            .doesNotContain("BaseMapper")
            .doesNotContain("Repository")
            .doesNotContain("subtitle")
            .doesNotContain("artifact")
            .doesNotContain("learning");
    }

    private SpeechToTextRequest validRequest(Path audioFile) {
        return new SpeechToTextRequest(
            audioFile,
            "zh-CN",
            "req_1",
            "task_1",
            Duration.ofSeconds(30)
        );
    }

    private static void assertInvalidRequest(SpeechToTextRequest request, String expectedMessage) {
        assertThatThrownBy(() -> SpeechToTextRequestValidator.validate(request))
            .isInstanceOf(SpeechToTextProviderException.class)
            .hasMessageContaining(expectedMessage);
    }

    private static String readJavaSources(Path directory) throws IOException {
        if (!Files.exists(directory)) {
            return "";
        }
        StringBuilder source = new StringBuilder();
        try (var paths = Files.walk(directory)) {
            for (Path path : paths.filter(path -> path.toString().endsWith(".java")).toList()) {
                source.append(Files.readString(path)).append('\n');
            }
        }
        return source.toString();
    }
}
