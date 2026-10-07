package com.example.courselingo.ai.asr;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import javax.sound.sampled.AudioFileFormat;
import javax.sound.sampled.AudioSystem;
import javax.sound.sampled.UnsupportedAudioFileException;

public final class BailianAsrProvider implements SpeechToTextProvider {
    private static final String SYNCHRONOUS_PATH = "/api/v1/services/aigc/multimodal-generation/generation";
    private static final Set<String> SYNCHRONOUS_MODELS = Set.of(
        "qwen-audio-3.1-asr-flash", "qwen-audio-3.0-asr-flash", "fun-asr-flash-2026-06-15");
    // The HTTP reference still limits Base64 input to 10 MB, despite larger URL limits.
    private static final long MAX_ENCODED_BYTES = 10_000_000L;
    private static final Set<String> LANGUAGES = Set.of(
        "zh", "en", "ja", "ko", "vi", "th", "id", "ms", "tl", "hi", "ar", "fr", "de", "es", "pt",
        "ru", "it", "nl", "sv", "da", "fi", "no", "el", "pl", "cs", "hu", "ro", "bg", "hr", "sk");
    private final BailianAsrProperties properties;
    private final BailianAsrTransport transport;
    private final ObjectMapper mapper = new ObjectMapper()
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
        .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);

    BailianAsrProvider(BailianAsrProperties properties, BailianAsrTransport transport) {
        this.properties = properties;
        this.transport = transport;
    }

    @Override
    public String providerName() { return "bailian"; }

    @Override
    public SpeechToTextResult transcribe(SpeechToTextRequest request) {
        SpeechToTextRequestValidator.validate(request);
        URI endpoint = validateSettings();
        byte[] body = body(request);
        long started = System.nanoTime();
        BailianAsrTransport.Response response;
        try {
            // As with the existing provider, the provider's configured timeout controls the HTTP call.
            response = transport.send(endpoint, properties.getApiKey(), body, properties.getRequestTimeout());
        } catch (AsrProviderException exception) {
            // Preserve classification, but never trust a transport's message or cause.
            throw new AsrProviderException("Bailian ASR transport failed", exception.retryable(),
                exception.statusCode().orElse(null));
        } catch (RuntimeException exception) {
            throw new AsrProviderException("Bailian ASR network call failed", true);
        }
        if (response == null) { throw invalidResponse(); }
        int status = response.statusCode();
        if (status < 200 || status >= 300) {
            throw new AsrProviderException("Bailian ASR request failed with HTTP " + status,
                status == 408 || status == 429 || (status >= 500 && status <= 599), status);
        }
        String text = responseText(response.body());
        // Non-streaming output.text is cumulative; sentence can describe only the last sentence.
        // Let the existing measured-chunk timing fallback handle the full transcript.
        return new SpeechToTextResult(providerName(), request.language(), text,
            text.isBlank() ? List.of() : List.of(new TranscribedSegment(0, 0, 0, text)),
            Duration.ofNanos(System.nanoTime() - started), 0L,
            Map.of("segmentTimingSource", "provider_not_available",
                "providerLanguageHintSupported", true));
    }

    private URI validateSettings() {
        try {
            URI uri = URI.create(properties.getEndpoint());
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null
                || uri.getRawUserInfo() != null || uri.getRawQuery() != null || uri.getRawFragment() != null
                || uri.getPath().isBlank()) {
                throw invalid("endpoint must be an HTTPS URL without credentials, query or fragment");
            }
            // These payloads cannot be sent to filetrans or OpenAI-compatible endpoints.
            if (!SYNCHRONOUS_PATH.equals(uri.getRawPath())) {
                throw invalid("endpoint must use the synchronous ASR path");
            }
            if (properties.getApiKey() == null || properties.getApiKey().isBlank()
                || properties.getApiKey().chars().anyMatch(Character::isWhitespace)) {
                throw invalid("credential is missing or invalid");
            }
            if (properties.getModel() == null || !SYNCHRONOUS_MODELS.contains(properties.getModel())) {
                throw invalid("model must be a verified synchronous Qwen-Audio/Fun-ASR-Flash model");
            }
            if (properties.getRequestTimeout() == null || properties.getRequestTimeout().isNegative()
                || properties.getRequestTimeout().isZero() || properties.getMaxAudioFileSize() == null
                || properties.getMaxAudioFileSize().toBytes() <= 0) {
                throw invalid("timeout and audio size limit must be positive");
            }
            String context = properties.getContext();
            if (context == null || context.codePointCount(0, context.length()) > 400) {
                throw invalid("context must contain at most 400 characters");
            }
            Map<String, Integer> vocabulary = properties.getVocabulary();
            if (vocabulary == null || vocabulary.size() > 2000) { throw invalid("vocabulary is invalid"); }
            long superWords = 0;
            for (var entry : vocabulary.entrySet()) {
                Integer weight = entry.getValue();
                if (entry.getKey() == null || entry.getKey().isBlank() || weight == null
                    || !(weight >= 1 && weight <= 5 || weight == 50)) {
                    throw invalid("vocabulary entry is invalid");
                }
                if (weight == 50) { superWords++; }
            }
            if (superWords > 50) { throw invalid("too many super hotwords"); }
            if (!vocabulary.isEmpty() && !Set.of("qwen-audio-3.1-asr-flash", "qwen-audio-3.0-asr-flash")
                .contains(properties.getModel())) {
                throw invalid("instant vocabulary is not verified for this model");
            }
            return uri;
        } catch (IllegalArgumentException | NullPointerException exception) {
            throw invalid("settings are invalid");
        }
    }

    private byte[] body(SpeechToTextRequest request) {
        try {
            long size = Files.size(request.audioFile());
            if (size <= 0 || size > properties.getMaxAudioFileSize().toBytes()
                || 4 * ((size + 2) / 3) + 22 > MAX_ENCODED_BYTES) {
                throw invalid("audio file exceeds configured or Base64 limit");
            }
            AudioFileFormat audio = AudioSystem.getAudioFileFormat(request.audioFile().toFile());
            float frameRate = audio.getFormat().getFrameRate();
            if (!AudioFileFormat.Type.WAVE.equals(audio.getType()) || !Float.isFinite(frameRate)
                || frameRate <= 0 || audio.getFrameLength() <= 0
                || audio.getFrameLength() / (double) frameRate >= 300) {
                throw invalid("expected WAV audio shorter than five minutes");
            }
            var parameters = new LinkedHashMap<String, Object>();
            parameters.put("format", "wav");
            if (properties.isLanguageHintEnabled()) {
                String language = request.language().strip().toLowerCase(Locale.ROOT).replace('_', '-').split("-", 2)[0];
                if (!language.equals("auto")) {
                    if (!LANGUAGES.contains(language)) { throw invalid("language hint is unsupported"); }
                    parameters.put("language_hints", List.of(language));
                }
            }
            if (!properties.getVocabulary().isEmpty()) { parameters.put("vocabulary", properties.getVocabulary()); }
            List<Object> messages = new ArrayList<>();
            if (!properties.getContext().isBlank()) {
                messages.add(Map.of("role", "user", "content",
                    List.of(Map.of("type", "input_text", "text", properties.getContext()))));
            }
            // Bound the read too: a concurrently growing file must not bypass the allocation limit.
            byte[] audioBytes;
            try (var stream = Files.newInputStream(request.audioFile())) {
                audioBytes = stream.readNBytes(Math.toIntExact(size + 1));
            }
            if (audioBytes.length != size) { throw invalid("audio file changed during upload"); }
            messages.add(Map.of("role", "user", "content", List.of(Map.of("type", "input_audio",
                "input_audio", Map.of("data", "data:audio/wav;base64," + Base64.getEncoder().encodeToString(audioBytes))))));
            return mapper.writeValueAsBytes(Map.of("model", properties.getModel(),
                "input", Map.of("messages", messages), "parameters", parameters));
        } catch (IOException | UnsupportedAudioFileException exception) {
            throw new AsrProviderException("Bailian ASR audio or request cannot be read", false);
        }
    }

    private String responseText(String body) {
        try {
            JsonNode root = mapper.readTree(body);
            if (root == null || !root.isObject() || root.hasNonNull("code")) { throw invalidResponse(); }
            JsonNode output = root.path("output");
            JsonNode text = output.path("text");
            if (text.isMissingNode()) { text = output.path("output").path("sentence").path("text"); }
            if (text.isMissingNode()) { text = output.path("sentence").path("text"); }
            if (!text.isTextual()) { throw invalidResponse(); }
            return text.textValue().strip();
        } catch (IOException | IllegalArgumentException exception) {
            throw invalidResponse();
        }
    }

    private static AsrProviderException invalidResponse() {
        return new AsrProviderException("Bailian ASR response is invalid", false);
    }
    private static AsrProviderException invalid(String reason) {
        return new AsrProviderException("Bailian ASR configuration is invalid: " + reason, false);
    }
}
