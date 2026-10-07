package com.example.courselingo.ai.asr;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class JavaHttpBailianAsrTransportTest {
    @ParameterizedTest
    @ValueSource(ints = {200, 302})
    void sendsActualHttpHeadersAndBodyWithoutFollowingRedirects(int status) throws Exception {
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        AtomicReference<String> authorization = new AtomicReference<>();
        AtomicReference<String> contentType = new AtomicReference<>();
        AtomicReference<String> sse = new AtomicReference<>();
        AtomicReference<String> method = new AtomicReference<>();
        AtomicReference<String> async = new AtomicReference<>();
        AtomicReference<String> received = new AtomicReference<>();
        server.createContext("/asr", exchange -> {
            method.set(exchange.getRequestMethod());
            async.set(exchange.getRequestHeaders().getFirst("X-DashScope-Async"));
            authorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
            contentType.set(exchange.getRequestHeaders().getFirst("Content-Type"));
            sse.set(exchange.getRequestHeaders().getFirst("X-DashScope-SSE"));
            received.set(new String(exchange.getRequestBody().readAllBytes()));
            exchange.getResponseHeaders().add("Location", "/must-not-follow");
            byte[] response = "{\"output\":{\"text\":\"hello\"}}".getBytes(java.nio.charset.StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        });
        server.start();
        try {
            var response = new JavaHttpBailianAsrTransport(Duration.ofSeconds(1)).send(
                URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/asr"),
                "fake-credential", "{\"test\":true}".getBytes(), Duration.ofSeconds(2));
            assertThat(response.statusCode()).isEqualTo(status);
            assertThat(response.body()).isEqualTo("{\"output\":{\"text\":\"hello\"}}");
            assertThat(method).hasValue("POST");
            assertThat(async.get()).isNull();
            assertThat(authorization).hasValue("Bearer fake-credential");
            assertThat(contentType).hasValue("application/json");
            assertThat(sse).hasValue("disable");
            assertThat(received).hasValue("{\"test\":true}");
        } finally { server.stop(0); }
    }

    @Test
    void networkTimeoutAndInterruptionAreRetryableWithNoUnsafeCause() throws Exception {
        for (Exception failure : new Exception[] {new HttpTimeoutException("fake-credential"),
            new IOException("Authorization: Bearer fake-credential"), new InterruptedException("data:audio/wav;base64,AAAA")}) {
            HttpClient client = mock(HttpClient.class);
            when(client.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class))).thenThrow(failure);
            try {
                assertThatThrownBy(() -> new JavaHttpBailianAsrTransport(client).send(URI.create("https://example.com/asr"),
                    "fake-credential", new byte[0], Duration.ofSeconds(1))).satisfies(error -> {
                        assertThat(error).isInstanceOf(AsrProviderException.class);
                        assertThat(((AsrProviderException) error).retryable()).isTrue();
                        assertThat(error.getCause()).isNull();
                        assertThat(error.toString()).doesNotContain("fake-credential", "Authorization", "AAAA");
                    });
                assertThat(Thread.currentThread().isInterrupted()).isEqualTo(failure instanceof InterruptedException);
            } finally { Thread.interrupted(); }
        }
    }
}
