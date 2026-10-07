package com.example.courselingo.ai.asr;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import javax.sound.sampled.AudioFileFormat;
import javax.sound.sampled.AudioFormat;
import javax.sound.sampled.AudioInputStream;
import javax.sound.sampled.AudioSystem;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

// Fixtures follow the synchronous HTTP reference and its differently nested user-guide response.
@ExtendWith(OutputCaptureExtension.class)
class BailianAsrContractTest {
    private static final String KEY = "contract-test-credential-not-real";
    private static final String API_PATH = "/api/v1/services/aigc/multimodal-generation/generation";
    private static final ObjectMapper JSON = new ObjectMapper();
    @TempDir Path tempDir;

    @ParameterizedTest
    @ValueSource(strings = {"workspace.cn-beijing.maas.aliyuncs.com", "workspace.ap-southeast-1.maas.aliyuncs.com",
        "dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com"})
    void serializesExactSynchronousContractWithoutChangingRegion(String host) throws Exception {
        var properties = properties();
        properties.setEndpoint("https://" + host + API_PATH);
        properties.setLanguageHintEnabled(true);
        properties.setContext("课程：\"特征值\"\nC:\\lecture 🧮");
        properties.setVocabulary(Map.of("特征值", 5, "eigenvector", 50));
        var sent = new AtomicReference<byte[]>();
        var provider = new BailianAsrProvider(properties, (uri, key, body, timeout) -> {
            assertThat(uri.toString()).isEqualTo(properties.getEndpoint());
            assertThat(key).isEqualTo(KEY);
            sent.set(body);
            return new BailianAsrTransport.Response(200, "{\"output\":{\"text\":\"识别文本\"}}");
        });
        var request = request(1, "zh-CN");
        assertThat(provider.transcribe(request).fullText()).isEqualTo("识别文本");
        String data = "data:audio/wav;base64," + Base64.getEncoder().encodeToString(Files.readAllBytes(request.audioFile()));
        var expected = Map.of(
            "model", "qwen-audio-3.1-asr-flash",
            "input", Map.of("messages", List.of(
                Map.of("role", "user", "content", List.of(Map.of("type", "input_text", "text", properties.getContext()))),
                Map.of("role", "user", "content", List.of(Map.of("type", "input_audio", "input_audio", Map.of("data", data)))))),
            "parameters", Map.of("format", "wav", "language_hints", List.of("zh"), "vocabulary", properties.getVocabulary()));
        // Full structural equality also rejects accidental prompt/language/hotwords/file_urls fields.
        assertThat(JSON.readTree(sent.get())).isEqualTo(JSON.valueToTree(expected));
        assertThat(new String(sent.get(), StandardCharsets.UTF_8)).doesNotContain(KEY, "Authorization");
        assertThat(Base64.getDecoder().decode(JSON.readTree(sent.get())
            .at("/input/messages/1/content/0/input_audio/data").asText().substring(22)))
            .isEqualTo(Files.readAllBytes(request.audioFile()));
    }

