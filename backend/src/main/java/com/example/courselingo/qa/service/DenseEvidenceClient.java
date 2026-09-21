package com.example.courselingo.qa.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.evidence.CourseEvidence;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class DenseEvidenceClient implements AutoCloseable {
    private static final Logger log = LoggerFactory.getLogger(DenseEvidenceClient.class);
    private static final String PATH = "/internal/v1/retrieve";
    private final DenseRetrievalProperties properties;
    private final ObjectMapper json;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();

    public DenseEvidenceClient(DenseRetrievalProperties properties, ObjectMapper json) {
        this.properties = properties;
        this.json = json;
    }

    public boolean enabled() { return properties.isEnabled(); }

    @jakarta.annotation.PreDestroy
    @Override
    public void close() { http.close(); }

    public com.fasterxml.jackson.databind.JsonNode sync(String taskId, Long ownerId, long revision,
            long sequence, List<CourseEvidence> evidence, boolean deleted) throws Exception {
        Map<String, Object> payload = new LinkedHashMap<>();
        String requestId = UUID.randomUUID().toString();
        payload.put("request_id", requestId);
        payload.put("owner_id", ownerId);
        payload.put("course_id", taskId);
        payload.put("revision", revision);
        payload.put("sequence", sequence);
        payload.put("operation", deleted ? "DELETE" : "PLAN");
        List<Map<String, Object>> manifest = new ArrayList<>();
        for (var item : evidence) manifest.add(Map.of("evidence_id", item.evidenceId(), "content_hash",
            HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(item.normalizedText().getBytes(StandardCharsets.UTF_8))),
            "start_ms", item.startMs(), "end_ms", item.endMs()));
        payload.put("manifest", manifest);
        var plan = post("/internal/v1/evidence/sync", payload);
        validateSync(plan, requestId, taskId, ownerId, revision, sequence);
        if (deleted) {
            if (!"DELETED".equals(plan.path("state").asText())) throw new IllegalStateException("Delete not acknowledged");
            return plan;
        }
        if ("READY".equals(plan.path("state").asText())) return plan;
        if (!"PENDING".equals(plan.path("state").asText()) || !plan.path("missing_ids").isArray()) {
            throw new IllegalStateException("Invalid sync plan");
        }
        var missing = new HashSet<String>();
        plan.path("missing_ids").forEach(id -> missing.add(id.asText()));
        var allowed = evidence.stream().map(CourseEvidence::evidenceId).collect(Collectors.toSet());
        if (!allowed.containsAll(missing)) throw new IllegalStateException("Invalid sync scope");
        payload.put("operation", "APPLY");
        payload.put("index_version", plan.path("index_version").asText());
        payload.put("upserts", evidence.stream().filter(e -> missing.contains(e.evidenceId())).map(e -> Map.of(
            "evidence_id", e.evidenceId(), "text", e.normalizedText(),
            "start_ms", e.startMs(), "end_ms", e.endMs())).toList());
        var result = post("/internal/v1/evidence/sync", payload);
        validateSync(result, requestId, taskId, ownerId, revision, sequence);
        if (!"READY".equals(result.path("state").asText())
                || !plan.path("index_version").equals(result.path("index_version"))) {
            throw new IllegalStateException("Index not published");
        }
        return result;
    }

    private void validateSync(com.fasterxml.jackson.databind.JsonNode result, String requestId, String taskId,
                              Long ownerId, long revision, long sequence) {
        if (!requestId.equals(result.path("request_id").asText()) || !taskId.equals(result.path("course_id").asText())
                || !result.path("owner_id").isIntegralNumber() || result.path("owner_id").asLong() != ownerId
                || !result.path("revision").isIntegralNumber() || result.path("revision").asLong() != revision
                || !result.path("sequence").isIntegralNumber() || result.path("sequence").asLong() != sequence
                || result.path("index_version").asText().isBlank()) throw new IllegalStateException("Sync response mismatch");
    }

    private com.fasterxml.jackson.databind.JsonNode post(String path, Map<String, Object> payload) throws Exception {
        if (properties.getServiceSecret().getBytes(StandardCharsets.UTF_8).length < 32) {
            throw new IllegalStateException("Missing retrieval execution-context key");
        }
        byte[] body = json.writeValueAsBytes(payload);
        if (body.length > 4 * 1024 * 1024) throw new IllegalStateException("Request too large");
        String timestamp = Long.toString(Instant.now().getEpochSecond());
        String digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(body));
        String message = "lecturelens-retrieval-v1\nPOST\n" + path + "\n" + timestamp + "\n" + digest;
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(properties.getServiceSecret().getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        String signature = HexFormat.of().formatHex(mac.doFinal(message.getBytes(StandardCharsets.UTF_8)));
        var request = HttpRequest.newBuilder(URI.create(properties.getBaseUrl().replaceAll("/+$", "") + path))
            .timeout(properties.getTimeout()).header("Content-Type", "application/json")
            .header("X-LectureLens-Timestamp", timestamp).header("X-LectureLens-Signature", signature)
            .POST(HttpRequest.BodyPublishers.ofByteArray(body)).build();
        var response = http.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        if (response.statusCode() != 200) throw new IllegalStateException("Evidence service rejected request: " + response.statusCode());
        return json.readTree(response.body());
    }

    public List<CourseEvidence> retrieve(String taskId, Long ownerId, List<CourseEvidence> evidence,
                                        String question, Long startMs, Long endMs, int topK) {
        if (evidence.isEmpty()) return List.of();
        String requestId = UUID.randomUUID().toString();
        long started = System.nanoTime();
        try {
            if (properties.getServiceSecret().getBytes(StandardCharsets.UTF_8).length < 32) {
                throw new IllegalStateException("Missing retrieval execution-context key");
            }
            if (evidence.size() > 2000) throw new IllegalStateException("Snapshot exceeds L1 limit");
            long revision = evidence.getFirst().revision();
            if (evidence.stream().anyMatch(e -> e.revision() != revision || !taskId.equals(e.courseId())
                    || !ownerId.equals(e.ownerId()) || !e.retrievable())) {
                throw new IllegalStateException("Mixed evidence authority");
            }
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("request_id", requestId);
            payload.put("owner_id", ownerId);
            payload.put("course_id", taskId);
            payload.put("revision", revision);
            payload.put("query", question);
            payload.put("top_k", topK);
            payload.put("allowed_evidence_ids", evidence.stream().map(CourseEvidence::evidenceId).toList());
            if (startMs != null && endMs != null) payload.put("time_window", Map.of("start_ms", startMs, "end_ms", endMs));
            var result = post(PATH, payload);
            if (!requestId.equals(result.path("request_id").asText())
                    || !taskId.equals(result.path("course_id").asText())
                    || !result.path("owner_id").isIntegralNumber() || result.path("owner_id").asLong() != ownerId
                    || !result.path("revision").isIntegralNumber() || result.path("revision").asLong() != revision
                    || result.path("index_version").asText().isBlank() || !result.path("hits").isArray()
                    || result.path("hits").size() > topK) {
                throw new IllegalStateException("Retrieval response contract mismatch");
            }
            Map<String, CourseEvidence> allowed = evidence.stream().collect(Collectors.toMap(CourseEvidence::evidenceId, Function.identity()));
            List<CourseEvidence> selected = new ArrayList<>();
            var seen = new HashSet<String>();
            for (var hit : result.path("hits")) {
                String id = hit.path("evidence_id").asText();
                CourseEvidence item = allowed.get(id);
                double score = hit.path("score").asDouble(Double.NaN);
                if (item == null || !seen.add(id) || !Double.isFinite(score) || score < -1.000001 || score > 1.000001
                        || (startMs != null && endMs != null && (item.startMs() > endMs || item.endMs() < startMs))) {
                    throw new IllegalStateException("Retrieval returned evidence outside request scope");
                }
                selected.add(item); // Source text and citation times always come from Java's canonical snapshot.
            }
            log.info("Dense retrieval: requestId={}, cacheHit={}, hits={}, elapsedMs={}", requestId,
                result.path("cache_hit").asBoolean(), selected.size(), (System.nanoTime() - started) / 1_000_000);
            return List.copyOf(selected);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new BusinessException(ErrorCode.RETRIEVAL_UNAVAILABLE);
        } catch (Exception failure) {
            log.warn("Dense retrieval failed: requestId={}, type={}", requestId, failure.getClass().getSimpleName());
            throw new BusinessException(ErrorCode.RETRIEVAL_UNAVAILABLE);
        }
    }
}
