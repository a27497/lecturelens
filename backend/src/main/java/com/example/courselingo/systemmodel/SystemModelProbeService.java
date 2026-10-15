package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.asr.*;
import com.example.courselingo.ai.llm.LlmProviderFailureCategory;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.net.URI;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;

/** Explicit administrator action only. Results contain no vendor response or transcript. */
public final class SystemModelProbeService implements AutoCloseable {
    public static final int RESPONSE_LIMIT_BYTES = 65536;
    private final SystemModelRegistry registry;
    private final SystemModelHttpClient http;
    private final SystemModelUrlPolicy urls;
    private final Set<String> allowedOrigins;
    private final Duration timeout;
    private final int concurrency;
    private final ThreadPoolExecutor workers;
    private final Path audio;
    private final String fixtureSha256;
    private final ObjectMapper json =
            new ObjectMapper()
                    .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                    .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);

    public record Command(long expectedVersion, long modelId) {}

    public record Result(
            boolean ok,
            String category,
            long elapsedMillis,
            long version,
            long modelId,
            String finalUrl) {}

    public record Policy(
            List<String> allowedOrigins,
            long timeoutMillis,
            int concurrency,
            int responseLimitBytes,
            String asrFixtureSha256) {}

    SystemModelProbeService(
            SystemModelRegistry registry, SystemModelUrlPolicy urls, String allowedOrigins) {
        this(
                registry,
                urls,
                new SystemModelHttpClient(RESPONSE_LIMIT_BYTES),
                allowedOrigins,
                Duration.ofSeconds(10),
                2);
    }

    SystemModelProbeService(
            SystemModelRegistry registry,
            SystemModelUrlPolicy urls,
            SystemModelHttpClient http,
            String allowedOrigins,
            Duration timeout,
            int concurrency) {
        this.registry = registry;
        this.urls = urls;
        this.http = http;
        this.timeout = timeout;
        this.concurrency = concurrency;
        var origins = new TreeSet<String>();
        try {
            if (allowedOrigins.length() > 8192) throw new IllegalArgumentException();
            for (String value : allowedOrigins.split(",")) {
                if (value.isBlank()) continue;
                URI uri = URI.create(urls.normalize(value.strip()));
                if (!uri.getPath().isEmpty()) throw new IllegalArgumentException();
                origins.add(origin(uri));
            }
        } catch (RuntimeException ignored) {
            http.close();
            throw new BusinessException(ErrorCode.SYSTEM_MODEL_CONFIG_INVALID);
        }
        this.allowedOrigins = Collections.unmodifiableSet(origins);
        this.workers =
                new ThreadPoolExecutor(
                        concurrency,
                        concurrency,
                        0,
                        TimeUnit.MILLISECONDS,
                        new SynchronousQueue<>(),
                        task -> {
                            var thread = new Thread(task, "system-model-probe");
                            thread.setDaemon(true);
                            return thread;
                        },
                        new ThreadPoolExecutor.AbortPolicy());
        try (var stream = getClass().getResourceAsStream("/system-model-probe/tone.wav")) {
            if (stream == null) throw new java.io.IOException();
            byte[] bytes = stream.readAllBytes();
            fixtureSha256 =
                    java.util.HexFormat.of()
                            .formatHex(
                                    java.security.MessageDigest.getInstance("SHA-256")
                                            .digest(bytes));
            audio = Files.createTempFile("lecturelens-asr-probe-", ".wav");
            Files.write(audio, bytes);
        } catch (Exception ignored) {
            workers.shutdownNow();
            http.close();
            throw new BusinessException(ErrorCode.SYSTEM_MODEL_CONFIG_UNAVAILABLE);
        }
    }

    public Policy policy() {
        return new Policy(
                List.copyOf(allowedOrigins),
                timeout.toMillis(),
                concurrency,
                RESPONSE_LIMIT_BYTES,
                fixtureSha256);
    }

    public Result probe(Command command, long actor) {
        if (command.expectedVersion() < 0 || command.modelId() <= 0)
            throw new BusinessException(ErrorCode.SYSTEM_MODEL_CONFIG_INVALID);
        long started = System.nanoTime();
        var endpoint = new java.util.concurrent.atomic.AtomicReference<String>();
        Future<Result> pending;
        try {
            pending = workers.submit(() -> execute(command, started, endpoint));
        } catch (RejectedExecutionException ignored) {
            return result(command, started, "BUSY", null);
        }
        Result result;
        try {
            result = pending.get(timeout.toMillis(), TimeUnit.MILLISECONDS);
        } catch (TimeoutException ignored) {
            pending.cancel(true);
            result = result(command, started, "TIMEOUT", endpoint.get());
        } catch (InterruptedException ignored) {
            pending.cancel(true);
            Thread.currentThread().interrupt();
            result = result(command, started, "CANCELLED", endpoint.get());
        } catch (ExecutionException failure) {
            if (failure.getCause() instanceof BusinessException safe
                    && safe.errorCode() == ErrorCode.SYSTEM_MODEL_CONFIG_CONFLICT) throw safe;
            result = result(command, started, "CONFIGURATION_INVALID", null);
        }
        org.slf4j.LoggerFactory.getLogger(getClass())
                .info(
                        "event=system_model_probe actorId={} version={} modelId={} category={}"
                                + " elapsedMillis={}",
                        actor,
                        result.version(),
                        result.modelId(),
                        result.category(),
                        result.elapsedMillis());
        return result;
    }

    private Result execute(
            Command command,
            long started,
            java.util.concurrent.atomic.AtomicReference<String> observedEndpoint) {
        if (registry.currentVersion() != command.expectedVersion())
            throw new BusinessException(ErrorCode.SYSTEM_MODEL_CONFIG_CONFLICT);
        String endpoint = null;
        try {
            var route = registry.probeRoute(command.expectedVersion(), command.modelId());
            URI uri = SystemModelEndpoints.finalUri(route);
            endpoint = uri.toString();
            observedEndpoint.set(endpoint);
            if (!allowedOrigins.contains(origin(uri)))
                return result(command, started, "ORIGIN_NOT_ALLOWED", endpoint);
            urls.checkDestination(uri);
            String key = registry.credential(command.expectedVersion(), route);
            if (route.protocol() == SystemModelProtocol.OPENAI_CHAT) {
                chat(route, uri, key);
            } else {
                // Never use deployment transports or Mock for probes, even for unbound models.
                var factory =
                        route.protocol() == SystemModelProtocol.BAILIAN_ASR
                                ? AsrAdapterFactories.bailian(http, urls)
                                : AsrAdapterFactories.siliconFlow(http, urls);
                factory.create(bounded(route), key)
                        .transcribe(
                                new SpeechToTextRequest(
                                        audio,
                                        "en",
                                        "system-model-probe",
                                        "system-model-probe",
                                        timeout));
            }
            return result(command, started, "OK", endpoint);
        } catch (SystemModelCallFailure safe) {
            return result(command, started, safe.category(), endpoint);
        } catch (AsrProviderException safe) {
            return result(
                    command, started, AsrCallFailure.provider(safe).category().name(), endpoint);
        } catch (BusinessException safe) {
            String category =
                    switch (safe.errorCode()) {
                        case SYSTEM_MODEL_KEY_DECRYPTION_FAILED -> "KEY_UNAVAILABLE";
                        case SYSTEM_MODEL_ADDRESS_FORBIDDEN -> "ADDRESS_FORBIDDEN";
                        default -> "CONFIGURATION_INVALID";
                    };
            return result(command, started, category, endpoint);
        } catch (Exception ignored) {
            return result(command, started, "OUTPUT_INVALID", endpoint);
        }
    }

    private void chat(SystemModelResolvedRoute route, URI uri, String key) throws Exception {
        var payload = new LinkedHashMap<String, Object>();
        payload.put("model", route.model());
        payload.put(
                "messages",
                List.of(
                        Map.of(
                                "role",
                                "user",
                                "content",
                                "Return only a JSON object: {\"ok\":true}")));
        payload.put("response_format", Map.of("type", "json_object"));
        payload.put("max_tokens", 32);
        payload.put("stream", false);
        com.example.courselingo.ai.llm.OpenAiCompatibleRequestOptionsAdapter.apply(
                payload, route.model());
        byte[] body = json.writeValueAsBytes(payload);
        var response =
                http.post(
                        uri,
                        Map.of("Authorization", "Bearer " + key),
                        "application/json",
                        body,
                        timeout);
        int status = response.statusCode();
        if (status < 200 || status >= 300) {
            String category =
                    status == 401 || status == 403
                            ? "AUTHENTICATION"
                            : status == 404
                                    ? "MODEL_NOT_FOUND"
                                    : status == 429
                                            ? "RATE_LIMIT"
                                            : status == 408
                                                    ? "TIMEOUT"
                                                    : status >= 500
                                                            ? "SERVER_ERROR"
                                                            : "INVALID_REQUEST";
            throw new SystemModelCallFailure(
                    category, LlmProviderFailureCategory.INVALID_REQUEST, status, false);
        }
        var root = json.readTree(response.body());
        var content = root.path("choices").path(0).path("message").path("content");
        if (!content.isTextual() || !json.readTree(content.asText()).isObject())
            throw new SystemModelCallFailure(
                    "OUTPUT_INVALID", LlmProviderFailureCategory.OUTPUT_INVALID, null, false);
    }

    private SystemModelResolvedRoute bounded(SystemModelResolvedRoute r) {
        return new SystemModelResolvedRoute(
                r.feature(),
                r.source(),
                r.protocol(),
                r.credentialId(),
                r.providerId(),
                r.modelId(),
                r.baseUrl(),
                r.model(),
                r.capabilities(),
                0d,
                32,
                timeout.toMillis(),
                1,
                r.hasKey(),
                r.keyLast4(),
                r.asr());
    }

    static String origin(URI uri) {
        int port = uri.getPort();
        String scheme = uri.getScheme().toLowerCase(Locale.ROOT);
        if ((scheme.equals("https") && port == 443) || (scheme.equals("http") && port == 80))
            port = -1;
        return scheme
                + "://"
                + uri.getHost().toLowerCase(Locale.ROOT)
                + (port < 0 ? "" : ":" + port);
    }

    private static Result result(Command command, long started, String category, String endpoint) {
        return new Result(
                category.equals("OK"),
                category,
                Math.max(0, Duration.ofNanos(System.nanoTime() - started).toMillis()),
                command.expectedVersion(),
                command.modelId(),
                endpoint);
    }

    public void close() {
        workers.shutdownNow();
        http.close();
        try {
            Files.deleteIfExists(audio);
        } catch (java.io.IOException ignored) {
        }
    }
}
