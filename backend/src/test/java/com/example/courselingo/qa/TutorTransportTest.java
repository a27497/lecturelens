package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.*;

import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.qa.service.DenseRetrievalProperties;
import com.example.courselingo.study.StudyTransport;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class TutorTransportTest {
    @Test void tutorUsesBoundPathSignatureChecksResponseScopeAndRedactsRemoteErrors() throws Exception {
        var json = new ObjectMapper();
        var config = new DenseRetrievalProperties();
        config.setBaseUrl("http://127.0.0.1:25732");
        config.setServiceSecret("offline-test-service-secret-32-bytes");
        var reply = new AtomicReference<>("{\"owner_id\":42,\"course_id\":\"course\",\"revision\":7}");
        var status = new java.util.concurrent.atomic.AtomicInteger(200);
        var path = new AtomicReference<String>();
        try (var transport = new StudyTransport(config,json)) {
            var server = HttpServer.create(new InetSocketAddress("127.0.0.1",25732),0);
            server.createContext("/internal/v1/tutor/command", exchange -> {
                try {
                    byte[] body = exchange.getRequestBody().readAllBytes();
                    String timestamp = exchange.getRequestHeaders().getFirst("X-LectureLens-Timestamp");
                    assertThat(exchange.getRequestHeaders().getFirst("X-LectureLens-Signature"))
                        .isEqualTo(transport.signature(exchange.getRequestURI().getPath(),timestamp,body));
                    path.set(exchange.getRequestURI().getPath());
                    byte[] result = reply.get().getBytes(StandardCharsets.UTF_8);
                    exchange.sendResponseHeaders(status.get(),result.length);
                    exchange.getResponseBody().write(result);
                } catch (Exception error) { throw new RuntimeException(error); }
                finally { exchange.close(); }
            });
            server.start();
            try {
                Map<String,Object> payload = Map.of("owner_id",42L,"course_id","course","revision",7L,"operation","LIST");
                assertThat(transport.tutor(payload).path("revision").asLong()).isEqualTo(7L);
                assertThat(path.get()).isEqualTo("/internal/v1/tutor/command");
                reply.set("{\"owner_id\":99,\"course_id\":\"course\",\"revision\":7}");
                assertThatThrownBy(() -> transport.tutor(payload)).isInstanceOf(BusinessException.class);
                status.set(409); reply.set("{\"detail\":\"TUTOR_SESSION_STALE\"}");
                assertThatThrownBy(() -> transport.tutor(payload)).hasMessage("TUTOR_SESSION_STALE");
                status.set(500); reply.set("Bearer sk-fake-private-never-reflected");
                assertThatThrownBy(() -> transport.tutor(payload)).isInstanceOf(BusinessException.class)
                    .hasMessageNotContaining("sk-fake");
            } finally { server.stop(0); }
        }
    }
}
