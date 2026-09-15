package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.evidence.CourseEvidence;
import com.example.courselingo.qa.service.DenseEvidenceClient;
import com.example.courselingo.qa.service.DenseRetrievalProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class DenseEvidenceClientTest {
    private final ObjectMapper json = new ObjectMapper();
    private HttpServer server;
    private DenseRetrievalProperties properties;
    private DenseEvidenceClient client;
    private Consumer<ObjectNode> mutate = ignored -> {};
    private int status = 200;
    private long delay;
    private final AtomicReference<ObjectNode> received = new AtomicReference<>();
    private final AtomicReference<String> signature = new AtomicReference<>();

    @BeforeEach
    void setup() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/v1/retrieve", exchange -> {
            try {
                var request = (ObjectNode) json.readTree(exchange.getRequestBody());
                received.set(request);
                signature.set(exchange.getRequestHeaders().getFirst("X-LectureLens-Signature"));
                ObjectNode response = request.deepCopy();
                response.put("index_version", "test-v1");
                response.put("snapshot_id", "snapshot");
                response.put("cache_hit", false);
                response.putArray("hits").addObject().put("evidence_id", "e1").put("score", 0.9);
                mutate.accept(response);
                if (delay > 0) Thread.sleep(delay);
                byte[] bytes = json.writeValueAsBytes(response);
                exchange.sendResponseHeaders(status, bytes.length);
                exchange.getResponseBody().write(bytes);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } finally {
                exchange.close();
            }
        });
        server.start();
        properties = new DenseRetrievalProperties();
        properties.setEnabled(true);
        properties.setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());
        properties.setServiceSecret("test-execution-context-key-at-least-32-bytes");
        client = new DenseEvidenceClient(properties, json);
    }

    @AfterEach
    void cleanup() { server.stop(0); client.close(); }

    static CourseEvidence evidence(String id, long revision) {
        return new CourseEvidence(id, "task-1", 42L, revision, "SUBTITLE", "source-1", List.of("source-1"),
            1000, 2000, "en", "A recipe needs a stopping condition", "A recipe needs a stopping condition", null,
            false, "evidence-v1", "hash", true, "source_text", null, false);
    }

    @Test
    void signsServerOwnedScopeAndUsesCanonicalSourceText() {
        var source = evidence("e1", 7);
        assertThat(client.retrieve("task-1", 42L, List.of(source), "如何终止执行？", 900L, 2100L, 4))
            .containsExactly(source);
        assertThat(received.get().path("owner_id").asLong()).isEqualTo(42);
        assertThat(received.get().path("revision").asLong()).isEqualTo(7);
        assertThat(received.get().path("time_window").path("start_ms").asLong()).isEqualTo(900);
        assertThat(signature.get()).matches("[0-9a-f]{64}");
    }

    @ParameterizedTest
    @ValueSource(strings = {"owner", "revision", "course", "request", "unknown", "duplicate", "score", "window"})
    void rejectsForgedOrStaleResponse(String fault) {
        mutate = response -> {
            switch (fault) {
                case "owner" -> response.put("owner_id", 99);
                case "revision" -> response.put("revision", 8);
                case "course" -> response.put("course_id", "another-course");
                case "request" -> response.put("request_id", "old-request");
                case "unknown" -> ((ObjectNode) response.path("hits").get(0)).put("evidence_id", "unseen");
                case "duplicate" -> response.withArray("hits").add(response.path("hits").get(0).deepCopy());
                case "score" -> ((ObjectNode) response.path("hits").get(0)).put("score", 999);
                default -> { }
            }
        };
        assertUnavailable(() -> client.retrieve("task-1", 42L, List.of(evidence("e1", 7)), "question",
            fault.equals("window") ? 5000L : null, fault.equals("window") ? 6000L : null, 8));
    }

    @Test
    void rejectsMixedOwnerInputBeforeSending() {
        assertUnavailable(() -> client.retrieve("task-1", 99L, List.of(evidence("e1", 7)), "question", null, null, 8));
        assertThat(received.get()).isNull();
    }

    @Test
    void serviceFailureIsExplicitAndDoesNotBecomeAnEmptySuccess() {
        status = 503;
        assertUnavailable(() -> client.retrieve("task-1", 42L, List.of(evidence("e1", 7)), "question", null, null, 8));
    }

    @Test
    void httpDeadlineIsBounded() {
        properties.setTimeout(Duration.ofMillis(50));
        delay = 250;
        assertUnavailable(() -> client.retrieve("task-1", 42L, List.of(evidence("e1", 7)), "question", null, null, 8));
    }

    @Test
    void emptyEvidenceDoesNotCallService() {
        assertThat(client.retrieve("task-1", 42L, List.of(), "question", null, null, 8)).isEmpty();
        assertThat(received.get()).isNull();
    }

    private static void assertUnavailable(org.assertj.core.api.ThrowableAssert.ThrowingCallable action) {
        assertThatThrownBy(action).isInstanceOfSatisfying(BusinessException.class,
            failure -> assertThat(failure.errorCode()).isEqualTo(ErrorCode.RETRIEVAL_UNAVAILABLE));
    }
}
