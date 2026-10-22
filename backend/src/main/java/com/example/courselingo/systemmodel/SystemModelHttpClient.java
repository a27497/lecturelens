package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.common.exception.BusinessException;
import okhttp3.*;

import java.net.Proxy;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/** Bounded database-route transport; deployment-owned ENV adapters retain their legacy semantics. */
public final class SystemModelHttpClient implements OpenAiCompatibleLlmClient, AutoCloseable {
    private final OkHttpClient http;
    private final SystemModelUrlPolicy addresses;
    private final int responseLimit;

    public SystemModelHttpClient(int responseLimit) {
        this(responseLimit, new SystemModelUrlPolicy());
    }

    SystemModelHttpClient(int responseLimit, SystemModelUrlPolicy addresses) {
        this.responseLimit = responseLimit;
        this.addresses = addresses;
        this.http = new OkHttpClient.Builder()
                .connectTimeout(Duration.ofSeconds(3))
                .readTimeout(Duration.ZERO)
                .writeTimeout(Duration.ZERO)
                .proxy(Proxy.NO_PROXY)
                // Socket() can still consult the JVM SOCKS selector even with an HTTP NO_PROXY.
                .socketFactory(new DirectSockets())
                .followRedirects(false)
                .followSslRedirects(false)
                .retryOnConnectionFailure(false)
                .addNetworkInterceptor(chain -> {
                    var response = chain.proceed(chain.request());
                    chain.request().tag(WireHeaders.class).value = response.headers();
                    // OkHttp can repeat a 503/Retry-After:0 even with connection retries off.
                    // Preserve the original headers for our caller; only its bounded policy retries.
                    return response.code() == 503
                            ? response.newBuilder().removeHeader("Retry-After").build() : response;
                })
                // Preserve the original hostname for Host, SNI and certificate verification.
                // The resolver returns the checked IPs consumed by the actual socket.
                .dns(host -> Arrays.asList(addresses.publicAddresses(host)))
                .protocols(List.of(Protocol.HTTP_1_1))
                .connectionPool(new ConnectionPool(0, 1, TimeUnit.SECONDS))
                .build();
    }

    @Override
    public OpenAiCompatibleClientResponse complete(OpenAiCompatibleChatCompletionRequest request) {
        return post(request.uri(), request.headers(), request.contentType(),
                request.body().getBytes(StandardCharsets.UTF_8), request.timeout());
    }

    public OpenAiCompatibleClientResponse post(URI uri, Map<String, String> headers,
            String contentType, byte[] body, Duration timeout) {
        long start = System.nanoTime();
        try {
            // Literal IP hosts bypass OkHttp's DNS callback, so validate them here as well.
            addresses.checkDestination(uri);
            var original = new WireHeaders();
            var builder = new Request.Builder().url(uri.toString())
                    .tag(WireHeaders.class, original)
                    .post(RequestBody.create(body, MediaType.get(contentType)))
                    .header("Accept-Encoding", "identity");
            headers.forEach(builder::header);
            var call = http.newCall(builder.build());
            // Preflight consumes the same deadline; expiry must prevent the external send.
            long remaining = timeout.toNanos() - (System.nanoTime() - start);
            if (remaining <= 0) throw failure("TIMEOUT", LlmProviderFailureCategory.TIMEOUT);
            call.timeout().timeout(remaining, TimeUnit.NANOSECONDS);
            try (var response = call.execute()) {
                if (response.code() >= 300 && response.code() < 400)
                    throw failure("REDIRECT_FORBIDDEN", LlmProviderFailureCategory.INVALID_REQUEST);
                String encoding = response.header("Content-Encoding");
                if (encoding != null && !encoding.equalsIgnoreCase("identity"))
                    throw failure("ENCODING_UNSUPPORTED", LlmProviderFailureCategory.OUTPUT_INVALID);
                byte[] bytes = response.body() == null ? new byte[0]
                        : response.body().byteStream().readNBytes(responseLimit + 1);
                if (bytes.length > responseLimit)
                    throw failure("RESPONSE_TOO_LARGE", LlmProviderFailureCategory.OUTPUT_INVALID);
                return new OpenAiCompatibleClientResponse(response.code(),
                        new String(bytes, StandardCharsets.UTF_8), original.value.toMultimap(),
                        Duration.ofNanos(System.nanoTime() - start));
            }
        } catch (SystemModelCallFailure | BusinessException safe) {
            throw safe;
        } catch (java.io.InterruptedIOException timeoutFailure) {
            if (Thread.currentThread().isInterrupted())
                throw failure("CANCELLED", LlmProviderFailureCategory.NETWORK);
            throw failure("TIMEOUT", LlmProviderFailureCategory.TIMEOUT);
        } catch (Exception ignored) {
            throw failure("NETWORK", LlmProviderFailureCategory.NETWORK);
        }
    }

    private static final class WireHeaders { Headers value; }

    @Override
    public void close() {
        http.dispatcher().cancelAll();
        http.dispatcher().executorService().shutdownNow();
        http.connectionPool().evictAll();
    }

    private static SystemModelCallFailure failure(String category, LlmProviderFailureCategory type) {
        return new SystemModelCallFailure(category, type, null,
                type == LlmProviderFailureCategory.TIMEOUT || type == LlmProviderFailureCategory.NETWORK);
    }

    private static final class DirectSockets extends javax.net.SocketFactory {
        @Override public java.net.Socket createSocket() { return new java.net.Socket(Proxy.NO_PROXY); }
        @Override public java.net.Socket createSocket(String host, int port) throws java.io.IOException {
            throw new java.net.SocketException("Unconnected sockets required");
        }
        @Override public java.net.Socket createSocket(String host, int port, java.net.InetAddress local, int localPort) throws java.io.IOException {
            throw new java.net.SocketException("Unconnected sockets required");
        }
        @Override public java.net.Socket createSocket(java.net.InetAddress host, int port) throws java.io.IOException {
            throw new java.net.SocketException("Unconnected sockets required");
        }
        @Override public java.net.Socket createSocket(java.net.InetAddress host, int port, java.net.InetAddress local, int localPort) throws java.io.IOException {
            throw new java.net.SocketException("Unconnected sockets required");
        }
    }
}
