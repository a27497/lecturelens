package com.example.courselingo.ai.asr;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.util.unit.DataSize;

public class SiliconFlowAsrProvider implements SpeechToTextProvider {

    public static final String PROVIDER_NAME = "siliconflow";
    static final String TRANSCRIPTIONS_PATH = "/v1/audio/transcriptions";
    private static final int MAX_MODEL_LENGTH = 128;

    private final SiliconFlowAsrProperties properties;
    private final SiliconFlowAsrClient client;
    private final ObjectMapper objectMapper;

    public SiliconFlowAsrProvider(SiliconFlowAsrProperties properties, SiliconFlowAsrClient client) {
        this(properties, client, new ObjectMapper());
    }

    SiliconFlowAsrProvider(SiliconFlowAsrProperties properties, SiliconFlowAsrClient client, ObjectMapper objectMapper) {
        this.properties = properties;
        this.client = client;
        this.objectMapper = objectMapper;
    }

    @Override
    public SpeechToTextResult transcribe(SpeechToTextRequest request) {
        SpeechToTextRequestValidator.validate(request);
        ValidatedSettings settings = validateSettings();
        validateAudioSize(request.audioFile(), settings.maxAudioFileSize());

        SiliconFlowAsrClientResponse response = callClient(request, settings);
        handleErrorStatus(response);
        return mapSuccessResponse(request, response, settings);
    }

    @Override
    public String providerName() {
        return PROVIDER_NAME;
    }

    private SiliconFlowAsrClientResponse callClient(SpeechToTextRequest request, ValidatedSettings settings) {
        SiliconFlowAsrClientRequest clientRequest = new SiliconFlowAsrClientRequest(
            settings.uri(),
            Map.of("Authorization", "Bearer " + settings.apiKey()),
            request.audioFile(),
            "file",
            Map.of("model", settings.model()),
            settings.requestTimeout()
        );
        try {
            return client.transcribe(clientRequest);
        } catch (SiliconFlowAsrException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new SiliconFlowAsrException("SiliconFlow ASR network call failed", true, exception);
        }
    }

    private SpeechToTextResult mapSuccessResponse(
        SpeechToTextRequest request,
        SiliconFlowAsrClientResponse response,
        ValidatedSettings settings
    ) {
        SiliconFlowAsrResponse payload;
        try {
            payload = objectMapper.readValue(response.body(), SiliconFlowAsrResponse.class);
        } catch (JsonProcessingException exception) {
            throw new SiliconFlowAsrException("SiliconFlow ASR response JSON is invalid", false, exception);
        }

        String text = payload.text() == null ? "" : payload.text().strip();
        List<TranscribedSegment> segments = new ArrayList<>();
        if (!text.isBlank()) {
            segments.add(new TranscribedSegment(0, 0, 0, text));
        }

        Map<String, Object> metadata = new HashMap<>();
        metadata.put("model", settings.model());
        metadata.put("segmentTimingSource", "provider_not_available");
        traceId(response).ifPresent(traceId -> metadata.put("providerTraceId", traceId));

        return new SpeechToTextResult(
            providerName(),
            request.language(),
            text,
            segments,
            response.duration(),
            0L,
            metadata
        );
    }

    private void handleErrorStatus(SiliconFlowAsrClientResponse response) {
        if (response.statusCode() >= 200 && response.statusCode() < 300) {
            return;
        }
        boolean retryable = isRetryableStatus(response.statusCode());
        throw new SiliconFlowAsrException(
            "SiliconFlow ASR request failed with HTTP " + response.statusCode() + ": " + response.body(),
            retryable,
            response.statusCode()
        );
    }

    private ValidatedSettings validateSettings() {
        String apiKey = requireText(properties.getApiKey(), "API key is required");
        String model = requireText(properties.getModel(), "model is required");
        if (model.length() > MAX_MODEL_LENGTH) {
            throw invalid("model is too long");
        }
        Duration requestTimeout = positiveDuration(properties.getRequestTimeout(), "request timeout must be positive");
        DataSize maxAudioFileSize = properties.getMaxAudioFileSize();
        if (maxAudioFileSize == null || maxAudioFileSize.toBytes() <= 0) {
            throw invalid("max audio file size must be positive");
        }
        return new ValidatedSettings(apiKey, model, fixedTranscriptionUri(properties.getBaseUrl()), requestTimeout, maxAudioFileSize);
    }

    private void validateAudioSize(java.nio.file.Path audioFile, DataSize maxAudioFileSize) {
        try {
            long size = Files.size(audioFile);
            if (size > maxAudioFileSize.toBytes()) {
                throw invalid("audio file exceeds configured limit");
            }
        } catch (IOException exception) {
            throw new SiliconFlowAsrException("audio file size cannot be read", false, exception);
        }
    }

    private URI fixedTranscriptionUri(String baseUrl) {
        String trimmed = requireText(baseUrl, "base URL is required");
        try {
            URI baseUri = new URI(trimmed);
            String scheme = baseUri.getScheme();
            if (scheme == null || (!scheme.equalsIgnoreCase("http") && !scheme.equalsIgnoreCase("https"))) {
                throw invalid("base URL must use http or https");
            }
            if (baseUri.getRawAuthority() == null || baseUri.getRawAuthority().isBlank()) {
                throw invalid("base URL host is required");
            }
            return new URI(
                scheme.toLowerCase(Locale.ROOT),
                baseUri.getRawAuthority(),
                TRANSCRIPTIONS_PATH,
                null,
                null
            );
        } catch (URISyntaxException exception) {
            throw new SiliconFlowAsrException("base URL is invalid", false, exception);
        }
    }

    private static String requireText(String value, String message) {
        if (value == null || value.isBlank()) {
            throw invalid(message);
        }
        return value.strip();
    }

    private static Duration positiveDuration(Duration duration, String message) {
        if (duration == null || duration.isZero() || duration.isNegative()) {
            throw invalid(message);
        }
        return duration;
    }

    private static SiliconFlowAsrException invalid(String message) {
        return new SiliconFlowAsrException("SiliconFlow ASR configuration is invalid: " + message, false);
    }

    private static boolean isRetryableStatus(int statusCode) {
        return statusCode == 408
            || statusCode == 429
            || statusCode == 500
            || statusCode == 502
            || statusCode == 503
            || statusCode == 504;
    }

    private static java.util.Optional<String> traceId(SiliconFlowAsrClientResponse response) {
        return response.headers().entrySet().stream()
            .filter(entry -> "x-siliconcloud-trace-id".equalsIgnoreCase(entry.getKey()))
            .flatMap(entry -> entry.getValue().stream())
            .map(String::strip)
            .filter(value -> !value.isBlank())
            .filter(value -> !AsrErrorSanitizer.containsSensitiveData(value))
            .findFirst();
    }

    private record ValidatedSettings(
        String apiKey,
        String model,
        URI uri,
        Duration requestTimeout,
        DataSize maxAudioFileSize
    ) {
    }
}
