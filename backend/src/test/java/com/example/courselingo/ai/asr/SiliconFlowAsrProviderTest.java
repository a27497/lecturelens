package com.example.courselingo.ai.asr;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.util.unit.DataSize;

class SiliconFlowAsrProviderTest {

    @TempDir
    Path tempDir;

    @Test
    void providerImplementsSpeechToTextProviderAndReturnsStableName() {
        SiliconFlowAsrProvider provider = newProvider(properties(), new CapturingClient(ok("hello")));

        assertThat(provider).isInstanceOf(SpeechToTextProvider.class);
        assertThat(provider.providerName()).isEqualTo("siliconflow");
    }

    @Test
    void validRequestCallsClientWithFixedPathMultipartFieldsAndAuthorization() throws IOException {
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");
        CapturingClient client = new CapturingClient(ok("hello"));
        SiliconFlowAsrProvider provider = newProvider(properties(), client);

        provider.transcribe(validRequest(audioFile));

        SiliconFlowAsrClientRequest sent = client.singleRequest();
        assertThat(sent.uri()).isEqualTo(URI.create("https://api.siliconflow.cn/v1/audio/transcriptions"));
        assertThat(sent.audioFile()).isEqualTo(audioFile);
        assertThat(sent.fileFieldName()).isEqualTo("file");
        assertThat(sent.formFields()).containsEntry("model", "FunAudioLLM/SenseVoiceSmall");
        assertThat(sent.headers()).containsEntry("Authorization", "Bearer test-api-key");
        assertThat(sent.timeout()).isEqualTo(Duration.ofSeconds(180));
    }

    @Test
    void emptyApiKeyFailsBeforeClientCallAndIsSanitized() throws IOException {
        SiliconFlowAsrProperties properties = properties();
        properties.setApiKey(" ");
        CapturingClient client = new CapturingClient(ok("hello"));
        SiliconFlowAsrProvider provider = newProvider(properties, client);
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");

        assertThatThrownBy(() -> provider.transcribe(validRequest(audioFile)))
            .isInstanceOf(SiliconFlowAsrException.class)
            .satisfies(error -> {
                SiliconFlowAsrException exception = (SiliconFlowAsrException) error;
                assertThat(exception.retryable()).isFalse();
                assertSanitized(error.getMessage());
            });
        assertThat(client.requests()).isEmpty();
    }

    @ParameterizedTest
    @CsvSource({
        "'',base URL is required",
        "ftp://api.siliconflow.cn,base URL must use http or https"
    })
    void invalidBaseUrlFails(String baseUrl, String expectedMessage) throws IOException {
        SiliconFlowAsrProperties properties = properties();
        properties.setBaseUrl(baseUrl);
        SiliconFlowAsrProvider provider = newProvider(properties, new CapturingClient(ok("hello")));
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");

        assertThatThrownBy(() -> provider.transcribe(validRequest(audioFile)))
            .isInstanceOf(SiliconFlowAsrException.class)
            .hasMessageContaining(expectedMessage);
    }

    @Test
    void blankModelFailsBeforeClientCall() throws IOException {
        SiliconFlowAsrProperties properties = properties();
        properties.setModel(" ");
        CapturingClient client = new CapturingClient(ok("hello"));
        SiliconFlowAsrProvider provider = newProvider(properties, client);
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");

        assertThatThrownBy(() -> provider.transcribe(validRequest(audioFile)))
            .isInstanceOf(SiliconFlowAsrException.class)
            .hasMessageContaining("model is required");
        assertThat(client.requests()).isEmpty();
    }

    @Test
    void oversizedAudioFileFailsBeforeClientCall() throws IOException {
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");
        SiliconFlowAsrProperties properties = properties();
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        CapturingClient client = new CapturingClient(ok("hello"));
        SiliconFlowAsrProvider provider = newProvider(properties, client);

        assertThatThrownBy(() -> provider.transcribe(validRequest(audioFile)))
            .isInstanceOf(SiliconFlowAsrException.class)
            .hasMessageContaining("audio file exceeds configured limit");
        assertThat(client.requests()).isEmpty();
    }

