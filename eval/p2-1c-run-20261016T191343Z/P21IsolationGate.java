package com.example.courselingo.systemmodel;

import java.net.URI;
import java.nio.file.Path;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;

/** Evaluation guard only: runs before the original capture gate and all bean/database initialization. */
public final class P21IsolationGate implements ApplicationListener<ApplicationEnvironmentPreparedEvent>, Ordered {
    public int getOrder() { return Ordered.LOWEST_PRECEDENCE - 1; }
    private static void require(boolean condition) { if (!condition) throw new IllegalStateException(); }
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        try {
            var e = event.getEnvironment();
            require("dev".equals(System.getProperty("user.name")));
            require("127.0.0.1".equals(e.getProperty("server.address")));
            require(e.getProperty("server.port", Integer.class, 0) == 18091);
            String jdbc = e.getProperty("spring.datasource.url", "");
            require(jdbc.startsWith("jdbc:mysql://"));
            var uri = URI.create(jdbc.substring(5));
            require(uri.getUserInfo() == null && "/lecturelens_p21_20261016".equals(uri.getPath()));
            require(!"root".equalsIgnoreCase(e.getProperty("spring.datasource.username", "root")));
            require(e.getProperty("courselingo.redis.database", Integer.class, -1) == 15);
            String topic = "lecturelens-p21-20261016T073754Z";
            require(topic.equals(e.getProperty("courselingo.mq.rocketmq.analysis-topic")));
            require((topic + "-producer").equals(e.getProperty("courselingo.mq.rocketmq.producer-group")));
            require((topic + "-consumer").equals(e.getProperty("courselingo.mq.rocketmq.consumer-group")));
            String prefix = "courselingo.pipeline.translation-v2.";
            require(e.getProperty(prefix + "enabled", Boolean.class, false));
            require(e.getProperty(prefix + "isolated-runtime", Boolean.class, false));
            require(e.getProperty(prefix + "checkpoint-enabled", Boolean.class, false));
            require(!e.getProperty(prefix + "asr.cache-enabled", Boolean.class, true));
            require(!e.getProperty(prefix + "streaming-translation", Boolean.class, true));
            require(!e.getProperty(prefix + "materials-parallel", Boolean.class, true));
            Path root = Path.of(System.getProperty("p21.private")).toRealPath();
            require(Path.of(System.getProperty("java.io.tmpdir")).toRealPath().equals(root.resolve("tmp")));
            require(Path.of(e.getProperty("courselingo.task.runner.workspace-dir", "")).toRealPath().equals(root.resolve("workspace")));
            require(!e.getProperty("courselingo.retrieval.enabled", Boolean.class, true));
            require(!e.getProperty("courselingo.study.enabled", Boolean.class, true));
            require(e.getProperty("spring.flyway.enabled", Boolean.class, false));
            require(e.getProperty("courselingo.ai.system-models.enabled", Boolean.class, false));
            // Shared raw media is read-only; derived object keys remain scoped to new task IDs.
            require(e.getProperty("courselingo.storage.minio.bucket", "").equals(System.getenv("STORAGE_MINIO_BUCKET")));
            require(e.getProperty("courselingo.storage.minio.endpoint", "").equals(System.getenv("STORAGE_MINIO_ENDPOINT")));
            var expected = new com.fasterxml.jackson.databind.ObjectMapper().readTree(
                Path.of(System.getProperty("p21.options")).toFile()).path("properties");
            var fields = expected.fields();
            while (fields.hasNext()) {
                var field = fields.next();
                require(field.getValue().asText().equals(e.getProperty(field.getKey())));
            }
            System.out.println("P21_FINAL_ISOLATION_GATE_PASS");
        } catch (Exception ignored) {
            System.err.println("P21_FINAL_ISOLATION_GATE_FAILED");
            System.exit(44);
        }
    }
}