    @ParameterizedTest
    @ValueSource(strings = {"qwen-audio-3.1-asr-flash-filetrans", "qwen3-asr-flash-filetrans",
        "qwen-audio-3.1-asr-flash-streaming", "qwen3-asr-flash", "fun-asr", "unknown-model"})
    void rejectsOtherProtocolsBeforeSending(String model) throws Exception {
        var properties = properties();
        properties.setModel(model);
        assertRejectedWithoutSending(properties, request(1, "en"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"/api/v1/services/audio/asr/transcription", "/compatible-mode/v1/chat/completions",
        "/v1/audio/transcriptions", "/api/v1/tasks/task-id", "/api/v1/services/aigc/multimodal-generation/generation/"})
    void rejectsWrongEndpointBeforeSending(String path) throws Exception {
        var properties = properties();
        properties.setEndpoint("https://workspace.cn-beijing.maas.aliyuncs.com" + path);
        assertRejectedWithoutSending(properties, request(1, "en"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"qwen-audio-3.0-asr-flash", "fun-asr-flash-2026-06-15"})
    void supportsOtherDocumentedSynchronousModels(String model) throws Exception {
        var properties = properties();
        properties.setModel(model);
        var provider = new BailianAsrProvider(properties, (uri, key, body, timeout) -> {
            try { assertThat(JSON.readTree(body).path("model").asText()).isEqualTo(model); }
            catch (IOException exception) { throw new AssertionError(exception); }
            return new BailianAsrTransport.Response(200, "{\"output\":{\"text\":\"hello\"}}");
        });
        assertThat(provider.transcribe(request(1, "en")).fullText()).isEqualTo("hello");
    }

    @ParameterizedTest
    @CsvSource({"180,true", "299,true", "300,false", "301,false"})
    void validatesDurationIndependentlyOfFileSize(int seconds, boolean accepted) throws Exception {
        var calls = new AtomicInteger();
        var provider = new BailianAsrProvider(properties(), (uri, key, body, timeout) -> {
            calls.incrementAndGet();
            return new BailianAsrTransport.Response(200, "{\"output\":{\"text\":\"hello\"}}");
        });
        var request = request(seconds, "en");
        if (accepted) {
            assertThat(provider.transcribe(request).fullText()).isEqualTo("hello");
            assertThat(calls).hasValue(1);
        } else {
            assertThatThrownBy(() -> provider.transcribe(request)).isInstanceOf(AsrProviderException.class);
            assertThat(calls).hasValue(0);
        }
    }

    @ParameterizedTest
    @ValueSource(strings = {
        "{\"output\":{\"text\":\"ok\"}} {\"another\":1}",
        "{\"output\":{\"text\":\"ok\"}} trailing-garbage",
        "{\"output\":{\"text\":\"first\",\"text\":\"second\"}}",
        "{\"output\":{\"task_id\":\"id\",\"task_status\":\"PENDING\"}}",
        "{\"choices\":[{\"message\":{\"content\":\"wrong protocol\"}}]}",
        "data: {\"output\":{\"text\":\"stream\"}}"
    })
    void rejectsMalformedOrDifferentProtocolResponses(String response) throws Exception {
        var provider = new BailianAsrProvider(properties(), (uri, key, body, timeout) ->
            new BailianAsrTransport.Response(200, response));
        var request = request(1, "en");
        assertThatThrownBy(() -> provider.transcribe(request)).satisfies(error -> {
            assertThat(error).isInstanceOf(AsrProviderException.class);
            assertThat(((AsrProviderException) error).retryable()).isFalse();
            assertThat(error.getCause()).isNull();
        });
    }

    @Test
    void userGuideEnvelopeKeepsCumulativeTextAndDoesNotExposeExtraFields(CapturedOutput captured) throws Exception {
        var provider = new BailianAsrProvider(properties(), (uri, key, body, timeout) ->
            new BailianAsrTransport.Response(200, """
                {"output":{"text":"Whole lecture.","output":{"sentence":{"text":"Last sentence."}}},
                 "request_id":"contract-test-credential-not-real", "Authorization":"Bearer fake-value",
                 "debug":"data:audio/wav;base64,AAAA", "usage":{"duration":1}}
                """));
        var result = provider.transcribe(request(1, "en"));
        assertThat(result.fullText()).isEqualTo("Whole lecture.");
        assertThat(result.toString()).doesNotContain(KEY, "Authorization", "AAAA", "fake-value");
        assertThat(captured.getAll()).doesNotContain(KEY, "Authorization", "AAAA", "fake-value");
    }

    @ParameterizedTest
    @ValueSource(ints = {200, 401, 429, 503})
    void unsafeRemoteErrorsNeverReachLogsOrExceptionChains(int status, CapturedOutput captured) throws Exception {
        var request = request(1, "en");
        String base64 = Base64.getEncoder().encodeToString(Files.readAllBytes(request.audioFile()));
        var provider = new BailianAsrProvider(properties(), (uri, key, body, timeout) ->
            new BailianAsrTransport.Response(status, "Authorization: Bearer " + KEY + " data:audio/wav;base64," + base64));
        assertThatThrownBy(() -> provider.transcribe(request)).satisfies(error -> {
            var stack = new StringWriter();
            error.printStackTrace(new PrintWriter(stack));
            assertThat(stack.toString()).doesNotContain(KEY, "Authorization", base64);
        });
        assertThat(captured.getAll()).doesNotContain(KEY, "Authorization", base64);
    }

    @ParameterizedTest
    @ValueSource(strings = {"-", "---", "xx-Unknown"})
    void invalidLanguageHintIsClassifiedBeforeSending(String language) throws Exception {
        var properties = properties();
        properties.setLanguageHintEnabled(true);
        assertRejectedWithoutSending(properties, request(1, language));
    }

    private void assertRejectedWithoutSending(BailianAsrProperties properties, SpeechToTextRequest request) {
        var provider = new BailianAsrProvider(properties, (uri, key, body, timeout) -> {
            throw new AssertionError("Invalid configuration must not reach HTTP transport");
        });
        assertThatThrownBy(() -> provider.transcribe(request)).satisfies(error -> {
            assertThat(error).isInstanceOf(AsrProviderException.class);
            assertThat(((AsrProviderException) error).retryable()).isFalse();
        });
    }

    private BailianAsrProperties properties() {
        var properties = new BailianAsrProperties();
        properties.setApiKey(KEY);
        return properties;
    }

    private SpeechToTextRequest request(int seconds, String language) throws IOException {
        // 8 kHz makes a 301s fixture fit the size cap, isolating the duration check.
        Path path = tempDir.resolve("contract.wav");
        try (var stream = new AudioInputStream(new ByteArrayInputStream(new byte[8000 * 2 * seconds]),
            new AudioFormat(8000, 16, 1, true, false), 8000L * seconds)) {
            AudioSystem.write(stream, AudioFileFormat.Type.WAVE, path.toFile());
        }
        return new SpeechToTextRequest(path, language, "request", "task", Duration.ofSeconds(60));
    }
}
