package com.example.courselingo.ai.asr;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import javax.sound.sampled.AudioFileFormat;
import javax.sound.sampled.AudioFormat;
import javax.sound.sampled.AudioInputStream;
import javax.sound.sampled.AudioSystem;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.util.unit.DataSize;

class BailianAsrProviderTest {
    private static final String FAKE_KEY = "fixture-credential-never-real";
    @TempDir Path tempDir;

    @Test
    void successSendsDocumentedRequestAndUsesCumulativeText() throws Exception {
        var properties = properties();
        properties.setEndpoint("https://workspace.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation");
        properties.setLanguageHintEnabled(true);
        properties.setContext("Lecture about eigenvalues");
        properties.setVocabulary(Map.of("eigenvalue", 5));
        AtomicReference<byte[]> sent = new AtomicReference<>();
        var provider = new BailianAsrProvider(properties, (endpoint, key, body, timeout) -> {
            assertThat(endpoint.toString()).isEqualTo(properties.getEndpoint());
            assertThat(key).isEqualTo(FAKE_KEY);
            assertThat(timeout).isEqualTo(Duration.ofSeconds(180));
            sent.set(body);
            return new BailianAsrTransport.Response(200,
                "{\"output\":{\"text\":\"First sentence. Last sentence.\",\"sentence\":{\"text\":\"Last sentence.\",\"begin_time\":2000,\"end_time\":3000}},\"request_id\":\"" + FAKE_KEY + "\"}");
        });
        var request = request(1);
        var result = provider.transcribe(request);
        JsonNode json = new ObjectMapper().readTree(sent.get());
        assertThat(json.path("model").asText()).isEqualTo("qwen-audio-3.1-asr-flash");
        assertThat(json.at("/parameters/format").asText()).isEqualTo("wav");
        assertThat(json.at("/parameters/language_hints/0").asText()).isEqualTo("en");
        assertThat(json.at("/parameters/vocabulary/eigenvalue").asInt()).isEqualTo(5);
        assertThat(json.at("/input/messages/0/content/0/type").asText()).isEqualTo("input_text");
        assertThat(json.at("/input/messages/0/content/0/text").asText()).isEqualTo(properties.getContext());
        assertThat(json.at("/input/messages/1/content/0/input_audio/data").asText())
            .isEqualTo("data:audio/wav;base64," + Base64.getEncoder().encodeToString(Files.readAllBytes(request.audioFile())));
        assertThat(result.provider()).isEqualTo("bailian");
        assertThat(result.fullText()).isEqualTo("First sentence. Last sentence.");
        assertThat(result.segments()).hasSize(1);
        assertThat(result.segments().getFirst().endMillis()).isZero();
        assertThat(result.metadata()).containsEntry("segmentTimingSource", "provider_not_available");
        assertThat(result.toString()).doesNotContain(FAKE_KEY, "Authorization", "data:audio");
    }

    @Test
    void optionalHintsAreOmittedByDefaultAndAutoOmitsLanguage() throws Exception {
        var properties = properties();
        var provider = new BailianAsrProvider(properties, (endpoint, key, body, timeout) -> {
            try {
                JsonNode json = new ObjectMapper().readTree(body);
                assertThat(json.path("parameters").size()).isEqualTo(1);
                assertThat(json.at("/input/messages").size()).isEqualTo(1);
            } catch (IOException exception) { throw new AssertionError(exception); }
            return new BailianAsrTransport.Response(200, "{\"output\":{\"text\":\"\"}}");
        });
        assertThat(provider.transcribe(request(1)).segments()).isEmpty();
        properties.setLanguageHintEnabled(true);
        var request = request(1);
        provider.transcribe(new SpeechToTextRequest(request.audioFile(), "auto", "r", "t", request.timeout()));
    }

    @ParameterizedTest
    @ValueSource(strings = {
        "{\"output\":{\"output\":{\"sentence\":{\"text\":\"hello\"}}}}",
        "{\"output\":{\"sentence\":{\"text\":\"hello\"}}}"
    })
    void acceptsDocumentedSentenceEnvelopes(String body) throws Exception {
        assertThat(provider(200, body).transcribe(request(1)).fullText()).isEqualTo("hello");
    }

    @ParameterizedTest
    @CsvSource({"400,false", "401,false", "403,false", "404,false", "408,true", "413,false", "422,false",
        "429,true", "500,true", "501,true", "502,true", "503,true", "504,true", "599,true", "302,false"})
    void statusClassificationDoesNotExposeRemoteBody(int status, boolean retryable) throws Exception {
        var request = request(1);
        assertThatThrownBy(() -> provider(status, "Authorization: Bearer " + FAKE_KEY + " data:audio/wav;base64,AAAA")
            .transcribe(request)).isInstanceOf(AsrProviderException.class).satisfies(error -> {
                assertThat(((AsrProviderException) error).retryable()).isEqualTo(retryable);
                assertThat(((AsrProviderException) error).statusCode()).contains(status);
                assertSafe(error);
            });
    }

