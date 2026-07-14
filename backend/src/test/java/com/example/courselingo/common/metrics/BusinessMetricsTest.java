package com.example.courselingo.common.metrics;

import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Tag;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class BusinessMetricsTest {

    private SimpleMeterRegistry registry;
    private BusinessMetrics metrics;

    @BeforeEach
    void setUp() {
        registry = new SimpleMeterRegistry();
        metrics = new BusinessMetrics(registry);
    }

    @Test
    void recordsTaskMqRunnerUploadAndArtifactMetrics() {
        metrics.incrementTaskCreated("success");
        metrics.incrementTaskStateTransition("CREATED", "QUEUED", "success");
        metrics.incrementTaskRunner("run", "success");
        metrics.recordTaskRunnerDuration("run", "success", Duration.ofMillis(25));
        metrics.incrementMqProduced("courselingo-analysis-task", "ANALYSIS_CREATED", "success");
        metrics.incrementMqConsumed("courselingo-analysis-task", "ANALYSIS_CREATED", "success");
        metrics.incrementUploadSessionCreated("success");
        metrics.incrementUploadChunkReceived("success");
        metrics.incrementUploadCompleted("success");
        metrics.incrementArtifactSaved("JSON", "success");
        metrics.recordArtifactBytes("JSON", 128);

        assertCounter(BusinessMetricNames.TASK_CREATED_TOTAL, 1.0, "outcome", "success");
        assertCounter(BusinessMetricNames.TASK_STATE_TRANSITION_TOTAL, 1.0,
            "from", "created", "to", "queued", "outcome", "success");
        assertCounter(BusinessMetricNames.TASK_RUNNER_TOTAL, 1.0, "stage", "run", "outcome", "success");
        Timer timer = registry.find(BusinessMetricNames.TASK_RUNNER_DURATION)
            .tags("stage", "run", "outcome", "success")
            .timer();
        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(1);
        assertCounter(BusinessMetricNames.MQ_PRODUCE_TOTAL, 1.0,
            "topic", "courselingo-analysis-task", "tag", "analysis_created", "outcome", "success");
        assertCounter(BusinessMetricNames.MQ_CONSUME_TOTAL, 1.0,
            "topic", "courselingo-analysis-task", "tag", "analysis_created", "outcome", "success");
        assertCounter(BusinessMetricNames.UPLOAD_SESSION_CREATED_TOTAL, 1.0, "outcome", "success");
        assertCounter(BusinessMetricNames.UPLOAD_CHUNK_RECEIVED_TOTAL, 1.0, "outcome", "success");
        assertCounter(BusinessMetricNames.UPLOAD_COMPLETED_TOTAL, 1.0, "outcome", "success");
        assertCounter(BusinessMetricNames.ARTIFACT_SAVED_TOTAL, 1.0, "type", "json", "outcome", "success");

        DistributionSummary summary = registry.find(BusinessMetricNames.ARTIFACT_BYTES)
            .tags("type", "json")
            .summary();
        assertThat(summary).isNotNull();
        assertThat(summary.count()).isEqualTo(1);
        assertThat(summary.totalAmount()).isEqualTo(128);
    }

    @Test
    void normalizesBlankLongAndSensitiveTagValues() {
        metrics.incrementTaskCreated(null);
        metrics.incrementTaskStateTransition("task_123", "C:\\Users\\demo\\video.mp4", "success");
        metrics.incrementMqProduced("topic-with-secret-token", "Authorization", "success");
        metrics.incrementArtifactSaved("x".repeat(100), "success");
        metrics.recordTaskRunnerDuration("run", "success", Duration.ofMillis(-1));

        assertCounter(BusinessMetricNames.TASK_CREATED_TOTAL, 1.0, "outcome", "unknown");
        assertCounter(BusinessMetricNames.TASK_STATE_TRANSITION_TOTAL, 1.0,
            "from", "other", "to", "other", "outcome", "success");
        assertCounter(BusinessMetricNames.MQ_PRODUCE_TOTAL, 1.0,
            "topic", "other", "tag", "other", "outcome", "success");
        assertCounter(BusinessMetricNames.ARTIFACT_SAVED_TOTAL, 1.0, "type", "other", "outcome", "success");

        List<String> tagValues = registry.getMeters().stream()
            .flatMap(meter -> meter.getId().getTags().stream())
            .map(Tag::getValue)
            .toList();
        assertThat(tagValues).doesNotContain(
            "task_123",
            "C:\\Users\\demo\\video.mp4",
            "topic-with-secret-token",
            "Authorization",
            "x".repeat(100)
        );
    }

    private void assertCounter(String name, double expected, String... tags) {
        assertThat(registry.find(name).tags(tags).counter())
            .as(name)
            .isNotNull();
        assertThat(registry.find(name).tags(tags).counter().count()).isEqualTo(expected);
    }
}
