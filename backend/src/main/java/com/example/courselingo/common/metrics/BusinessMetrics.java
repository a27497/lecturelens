package com.example.courselingo.common.metrics;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.composite.CompositeMeterRegistry;
import java.time.Duration;
import org.springframework.stereotype.Component;

@Component
public class BusinessMetrics {

    private final MeterRegistry meterRegistry;

    public BusinessMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry == null ? new CompositeMeterRegistry() : meterRegistry;
    }

    public static BusinessMetrics noop() {
        return new BusinessMetrics(new CompositeMeterRegistry());
    }

    public void incrementTaskCreated(String outcome) {
        counter(BusinessMetricNames.TASK_CREATED_TOTAL, BusinessMetricTags.OUTCOME, outcome).increment();
    }

    public void incrementTaskStateTransition(String from, String to, String outcome) {
        Counter.builder(BusinessMetricNames.TASK_STATE_TRANSITION_TOTAL)
            .tag(BusinessMetricTags.FROM, BusinessMetricTags.normalize(from))
            .tag(BusinessMetricTags.TO, BusinessMetricTags.normalize(to))
            .tag(BusinessMetricTags.OUTCOME, BusinessMetricTags.normalize(outcome))
            .register(meterRegistry)
            .increment();
    }

    public void incrementTaskRunner(String stage, String outcome) {
        Counter.builder(BusinessMetricNames.TASK_RUNNER_TOTAL)
            .tag(BusinessMetricTags.STAGE, BusinessMetricTags.normalize(stage))
            .tag(BusinessMetricTags.OUTCOME, BusinessMetricTags.normalize(outcome))
            .register(meterRegistry)
            .increment();
    }

    public void recordTaskRunnerDuration(String stage, String outcome, Duration duration) {
        Timer.builder(BusinessMetricNames.TASK_RUNNER_DURATION)
            .tag(BusinessMetricTags.STAGE, BusinessMetricTags.normalize(stage))
            .tag(BusinessMetricTags.OUTCOME, BusinessMetricTags.normalize(outcome))
            .register(meterRegistry)
            .record(nonNegativeDuration(duration));
    }

    public void incrementMqProduced(String topic, String tag, String outcome) {
        Counter.builder(BusinessMetricNames.MQ_PRODUCE_TOTAL)
            .tag(BusinessMetricTags.TOPIC, BusinessMetricTags.normalize(topic))
            .tag(BusinessMetricTags.TAG, BusinessMetricTags.normalize(tag))
            .tag(BusinessMetricTags.OUTCOME, BusinessMetricTags.normalize(outcome))
            .register(meterRegistry)
            .increment();
    }

    public void incrementMqConsumed(String topic, String tag, String outcome) {
        Counter.builder(BusinessMetricNames.MQ_CONSUME_TOTAL)
            .tag(BusinessMetricTags.TOPIC, BusinessMetricTags.normalize(topic))
            .tag(BusinessMetricTags.TAG, BusinessMetricTags.normalize(tag))
            .tag(BusinessMetricTags.OUTCOME, BusinessMetricTags.normalize(outcome))
            .register(meterRegistry)
            .increment();
    }

    public void incrementUploadSessionCreated(String outcome) {
        counter(BusinessMetricNames.UPLOAD_SESSION_CREATED_TOTAL, BusinessMetricTags.OUTCOME, outcome).increment();
    }

    public void incrementUploadChunkReceived(String outcome) {
        counter(BusinessMetricNames.UPLOAD_CHUNK_RECEIVED_TOTAL, BusinessMetricTags.OUTCOME, outcome).increment();
    }

    public void incrementUploadCompleted(String outcome) {
        counter(BusinessMetricNames.UPLOAD_COMPLETED_TOTAL, BusinessMetricTags.OUTCOME, outcome).increment();
    }

    public void incrementArtifactSaved(String artifactType, String outcome) {
        Counter.builder(BusinessMetricNames.ARTIFACT_SAVED_TOTAL)
            .tag(BusinessMetricTags.TYPE, BusinessMetricTags.normalize(artifactType))
            .tag(BusinessMetricTags.OUTCOME, BusinessMetricTags.normalize(outcome))
            .register(meterRegistry)
            .increment();
    }

    public void recordArtifactBytes(String artifactType, long sizeBytes) {
        DistributionSummary.builder(BusinessMetricNames.ARTIFACT_BYTES)
            .tag(BusinessMetricTags.TYPE, BusinessMetricTags.normalize(artifactType))
            .register(meterRegistry)
            .record(Math.max(0L, sizeBytes));
    }

    private Counter counter(String name, String tagName, String tagValue) {
        return Counter.builder(name)
            .tag(tagName, BusinessMetricTags.normalize(tagValue))
            .register(meterRegistry);
    }

    private static Duration nonNegativeDuration(Duration duration) {
        if (duration == null || duration.isNegative()) {
            return Duration.ZERO;
        }
        return duration;
    }
}