    @ParameterizedTest
    @ValueSource(strings = {"null", "{}", "[]", "{", "{\"output\":{\"text\":12}}",
        "{\"output\":{\"text\":null}}", "{\"code\":\"InvalidApiKey\",\"output\":{\"text\":\"ignored\"}}",
        "{\"choices\":[{\"message\":{\"content\":\"wrong protocol\"}}]}"})
    void invalidResponseIsNonRetryable(String body) throws Exception {
        var request = request(1);
        assertThatThrownBy(() -> provider(200, body).transcribe(request)).satisfies(error -> {
            assertThat(error).isInstanceOf(AsrProviderException.class);
            assertThat(((AsrProviderException) error).retryable()).isFalse();
            assertSafe(error);
        });
    }

    @Test
    void malformedResponseAndTransportCauseCannotEscapeInStackTrace() throws Exception {
        var request = request(1);
        assertThatThrownBy(() -> provider(200, "{\"" + FAKE_KEY + " data:audio/wav;base64,AAAA").transcribe(request))
            .satisfies(BailianAsrProviderTest::assertSafe);
        var provider = new BailianAsrProvider(properties(), (endpoint, key, body, timeout) -> {
            throw new AsrProviderException(FAKE_KEY, true, 503, new IOException(new String(body)));
        });
        assertThatThrownBy(() -> provider.transcribe(request)).satisfies(error -> {
            assertSafe(error);
            assertThat(((AsrProviderException) error).retryable()).isTrue();
            assertThat(((AsrProviderException) error).statusCode()).contains(503);
        });
    }

    @Test
    void oversizeLongAudioAndInvalidOptionsFailBeforeNetwork() throws Exception {
        AtomicInteger calls = new AtomicInteger();
        var properties = properties();
        var provider = new BailianAsrProvider(properties, (endpoint, key, body, timeout) -> {
            calls.incrementAndGet();
            throw new AssertionError("must not call transport");
        });
        var request = request(1);
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        assertThatThrownBy(() -> provider.transcribe(request)).isInstanceOf(AsrProviderException.class);
        properties.setMaxAudioFileSize(DataSize.ofMegabytes(20));
        var longAudio = request(301, 8000);
        assertThatThrownBy(() -> provider.transcribe(longAudio)).isInstanceOf(AsrProviderException.class);
        var base64Oversize = request(301);
        assertThatThrownBy(() -> provider.transcribe(base64Oversize)).isInstanceOf(AsrProviderException.class);
        properties.setContext("a".repeat(401));
        assertThatThrownBy(() -> provider.transcribe(request)).isInstanceOf(AsrProviderException.class);
        properties.setContext("");
        properties.setVocabulary(Map.of("word", 6));
        assertThatThrownBy(() -> provider.transcribe(request)).isInstanceOf(AsrProviderException.class);
        properties.setVocabulary(Map.of("word", 5));
        properties.setModel("fun-asr-flash-2026-06-15");
        assertThatThrownBy(() -> provider.transcribe(request)).isInstanceOf(AsrProviderException.class);
        assertThat(calls).hasValue(0);
    }

    @ParameterizedTest
    @ValueSource(strings = {"http://example.com/asr", "https://user:password@example.com/asr",
        "https://example.com/asr?key=fixture", "bad endpoint"})
    void rejectsUnsafeEndpointsWithoutEchoingThem(String endpoint) throws Exception {
        var properties = properties();
        properties.setEndpoint(endpoint);
        var request = request(1);
        assertThatThrownBy(() -> new BailianAsrProvider(properties, null).transcribe(request))
            .isInstanceOf(AsrProviderException.class).hasMessageNotContaining(endpoint);
    }

    @Test
    void recommended180SecondAudioFitsBase64Limit() throws Exception {
        assertThat(provider(200, "{\"output\":{\"text\":\"long course\"}}")
            .transcribe(request(180)).fullText()).isEqualTo("long course");
    }

    private BailianAsrProvider provider(int status, String body) {
        return new BailianAsrProvider(properties(), (endpoint, key, bytes, timeout) ->
            new BailianAsrTransport.Response(status, body));
    }

    private BailianAsrProperties properties() {
        var properties = new BailianAsrProperties();
        properties.setApiKey(FAKE_KEY);
        return properties;
    }

    private SpeechToTextRequest request(int seconds) throws IOException {
        return request(seconds, 16000);
    }

    private SpeechToTextRequest request(int seconds, int sampleRate) throws IOException {
        Path path = tempDir.resolve("audio-" + seconds + "-" + sampleRate + ".wav");
        byte[] pcm = new byte[sampleRate * 2 * seconds];
        try (var input = new AudioInputStream(new ByteArrayInputStream(pcm),
            new AudioFormat(sampleRate, 16, 1, true, false), (long) sampleRate * seconds)) {
            AudioSystem.write(input, AudioFileFormat.Type.WAVE, path.toFile());
        }
        return new SpeechToTextRequest(path, "en-US", "request", "task", Duration.ofSeconds(60));
    }

    private static void assertSafe(Throwable error) {
        StringWriter stack = new StringWriter();
        error.printStackTrace(new PrintWriter(stack));
        assertThat(stack.toString()).doesNotContain(FAKE_KEY, "Authorization", "Bearer", "data:audio", "AAAA");
        assertThat(error.getCause()).isNull();
    }
}
