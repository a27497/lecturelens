package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.ai.llm.OpenAiCompatibleClientResponse;
import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.net.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

class SystemModelProbeTransportTest {
    private HttpServer server;
    private SystemModelRegistry registry;
    private SystemModelUrlPolicy urls;
    private String origin;
    private SystemModelResolvedRoute route;
    private final SystemModelProbeService.Command command =
            new SystemModelProbeService.Command(7, 3);

    @BeforeEach
    void prepare() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        origin = "http://127.0.0.1:" + server.getAddress().getPort();
        // Test-only DNS stub allows exercising the real HTTP client against the local server.
        urls =
                new SystemModelUrlPolicy(
                        host -> new InetAddress[] {InetAddress.getByName("8.8.8.8")});
        registry = mock(SystemModelRegistry.class);
        route =
                new SystemModelResolvedRoute(
                        "COURSE_QA",
                        "DATABASE",
                        SystemModelProtocol.OPENAI_CHAT,
                        "1",
                        1L,
                        3L,
                        origin,
                        "model",
                        Set.of("TEXT_CHAT", "JSON_OUTPUT"),
                        null,
                        null,
                        10000L,
                        1,
                        true,
                        "4268");
        when(registry.currentVersion()).thenReturn(7L);
        when(registry.probeRoute(7, 3)).thenReturn(route);
        when(registry.credential(7, route)).thenReturn("synthetic-probe-key-4268");
    }

    @AfterEach
    void cleanup() {
        server.stop(0);
    }

    @ParameterizedTest
    @ValueSource(strings = {"redirect", "large", "slow"})
    void realProbeTransportBoundsRedirectsBodyAndDeadline(String mode) {
        var followed = new AtomicInteger();
        server.createContext(
                "/target",
                exchange -> {
                    followed.incrementAndGet();
                    exchange.sendResponseHeaders(200, -1);
                    exchange.close();
                });
        server.createContext(
                "/chat/completions",
                exchange -> {
                    if (mode.equals("redirect")) {
                        exchange.getResponseHeaders().add("Location", "/target");
                        exchange.sendResponseHeaders(302, -1);
                        exchange.close();
                        return;
                    }
                    exchange.sendResponseHeaders(200, 0);
                    try (var output = exchange.getResponseBody()) {
                        if (mode.equals("large"))
                            output.write(
                                    new byte[SystemModelProbeService.RESPONSE_LIMIT_BYTES + 1]);
                        else {
                            output.write(1);
                            output.flush();
                            Thread.sleep(500);
                            output.write(2);
                        }
                    } catch (Exception ignored) {
                    }
                    exchange.close();
                });
        server.start();
        long started = System.nanoTime();
        try (var probes =
                new SystemModelProbeService(
                        registry,
                        urls,
                        new SystemModelHttpClient(SystemModelProbeService.RESPONSE_LIMIT_BYTES),
                        origin,
                        mode.equals("slow") ? Duration.ofMillis(150) : Duration.ofSeconds(3),
                        2)) {
            var result = probes.probe(command, 1);
            assertThat(result.category())
                    .isEqualTo(
                            switch (mode) {
                                case "redirect" -> "REDIRECT_FORBIDDEN";
                                case "large" -> "RESPONSE_TOO_LARGE";
                                default -> "TIMEOUT";
                            });
            assertThat(result.finalUrl()).isEqualTo(origin + "/chat/completions");
            assertThat(result.ok()).isFalse();
        }
        assertThat(followed.get()).isZero();
        assertThat(Duration.ofNanos(System.nanoTime() - started)).isLessThan(Duration.ofSeconds(4));
    }

    @Test
    void timeoutDoesNotReleaseConcurrencyUntilUninterruptibleWorkerActuallyExits()
            throws Exception {
        var http = mock(SystemModelHttpClient.class);
        var entered = new CountDownLatch(2);
        var release = new CountDownLatch(1);
        when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                .thenAnswer(
                        call -> {
                            entered.countDown();
                            while (release.getCount() != 0) {
                                try {
                                    release.await();
                                } catch (InterruptedException ignored) {
                                    /* Deliberately uninterruptible fake vendor. */
                                }
                            }
                            return new OpenAiCompatibleClientResponse(
                                    200, "{}", Map.of(), Duration.ZERO);
                        });
        try (var probes =
                        new SystemModelProbeService(
                                registry, urls, http, origin, Duration.ofMillis(300), 2);
                var callers = Executors.newFixedThreadPool(2)) {
            var first = callers.submit(() -> probes.probe(command, 1));
            var second = callers.submit(() -> probes.probe(command, 2));
            try {
                assertThat(entered.await(2, TimeUnit.SECONDS)).isTrue();
                assertThat(first.get(2, TimeUnit.SECONDS).category()).isEqualTo("TIMEOUT");
                assertThat(second.get(2, TimeUnit.SECONDS).category()).isEqualTo("TIMEOUT");
                assertThat(probes.probe(command, 3).category()).isEqualTo("BUSY");
                verify(http, times(2)).post(any(), anyMap(), anyString(), any(byte[].class), any());
            } finally {
                release.countDown();
            }
        }
    }

    @Test
    void whitelistCanonicalizesDefaultPortsAndRejectsPathsAndCredentials() {
        assertThat(SystemModelProbeService.origin(URI.create("https://EXAMPLE.COM:443/path")))
                .isEqualTo("https://example.com");
        for (String invalid :
                List.of(
                        "https://example.com/path",
                        "https://key@example.com",
                        "file:///tmp",
                        "https://example.com?key=private")) {
            assertThatThrownBy(
                            () ->
                                    new SystemModelProbeService(
                                            registry,
                                            urls,
                                            mock(SystemModelHttpClient.class),
                                            invalid,
                                            Duration.ofSeconds(1),
                                            2))
                    .isInstanceOf(com.example.courselingo.common.exception.BusinessException.class)
                    .hasNoCause();
        }
    }

    @Test
    void endpointInspectionPreservesLegacyV1AndExactNewPrefixes() {
        var legacy =
                new SystemModelResolvedRoute(
                        "COURSE_QA",
                        "ENV",
                        SystemModelProtocol.OPENAI_CHAT,
                        "env",
                        null,
                        null,
                        "https://example.com",
                        "model",
                        Set.of("JSON_OUTPUT"),
                        null,
                        null,
                        1000L,
                        1,
                        true,
                        "4268");
        assertThat(SystemModelEndpoints.finalUri(legacy).toString())
                .isEqualTo("https://example.com/v1/chat/completions");
        assertThat(SystemModelEndpoints.finalUri(route).toString())
                .isEqualTo(origin + "/chat/completions");
    }
}
