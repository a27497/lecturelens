package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.llm.*;

import java.io.ByteArrayOutputStream;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.SocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;

public final class SystemModelHttpClient implements OpenAiCompatibleLlmClient, AutoCloseable {
    private final HttpClient http;
    private final int responseLimit;

    public SystemModelHttpClient(int responseLimit) {
        this.responseLimit = responseLimit;
        this.http =
                HttpClient.newBuilder()
                        .connectTimeout(Duration.ofSeconds(3))
                        .followRedirects(HttpClient.Redirect.NEVER)
                        .proxy(
                                new ProxySelector() {
                                    @Override
                                    public List<Proxy> select(URI uri) {
                                        return List.of(Proxy.NO_PROXY);
                                    }

                                    @Override
                                    public void connectFailed(
                                            URI uri,
                                            SocketAddress address,
                                            java.io.IOException failure) {}
                                })
                        .build();
    }

    @Override
    public OpenAiCompatibleClientResponse complete(OpenAiCompatibleChatCompletionRequest request) {
        return post(
                request.uri(),
                request.headers(),
                request.contentType(),
                request.body().getBytes(StandardCharsets.UTF_8),
                request.timeout());
    }

    public OpenAiCompatibleClientResponse post(
            URI uri,
            java.util.Map<String, String> headers,
            String contentType,
            byte[] body,
            Duration timeout) {
        long start = System.nanoTime();
        CompletableFuture<HttpResponse<byte[]>> pending = null;
        try {
            var builder =
                    HttpRequest.newBuilder(uri)
                            .timeout(timeout)
                            .header("Content-Type", contentType);
            headers.forEach(builder::header);
            var httpRequest = builder.POST(HttpRequest.BodyPublishers.ofByteArray(body)).build();
            pending = http.sendAsync(httpRequest, ignored -> new LimitedBody(responseLimit));
            var response = pending.get(timeout.toMillis(), TimeUnit.MILLISECONDS);
            if (response.statusCode() >= 300 && response.statusCode() < 400)
                throw failure("REDIRECT_FORBIDDEN", LlmProviderFailureCategory.INVALID_REQUEST);
            if (response.headers()
                    .firstValue("Content-Encoding")
                    .filter(v -> !v.equalsIgnoreCase("identity"))
                    .isPresent())
                throw failure("ENCODING_UNSUPPORTED", LlmProviderFailureCategory.OUTPUT_INVALID);
            return new OpenAiCompatibleClientResponse(
                    response.statusCode(),
                    new String(response.body(), StandardCharsets.UTF_8),
                    response.headers().map(),
                    Duration.ofNanos(System.nanoTime() - start));
        } catch (SystemModelCallFailure safe) {
            throw safe;
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
            throw failure("CANCELLED", LlmProviderFailureCategory.NETWORK);
        } catch (Exception failure) {
            if (failure instanceof java.util.concurrent.TimeoutException
                    || failure.getCause() instanceof java.net.http.HttpTimeoutException)
                throw failure("TIMEOUT", LlmProviderFailureCategory.TIMEOUT);
            Throwable current = failure;
            for (int depth = 0; current != null && depth < 8; depth++, current = current.getCause())
                if (current instanceof SystemModelCallFailure safe) throw safe;
            throw failure("NETWORK", LlmProviderFailureCategory.NETWORK);
        } finally {
            if (pending != null && !pending.isDone()) pending.cancel(true);
        }
    }

    @Override
    public void close() {
        http.shutdownNow();
    }

    private static SystemModelCallFailure failure(
            String category, LlmProviderFailureCategory failure) {
        return new SystemModelCallFailure(
                category,
                failure,
                null,
                failure == LlmProviderFailureCategory.TIMEOUT
                        || failure == LlmProviderFailureCategory.NETWORK);
    }

    private static final class LimitedBody implements HttpResponse.BodySubscriber<byte[]> {
        private final int limit;
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        private final CompletableFuture<byte[]> result = new CompletableFuture<>();
        private Flow.Subscription subscription;

        LimitedBody(int limit) {
            this.limit = limit;
        }

        @Override
        public CompletionStage<byte[]> getBody() {
            return result;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(List<ByteBuffer> chunks) {
            for (var chunk : chunks) {
                if (chunk.remaining() > limit - bytes.size()) {
                    subscription.cancel();
                    result.completeExceptionally(
                            failure(
                                    "RESPONSE_TOO_LARGE",
                                    LlmProviderFailureCategory.OUTPUT_INVALID));
                    return;
                }
                byte[] part = new byte[chunk.remaining()];
                chunk.get(part);
                bytes.writeBytes(part);
            }
            subscription.request(1);
        }

        @Override
        public void onError(Throwable ignored) {
            result.completeExceptionally(failure("NETWORK", LlmProviderFailureCategory.NETWORK));
        }

        @Override
        public void onComplete() {
            result.complete(bytes.toByteArray());
        }
    }
}
