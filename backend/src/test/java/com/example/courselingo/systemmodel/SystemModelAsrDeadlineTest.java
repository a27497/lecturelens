package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.*;

import com.example.courselingo.ai.asr.*;
import com.sun.net.httpserver.HttpServer;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SystemModelAsrDeadlineTest {
    @Test
    void expiredAdapterPreflightMustNotSend(@TempDir Path directory) throws Exception {
        var requests = new AtomicInteger();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            requests.incrementAndGet();
            exchange.sendResponseHeaders(200, 2);
            exchange.getResponseBody().write("{}".getBytes());
            exchange.close();
        });
        server.start();
        var checks = new AtomicInteger();
        var urls = new SystemModelUrlPolicy() {
            @Override public void checkDestination(URI uri) {
                if (checks.incrementAndGet() == 1)
                    java.util.concurrent.locks.LockSupport.parkNanos(Duration.ofMillis(1200).toNanos());
            }
            @Override InetAddress[] publicAddresses(String host) {
                return new InetAddress[]{InetAddress.getLoopbackAddress()};
            }
        };
        Path audio = directory.resolve("synthetic.wav");
        Files.write(audio, new byte[]{1, 2, 3, 4});
        var options = AsrConfigurationSnapshot.capture(
                new BailianAsrProperties(), new SiliconFlowAsrProperties(), new MockAsrProperties());
        var route = new SystemModelResolvedRoute(
                "ASR_TRANSCRIPTION", "DATABASE", SystemModelProtocol.SILICONFLOW_ASR,
                "1", 1L, 1L, "http://deadline.invalid:" + server.getAddress().getPort(),
                "synthetic", Set.of("ASR"), 0d, 32, 1000L, 1, true, "test", options);
        try (var http = new SystemModelHttpClient(1024, urls)) {
            var adapter = AsrAdapterFactories.siliconFlow(http, urls).create(route, "synthetic-key");
            assertThatThrownBy(() -> adapter.transcribe(new SpeechToTextRequest(
                    audio, "en", "request", "task", Duration.ofSeconds(1))))
                    .isInstanceOfSatisfying(AsrCallFailure.class,
                            failure -> assertThat(failure.category()).isEqualTo(AsrCallFailure.Category.TIMEOUT));
            assertThat(requests.get()).as("expired preflight must prevent a billable request").isZero();
        } finally {
            server.stop(0);
        }
    }
}