    @Test
    void successfulTextResponseMapsToSpeechToTextResultWithSafeMetadata() throws IOException {
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");
        CapturingClient client = new CapturingClient(new SiliconFlowAsrClientResponse(
            200,
            "{\"text\":\"hello\"}",
            Map.of("x-siliconcloud-trace-id", List.of("trace-123")),
            Duration.ofMillis(42)
        ));
        SiliconFlowAsrProvider provider = newProvider(properties(), client);

        SpeechToTextResult result = provider.transcribe(validRequest(audioFile));

        assertThat(result.provider()).isEqualTo("siliconflow");
        assertThat(result.language()).isEqualTo("zh-CN");
        assertThat(result.fullText()).isEqualTo("hello");
        assertThat(result.segments()).containsExactly(new TranscribedSegment(0, 0, 0, "hello"));
        assertThat(result.duration()).isEqualTo(Duration.ofMillis(42));
        assertThat(result.audioDurationMillis()).isZero();
        assertThat(result.metadata())
            .containsEntry("segmentTimingSource", "provider_not_available")
            .containsEntry("providerTraceId", "trace-123");
        assertThat(result.metadata().toString()).doesNotContain("test-api-key");
    }

    @Test
    void emptyTextResponseReturnsEmptyResultWithoutSegments() throws IOException {
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");
        SiliconFlowAsrProvider provider = newProvider(properties(), new CapturingClient(ok(" ")));

        SpeechToTextResult result = provider.transcribe(validRequest(audioFile));

        assertThat(result.fullText()).isEmpty();
        assertThat(result.segments()).isEmpty();
        assertThat(result.metadata()).containsEntry("segmentTimingSource", "provider_not_available");
    }

    @ParameterizedTest
    @CsvSource({
        "400,false",
        "401,false",
        "403,false",
        "404,false",
        "429,true",
        "503,true",
        "504,true"
    })
    void httpStatusMapsToProviderException(int statusCode, boolean retryable) throws IOException {
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");
        SiliconFlowAsrProvider provider = newProvider(
            properties(),
            new CapturingClient(new SiliconFlowAsrClientResponse(
                statusCode,
                "{\"error\":\"token=abc secret=def apiKey=ghi C:\\\\Users\\\\demo\\\\private\\\\audio.wav\"}",
                Map.of(),
                Duration.ofMillis(1)
            ))
        );

        assertThatThrownBy(() -> provider.transcribe(validRequest(audioFile)))
            .isInstanceOf(SiliconFlowAsrException.class)
            .satisfies(error -> {
                SiliconFlowAsrException exception = (SiliconFlowAsrException) error;
                assertThat(exception.retryable()).isEqualTo(retryable);
                assertThat(exception.statusCode()).contains(statusCode);
                assertSanitized(error.getMessage());
            });
    }

    @Test
    void timeoutMapsToRetryableProviderException() throws IOException {
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");
        SiliconFlowAsrProvider provider = newProvider(
            properties(),
            new ThrowingClient(new SiliconFlowAsrException("timeout token=abc", true))
        );

        assertThatThrownBy(() -> provider.transcribe(validRequest(audioFile)))
            .isInstanceOf(SiliconFlowAsrException.class)
            .satisfies(error -> {
                SiliconFlowAsrException exception = (SiliconFlowAsrException) error;
                assertThat(exception.retryable()).isTrue();
                assertSanitized(error.getMessage());
            });
    }

    @Test
    void invalidJsonMapsToProviderException() throws IOException {
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");
        SiliconFlowAsrProvider provider = newProvider(
            properties(),
            new CapturingClient(new SiliconFlowAsrClientResponse(200, "{not-json", Map.of(), Duration.ofMillis(1)))
        );

        assertThatThrownBy(() -> provider.transcribe(validRequest(audioFile)))
            .isInstanceOf(SiliconFlowAsrException.class)
            .satisfies(error -> {
                SiliconFlowAsrException exception = (SiliconFlowAsrException) error;
                assertThat(exception.retryable()).isFalse();
                assertSanitized(error.getMessage());
            });
    }

