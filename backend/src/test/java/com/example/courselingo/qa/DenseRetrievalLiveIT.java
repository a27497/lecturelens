package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.evidence.CourseEvidence;
import com.example.courselingo.qa.service.DenseEvidenceClient;
import com.example.courselingo.qa.service.DenseRetrievalProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/** Opt-in: requires the real Python service + local embedding model + pgvector. No paid API. */
class DenseRetrievalLiveIT {
    @Test
    void javaSignedContextToPythonEmbeddingToPgvectorToCanonicalCitation() throws Exception {
        String secret = System.getenv("AGENT_SERVICE_SECRET");
        assertThat(secret).as("Set AGENT_SERVICE_SECRET and start the Python service before this opt-in IT")
            .isNotBlank();
        var properties = new DenseRetrievalProperties();
        properties.setEnabled(true);
        properties.setServiceSecret(secret);
        properties.setBaseUrl(System.getProperty("agent.live.url", "http://127.0.0.1:8090"));
        try (var client = new DenseEvidenceClient(properties, new ObjectMapper())) {
            String task = "live-" + UUID.randomUUID();
            var recipe = item(task, "recipe", "An algorithm needs a stopping condition so a recipe does not keep baking bread forever.", 1000);
            var unrelated = item(task, "biology", "DNA stores genetic information in cells. Proteins are made of amino acids.", 10000);
            List<CourseEvidence> candidates = List.of(recipe, unrelated);
            assertThat(client.sync(task, 42L, 1, 1, candidates, false).path("state").asText()).isEqualTo("READY");
            var result = client.retrieve(task, 42L, candidates, "程序怎样避免一直运行下去？", null, null, 1);
            assertThat(result).containsExactly(recipe);
            assertThat(client.retrieve(task, 42L, candidates, "程序怎样避免一直运行下去？", null, null, 1))
                .containsExactly(recipe); // warm cache, same citation
            assertThat(client.retrieve(task, 42L, candidates, "遗传信息", 9000L, 12000L, 1))
                .containsExactly(unrelated);
            assertThat(client.retrieve(task, 42L, candidates, "程序停止", 20000L, 21000L, 1)).isEmpty();
            assertThat(client.sync(task, 42L, 1, 2, List.of(), true).path("state").asText()).isEqualTo("DELETED");
            System.out.println("PASS Java HMAC -> FastAPI -> real multilingual embedding -> pgvector -> canonical citation");
        }
    }

    private static CourseEvidence item(String task, String id, String text, long start) {
        return new CourseEvidence(id, task, 42L, 1, "SUBTITLE", id, List.of(id), start, start + 1000,
            "en", text, text, null, false, "evidence-v1", id, true, "source_text", null, false);
    }
}
