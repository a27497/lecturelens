package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.*;

import com.example.courselingo.ai.llm.*;
import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.*;

import java.net.InetSocketAddress;
import java.net.URI;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

class SystemModelHttpClientTest {
    private HttpServer server;
    private SystemModelHttpClient client;

    @BeforeEach
    void setup() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        client = new SystemModelHttpClient(128);
    }

    @AfterEach
    void cleanup() {
        server.stop(0);
        client.close();
    }

    private OpenAiCompatibleChatCompletionRequest request(String path, long millis) {
        return new OpenAiCompatibleChatCompletionRequest(
                URI.create("http://127.0.0.1:" + server.getAddress().getPort() + path),
                Map.of("Authorization", "Bearer synthetic-http-test-key"),
                "POST",
                "application/json",
                "{}",
                Duration.ofMillis(millis));
    }

    @Test
    void binaryMultipartPostPreservesAllBytes() {
        byte[] body = new byte[] {0, 1, 13, 10, (byte) 255};
        var received = new java.util.concurrent.atomic.AtomicReference<byte[]>();
        server.createContext("/binary", exchange -> {
            received.set(exchange.getRequestBody().readAllBytes());
            exchange.sendResponseHeaders(200, 2);
            exchange.getResponseBody().write("{}".getBytes(java.nio.charset.StandardCharsets.UTF_8));
            exchange.close();
        });
        server.start();
        var response = client.post(request("/binary", 3000).uri(), Map.of(),
                "multipart/form-data; boundary=test", body, Duration.ofSeconds(3));
        assertThat(received.get()).containsExactly(body);
        assertThat(response.statusCode()).isEqualTo(200);
    }

    @Test
    void redirectsAreNeverFollowed() {
        var followed = new AtomicInteger();
        server.createContext(
                "/redirect",
                exchange -> {
                    exchange.getResponseHeaders().add("Location", "/target");
                    exchange.sendResponseHeaders(302, -1);
                    exchange.close();
                });
        server.createContext(
                "/target",
                exchange -> {
                    followed.incrementAndGet();
                    exchange.sendResponseHeaders(200, -1);
                    exchange.close();
                });
        server.start();
        assertThatThrownBy(() -> client.complete(request("/redirect", 3000)))
                .isInstanceOf(SystemModelCallFailure.class)
                .hasMessageContaining("REDIRECT_FORBIDDEN")
                .hasNoCause();
        assertThat(followed.get()).isZero();
    }

    @Test
    void chunkedBodiesAreStoppedAtLimit() {
        server.createContext(
                "/large",
                exchange -> {
                    exchange.sendResponseHeaders(200, 0);
                    try (var output = exchange.getResponseBody()) {
                        output.write(new byte[1024]);
                    } catch (Exception ignored) {
                    }
                    exchange.close();
                });
        server.start();
        assertThatThrownBy(() -> client.complete(request("/large", 3000)))
                .isInstanceOf(SystemModelCallFailure.class)
                .hasMessageContaining("RESPONSE_TOO_LARGE")
                .hasNoCause();
    }

    @Test
    void deadlineIncludesSlowResponseBody() {
        server.createContext(
                "/slow",
                exchange -> {
                    exchange.sendResponseHeaders(200, 0);
                    try (var output = exchange.getResponseBody()) {
                        output.write(1);
                        output.flush();
                        Thread.sleep(1000);
                        output.write(2);
                    } catch (Exception ignored) {
                    }
                    exchange.close();
                });
        server.start();
        long started = System.nanoTime();
        assertThatThrownBy(() -> client.complete(request("/slow", 100)))
                .isInstanceOf(SystemModelCallFailure.class)
                .hasMessageContaining("TIMEOUT")
                .hasNoCause();
        assertThat(Duration.ofNanos(System.nanoTime() - started)).isLessThan(Duration.ofSeconds(3));
    }

    @Test
    void ignoresJvmDefaultProxy() {
        var previous = java.net.ProxySelector.getDefault();
        var selections = new AtomicInteger();
        java.net.ProxySelector.setDefault(
                new java.net.ProxySelector() {
                    @Override
                    public java.util.List<java.net.Proxy> select(URI uri) {
                        selections.incrementAndGet();
                        throw new AssertionError("environment proxy used");
                    }

                    @Override
                    public void connectFailed(
                            URI u, java.net.SocketAddress a, java.io.IOException failure) {}
                });
        try {
            client.close();
            client = new SystemModelHttpClient(128);
            server.createContext(
                    "/ok",
                    exchange -> {
                        byte[] body = "{}".getBytes();
                        exchange.sendResponseHeaders(200, body.length);
                        exchange.getResponseBody().write(body);
                        exchange.close();
                    });
            server.start();
            assertThat(client.complete(request("/ok", 3000)).statusCode()).isEqualTo(200);
            assertThat(selections.get()).isZero();
        } finally {
            java.net.ProxySelector.setDefault(previous);
        }
    }
}
