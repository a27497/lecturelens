package com.example.courselingo.ai.asr;

import com.example.courselingo.systemmodel.*;

import org.springframework.util.unit.DataSize;

import java.time.Duration;
import java.util.Map;

/**
 * Factories have no selected provider or credential; each invocation creates an isolated adapter.
 */
public final class AsrAdapterFactories {
    private AsrAdapterFactories() {}

    public static AsrAdapterFactory bailian(SystemModelHttpClient http, SystemModelUrlPolicy urls) {
        var environmentTransports =
                new java.util.concurrent.ConcurrentHashMap<Long, BailianAsrTransport>();
        return new AsrAdapterFactory() {
            public SystemModelProtocol protocol() {
                return SystemModelProtocol.BAILIAN_ASR;
            }

            public SpeechToTextProvider create(SystemModelResolvedRoute route, String credential) {
                var options = route.asr();
                var properties = new BailianAsrProperties();
                properties.setEndpoint(route.baseUrl());
                properties.setModel(route.model());
                properties.setApiKey(credential);
                properties.setRequestTimeout(Duration.ofMillis(route.timeoutMillis()));
                properties.setMaxAudioFileSize(DataSize.ofBytes(options.bailianMaxAudioBytes()));
                properties.setConnectTimeout(Duration.ofMillis(options.bailianConnectMillis()));
                properties.setLanguageHintEnabled(options.languageHintEnabled());
                properties.setContext(options.context());
                properties.setVocabulary(options.vocabulary());
                BailianAsrTransport transport =
                        "DATABASE".equals(route.source())
                                ? (endpoint, key, body, timeout) -> {
                                    check(urls, endpoint);
                                    var response =
                                            post(
                                                    http,
                                                    endpoint,
                                                    Map.of(
                                                            "Authorization",
                                                            "Bearer " + key,
                                                            "X-DashScope-SSE",
                                                            "disable"),
                                                    "application/json",
                                                    body,
                                                    timeout);
                                    return new BailianAsrTransport.Response(
                                            response.statusCode(), response.body());
                                }
                                : environmentTransports.computeIfAbsent(
                                        options.bailianConnectMillis(),
                                        ignored ->
                                                new JavaHttpBailianAsrTransport(
                                                        properties.getConnectTimeout()));
                return new BailianAsrProvider(properties, transport);
            }
        };
    }

    public static AsrAdapterFactory siliconFlow(
            SystemModelHttpClient http, SystemModelUrlPolicy urls) {
        var environmentClients =
                new java.util.concurrent.ConcurrentHashMap<Long, SiliconFlowAsrClient>();
        return new AsrAdapterFactory() {
            public SystemModelProtocol protocol() {
                return SystemModelProtocol.SILICONFLOW_ASR;
            }

            public SpeechToTextProvider create(SystemModelResolvedRoute route, String credential) {
                var properties = new SiliconFlowAsrProperties();
                properties.setBaseUrl(route.baseUrl());
                properties.setModel(route.model());
                properties.setApiKey(credential);
                properties.setRequestTimeout(Duration.ofMillis(route.timeoutMillis()));
                properties.setConnectTimeout(
                        Duration.ofMillis(route.asr().siliconFlowConnectMillis()));
                properties.setMaxAudioFileSize(
                        DataSize.ofBytes(route.asr().siliconFlowMaxAudioBytes()));
                SiliconFlowAsrClient client =
                        "DATABASE".equals(route.source())
                                ? new JavaHttpSiliconFlowAsrClient(
                                        request -> {
                                            check(urls, request.uri());
                                            var response =
                                                    post(
                                                            http,
                                                            request.uri(),
                                                            request.headers(),
                                                            request.contentType(),
                                                            request.body(),
                                                            request.timeout());
                                            // Upstream headers are untrusted and are not needed for
                                            // runtime routing.
                                            return new SiliconFlowAsrClientResponse(
                                                    response.statusCode(),
                                                    response.body(),
                                                    Map.of(),
                                                    response.duration());
                                        })
                                : environmentClients.computeIfAbsent(
                                        route.asr().siliconFlowConnectMillis(),
                                        ignored ->
                                                new JavaHttpSiliconFlowAsrClient(
                                                        properties.getConnectTimeout()));
                return new SiliconFlowAsrProvider(properties, client);
            }
        };
    }

    private static void check(SystemModelUrlPolicy urls, java.net.URI uri) {
        try {
            urls.normalize(uri.toString());
            // DNS validation belongs inside the bounded transport deadline.
        } catch (RuntimeException ignored) {
            throw new AsrCallFailure(AsrCallFailure.Category.INVALID_REQUEST, false, null);
        }
    }

    private static com.example.courselingo.ai.llm.OpenAiCompatibleClientResponse post(
            SystemModelHttpClient http,
            java.net.URI uri,
            Map<String, String> headers,
            String contentType,
            byte[] body,
            Duration timeout) {
        try {
            return http.post(uri, headers, contentType, body, timeout);
        } catch (SystemModelCallFailure failure) {
            AsrCallFailure.Category category;
            try {
                category = AsrCallFailure.Category.valueOf(failure.category());
            } catch (IllegalArgumentException ignored) {
                category = AsrCallFailure.Category.OUTPUT_INVALID;
            }
            throw new AsrCallFailure(
                    category, failure.details().retryable(), failure.details().httpStatus());
        } catch (com.example.courselingo.common.exception.BusinessException forbidden) {
            throw new AsrCallFailure(AsrCallFailure.Category.INVALID_REQUEST, false, null);
        }
    }
}
