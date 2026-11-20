package com.example.courselingo.study;

import com.example.courselingo.evidence.CourseEvidence;
import com.example.courselingo.evidence.CourseEvidenceService;
import com.example.courselingo.evidence.EvidenceIndexSynchronizer;
import com.example.courselingo.evidence.retrieval.DenseEvidenceClient;
import com.example.courselingo.evidence.retrieval.DenseRetrievalProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.mock.web.MockHttpServletRequest;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/** Loopback-only dev fixture. The signed controller, authority and dense client run unchanged. */
public final class TutorDevEvidenceServer {
    private static final String EVIDENCE_PATH = "/internal/v1/study/evidence";
    private record Snapshot(String task_id, Long owner_id, long revision, List<CourseEvidence> items) {}

    private TutorDevEvidenceServer() {}

    public static void main(String[] args) throws Exception {
        var json = new ObjectMapper().findAndRegisterModules();
        var snapshots = json.readValue(Path.of(args[0]).toFile(), Snapshot[].class);
        var jdbc = new JdbcTemplate(new DriverManagerDataSource("jdbc:h2:mem:tutor-dev;DB_CLOSE_DELAY=-1", "sa", ""));
        jdbc.execute("CREATE TABLE analysis_task(id VARCHAR(128),user_id BIGINT,content_revision BIGINT,"
            + "status VARCHAR(32),deleted_at TIMESTAMP,learning_ready_at TIMESTAMP,PRIMARY KEY(id,user_id))");
        var evidence = mock(CourseEvidenceService.class);
        var indexes = mock(EvidenceIndexSynchronizer.class);
        for (var snapshot : snapshots) {
            var id = snapshot.task_id();
            var owner = snapshot.owner_id();
            jdbc.update("INSERT INTO analysis_task VALUES (?,?,?,'SUCCEEDED',NULL,NULL)", id, owner, snapshot.revision());
            when(evidence.current(id, owner)).thenReturn(snapshot.items());
            when(indexes.status(id, owner)).thenReturn(new EvidenceIndexSynchronizer.IndexStatus(
                "READY", snapshot.revision(), snapshot.revision(), "offline-dev", 0, null, null));
        }

        var properties = new DenseRetrievalProperties();
        properties.setBaseUrl("http://127.0.0.1:" + Integer.parseInt(args[2]));
        properties.setServiceSecret(System.getenv("TUTOR_DEV_SIGNING_KEY"));
        var study = new StudyProperties();
        study.setEnabled(true);
        try (var dense = new DenseEvidenceClient(properties, json); var transport = new StudyTransport(properties, json)) {
            var authority = new StudyEvidenceAuthority(jdbc, evidence, indexes, dense);
            var controller = new StudyController(null, study, authority, transport, json);
            var server = HttpServer.create(new InetSocketAddress("127.0.0.1", Integer.parseInt(args[1])), 0);
            server.createContext(EVIDENCE_PATH, exchange -> {
                try (exchange) {
                    if (!"POST".equals(exchange.getRequestMethod()) || !EVIDENCE_PATH.equals(exchange.getRequestURI().getPath())) {
                        exchange.sendResponseHeaders(404, -1);
                        return;
                    }
                    var request = new MockHttpServletRequest();
                    request.setContent(exchange.getRequestBody().readNBytes(65537));
                    for (String header : List.of("X-LectureLens-Timestamp", "X-LectureLens-Signature")) {
                        var value = exchange.getRequestHeaders().getFirst(header);
                        if (value != null) request.addHeader(header, value);
                    }
                    byte[] response;
                    try {
                        response = json.writeValueAsBytes(controller.evidence(request));
                    } catch (Exception failure) {
                        exchange.sendResponseHeaders(409, -1);
                        return;
                    }
                    exchange.getResponseHeaders().set("Content-Type", "application/json");
                    exchange.sendResponseHeaders(200, response.length);
                    exchange.getResponseBody().write(response);
                }
            });
            server.start();
            try {
                new CountDownLatch(1).await();
            } finally {
                server.stop(0);
            }
        }
    }
}
