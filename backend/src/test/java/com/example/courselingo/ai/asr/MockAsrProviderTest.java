package com.example.courselingo.ai.asr;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class MockAsrProviderTest {

    @TempDir
    Path tempDir;

    @Test
    void mockProviderImplementsSpeechToTextProviderAndReturnsStableName() {
        MockAsrProvider provider = new MockAsrProvider(properties());

        assertThat(provider).isInstanceOf(SpeechToTextProvider.class);
        assertThat(provider.providerName()).isEqualTo("mock");
    }

    @Test
    void validRequestReturnsDeterministicResultWithSafeMetadata() throws IOException {
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");
        MockAsrProperties properties = properties();
        properties.setDefaultText("local mock transcript");
        properties.setSegmentDurationMillis(3_000L);
        MockAsrProvider provider = new MockAsrProvider(properties);

        SpeechToTextResult result = provider.transcribe(validRequest(audioFile));

        assertThat(result.provider()).isEqualTo("mock");
        assertThat(result.language()).isEqualTo("zh-CN");
        assertThat(result.fullText()).isEqualTo("local mock transcript");
        assertThat(result.segments()).hasSize(1);
        TranscribedSegment segment = result.segments().getFirst();
        assertThat(segment.index()).isZero();
        assertThat(segment.startMillis()).isZero();
        assertThat(segment.endMillis()).isEqualTo(3_000L);
        assertThat(segment.text()).isEqualTo("local mock transcript");
        assertThat(result.audioDurationMillis()).isEqualTo(3_000L);
        assertThat(result.duration().isNegative()).isFalse();
        assertThat(result.metadata())
            .containsEntry("mock", true)
            .containsEntry("source", "mock-asr")
            .containsEntry("audioFileName", "lecture.wav");
        assertSafeMetadata(result.metadata(), audioFile);
    }

    @Test
    void blankConfiguredTextFallsBackToDeterministicAudioFileNameText() throws IOException {
        Path audioFile = Files.writeString(tempDir.resolve("lesson-01.wav"), "audio");
        MockAsrProperties properties = properties();
        properties.setDefaultText(" ");
        MockAsrProvider provider = new MockAsrProvider(properties);

        SpeechToTextResult result = provider.transcribe(validRequest(audioFile));

        assertThat(result.fullText()).isEqualTo("Mock ASR transcript for lesson-01.wav");
        assertThat(result.segments()).extracting(TranscribedSegment::text)
            .containsExactly("Mock ASR transcript for lesson-01.wav");
    }

    @Test
    void requestValidatorIsReusedForInvalidRequests() throws IOException {
        MockAsrProvider provider = new MockAsrProvider(properties());
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");

        assertInvalid(provider, new SpeechToTextRequest(null, "zh-CN", "req_1", "task_1", Duration.ofSeconds(30)),
            "audio file is required");
        assertInvalid(provider, validRequest(tempDir.resolve("missing.wav")), "audio file does not exist");
        assertInvalid(provider, validRequest(Files.createDirectory(tempDir.resolve("audio-dir"))),
            "audio file must be a regular file");
        assertInvalid(provider, new SpeechToTextRequest(audioFile, " ", "req_1", "task_1", Duration.ofSeconds(30)),
            "language is required");
        assertInvalid(provider, new SpeechToTextRequest(audioFile, "zh-CN", "", "task_1", Duration.ofSeconds(30)),
            "request id is required");
        assertInvalid(provider, new SpeechToTextRequest(audioFile, "zh-CN", "req_1", " ", Duration.ofSeconds(30)),
            "task id is required");
        assertInvalid(provider, new SpeechToTextRequest(audioFile, "zh-CN", "req_1", "task_1", Duration.ZERO),
            "timeout must be positive");
    }

    @Test
    void invalidSegmentDurationFailsWithSanitizedMessage() throws IOException {
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");
        MockAsrProperties properties = properties();
        properties.setSegmentDurationMillis(0L);
        MockAsrProvider provider = new MockAsrProvider(properties);

        assertThatThrownBy(() -> provider.transcribe(validRequest(audioFile)))
            .isInstanceOf(SpeechToTextProviderException.class)
            .hasMessageContaining("segment duration must be positive")
            .satisfies(error -> assertSanitized(error.getMessage()));
    }

    @Test
    void mockConfigurationIsDisabledByDefaultAndEnabledOnlyByProperty() {
        new ApplicationContextRunner()
            .withUserConfiguration(MockAsrConfiguration.class)
            .run(context -> assertThat(context).doesNotHaveBean(MockAsrProvider.class));

        new ApplicationContextRunner()
            .withUserConfiguration(MockAsrConfiguration.class)
            .withPropertyValues("courselingo.ai.asr.mock.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(MockAsrProvider.class);
                assertThat(context).hasSingleBean(MockAsrProperties.class);
            });
    }

    @Test
    void mockProviderDoesNotReferenceForbiddenIntegrationsOrNetworking() throws IOException {
        Path asrSource = Path.of("src/main/java/com/example/courselingo/ai/asr");

        String source = readJavaSources(asrSource);

        assertThat(source)
            .doesNotContain("LangChain4j")
            .doesNotContain("AnalysisTaskRunner")
            .doesNotContain("RocketMQ")
            .doesNotContain("Jdbc")
            .doesNotContain("BaseMapper")
            .doesNotContain("Repository")
            .doesNotContain("subtitle")
            .doesNotContain("artifact")
            .doesNotContain("learning");
        assertThat(readMockJavaSources(asrSource))
            .doesNotContain("SiliconFlow")
            .doesNotContain("HttpClient")
            .doesNotContain("WebClient")
            .doesNotContain("RestTemplate")
            .doesNotContain("OkHttp")
            .doesNotContain("apiKey")
            .doesNotContain("Authorization");
    }

    private MockAsrProperties properties() {
        MockAsrProperties properties = new MockAsrProperties();
        properties.setDefaultText("This is a mock ASR transcript for local development and testing.");
        properties.setSegmentDurationMillis(3_000L);
        return properties;
    }

    private SpeechToTextRequest validRequest(Path audioFile) {
        return new SpeechToTextRequest(audioFile, "zh-CN", "req_1", "task_1", Duration.ofSeconds(30));
    }

    private static void assertInvalid(MockAsrProvider provider, SpeechToTextRequest request, String expectedMessage) {
        assertThatThrownBy(() -> provider.transcribe(request))
            .isInstanceOf(SpeechToTextProviderException.class)
            .hasMessageContaining(expectedMessage)
            .satisfies(error -> assertSanitized(error.getMessage()));
    }

    private static void assertSafeMetadata(Map<String, Object> metadata, Path audioFile) {
        String serialized = metadata.toString();
        assertThat(serialized).doesNotContain(audioFile.toAbsolutePath().toString());
        assertSanitized(serialized);
    }

    private static void assertSanitized(String message) {
        assertThat(message).doesNotContain("abc", "def", "ghi", "C:\\Users", "demo");
        assertThat(message.toLowerCase()).doesNotContain("token", "secret", "apikey", "api_key", "api key");
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

    private static String readMockJavaSources(Path directory) throws IOException {
        if (!Files.exists(directory)) {
            return "";
        }
        StringBuilder source = new StringBuilder();
        try (var paths = Files.walk(directory)) {
            for (Path path : paths
                .filter(path -> path.getFileName().toString().startsWith("Mock"))
                .filter(path -> path.toString().endsWith(".java"))
                .toList()) {
                source.append(Files.readString(path)).append('\n');
            }
        }
        return source.toString();
    }
}
