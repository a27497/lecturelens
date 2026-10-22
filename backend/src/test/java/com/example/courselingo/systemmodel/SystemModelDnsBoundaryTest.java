package com.example.courselingo.systemmodel;

import com.example.courselingo.common.exception.BusinessException;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import java.net.*;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import static org.assertj.core.api.Assertions.*;

class SystemModelDnsBoundaryTest {
    @Test void rebindingIsRejectedBeforeAnyPrivateServerReceivesCredentials() throws Exception {
        var requests = new AtomicInteger();
        var lookups = new AtomicInteger();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/chat/completions", exchange -> {
            requests.incrementAndGet(); exchange.sendResponseHeaders(200, -1); exchange.close();
        });
        server.start();
        var policy = new SystemModelUrlPolicy(host -> new InetAddress[] {
            InetAddress.getByName(lookups.incrementAndGet() == 1 ? "8.8.8.8" : "127.0.0.1")});
        try (var http = new SystemModelHttpClient(128, policy)) {
            assertThatThrownBy(() -> http.post(
                    URI.create("http://rebinding.invalid:" + server.getAddress().getPort() + "/chat/completions"),
                    Map.of("Authorization", "Bearer synthetic-rebinding-key"), "application/json",
                    "{}".getBytes(), Duration.ofSeconds(2)))
                    .isInstanceOf(BusinessException.class).hasNoCause();
            assertThat(lookups.get()).isEqualTo(2);
            assertThat(requests.get()).isZero();
        } finally { server.stop(0); }
    }

    @Test void checkedAddressesReachSocketWithoutAnIndependentSystemLookup() throws Exception {
        var host = new AtomicReference<String>();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/chat/completions", exchange -> {
            host.set(exchange.getRequestHeaders().getFirst("Host"));
            exchange.sendResponseHeaders(200, 2);
            exchange.getResponseBody().write("{}".getBytes()); exchange.close();
        });
        server.start();
        try (var http = SystemModelHttpTestSupport.loopbackClient(128)) {
            var response = http.post(URI.create("http://pinned.invalid:" + server.getAddress().getPort() + "/chat/completions"),
                    Map.of(), "application/json", "{}".getBytes(), Duration.ofSeconds(2));
            assertThat(response.statusCode()).isEqualTo(200);
            assertThat(host.get()).isEqualTo("pinned.invalid:" + server.getAddress().getPort());
        } finally { server.stop(0); }
    }

    @Test void literalAddressesCannotBypassDnsCallbackValidation() {
        try (var http = new SystemModelHttpClient(128)) {
            for (String host : new String[]{"127.0.0.1", "169.254.169.254", "[::1]"})
                assertThatThrownBy(() -> http.post(URI.create("http://" + host + "/chat/completions"),
                        Map.of(), "application/json", new byte[0], Duration.ofSeconds(1)))
                        .isInstanceOf(BusinessException.class).hasNoCause();
        }
    }
}