    @Test
    void javaHttpClientCanBuildMultipartRequestWithoutSendingRealNetworkCall() throws IOException {
        Path audioFile = Files.writeString(tempDir.resolve("lecture.wav"), "audio");
        CapturingHttpTransport transport = new CapturingHttpTransport(new SiliconFlowAsrClientResponse(
            200,
            "{\"text\":\"ok\"}",
            Map.of(),
            Duration.ofMillis(2)
        ));
        JavaHttpSiliconFlowAsrClient client = new JavaHttpSiliconFlowAsrClient(transport);
        SiliconFlowAsrClientRequest request = new SiliconFlowAsrClientRequest(
            URI.create("https://api.siliconflow.cn/v1/audio/transcriptions"),
            Map.of("Authorization", "Bearer test-api-key"),
            audioFile,
            "file",
            Map.of("model", "FunAudioLLM/SenseVoiceSmall"),
            Duration.ofSeconds(60)
        );

        SiliconFlowAsrClientResponse response = client.transcribe(request);

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(transport.contentType()).startsWith("multipart/form-data; boundary=");
        assertThat(transport.bodyAsString())
            .contains("name=\"model\"")
            .contains("FunAudioLLM/SenseVoiceSmall")
            .contains("name=\"file\"")
            .contains("filename=\"lecture.wav\"")
            .contains("audio");
        assertThat(transport.headers()).containsEntry("Authorization", "Bearer test-api-key");
    }

    @Test
    void asrProviderDoesNotReferenceForbiddenPipelineIntegrations() throws IOException {
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
    }

    private SiliconFlowAsrProvider newProvider(SiliconFlowAsrProperties properties, SiliconFlowAsrClient client) {
        return new SiliconFlowAsrProvider(properties, client);
    }

    private SiliconFlowAsrProperties properties() {
        SiliconFlowAsrProperties properties = new SiliconFlowAsrProperties();
        properties.setApiKey("test-api-key");
        return properties;
    }

    private SpeechToTextRequest validRequest(Path audioFile) {
        return new SpeechToTextRequest(audioFile, "zh-CN", "req_1", "task_1", Duration.ofSeconds(30));
    }

    private static SiliconFlowAsrClientResponse ok(String text) {
        return new SiliconFlowAsrClientResponse(200, "{\"text\":\"" + text + "\"}", Map.of(), Duration.ofMillis(1));
    }

    private static void assertSanitized(String message) {
        assertThat(message).doesNotContain("abc", "def", "ghi", "test-api-key", "C:\\Users", "demo");
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

    private static final class CapturingClient implements SiliconFlowAsrClient {

        private final SiliconFlowAsrClientResponse response;
        private final List<SiliconFlowAsrClientRequest> requests = new ArrayList<>();

        private CapturingClient(SiliconFlowAsrClientResponse response) {
            this.response = response;
        }

        @Override
        public SiliconFlowAsrClientResponse transcribe(SiliconFlowAsrClientRequest request) {
            requests.add(request);
            return response;
        }

        List<SiliconFlowAsrClientRequest> requests() {
            return requests;
        }

        SiliconFlowAsrClientRequest singleRequest() {
            assertThat(requests).hasSize(1);
            return requests.getFirst();
        }
    }

    private static final class ThrowingClient implements SiliconFlowAsrClient {

        private final RuntimeException exception;

        private ThrowingClient(RuntimeException exception) {
            this.exception = exception;
        }

        @Override
        public SiliconFlowAsrClientResponse transcribe(SiliconFlowAsrClientRequest request) {
            throw exception;
        }
    }

    private static final class CapturingHttpTransport implements SiliconFlowHttpTransport {

        private final SiliconFlowAsrClientResponse response;
        private Map<String, String> headers;
        private String contentType;
        private byte[] body;

        private CapturingHttpTransport(SiliconFlowAsrClientResponse response) {
            this.response = response;
        }

        @Override
        public SiliconFlowAsrClientResponse send(SiliconFlowHttpRequest request) {
            this.headers = request.headers();
            this.contentType = request.contentType();
            this.body = request.body();
            return response;
        }

        Map<String, String> headers() {
            return headers;
        }

        String contentType() {
            return contentType;
        }

        String bodyAsString() {
            return new String(body);
        }
    }
}
