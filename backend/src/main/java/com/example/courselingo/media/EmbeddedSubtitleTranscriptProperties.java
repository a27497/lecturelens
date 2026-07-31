package com.example.courselingo.media;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.ai.asr.transcript")
public class EmbeddedSubtitleTranscriptProperties {

    private String strategy = "EMBEDDED_SUBTITLE_FIRST";
    private double minimumCoverage = 0.80d;
    private int minimumCues = 2;
    private int maximumCues = 10000;
    private Duration segmentDuration = Duration.ofSeconds(60);

    public boolean embeddedSubtitleFirst() {
        return "EMBEDDED_SUBTITLE_FIRST".equalsIgnoreCase(strategy);
    }

    public String getStrategy() {
        return strategy;
    }

    public void setStrategy(String strategy) {
        this.strategy = strategy == null ? "EMBEDDED_SUBTITLE_FIRST" : strategy.strip();
    }

    public double getMinimumCoverage() {
        return minimumCoverage;
    }

    public void setMinimumCoverage(double minimumCoverage) {
        this.minimumCoverage = Math.max(0.1d, Math.min(1.0d, minimumCoverage));
    }

    public int getMinimumCues() {
        return minimumCues;
    }

    public void setMinimumCues(int minimumCues) {
        this.minimumCues = Math.max(1, Math.min(100, minimumCues));
    }

    public int getMaximumCues() {
        return maximumCues;
    }

    public void setMaximumCues(int maximumCues) {
        this.maximumCues = Math.max(100, Math.min(20000, maximumCues));
    }

    public Duration getSegmentDuration() {
        return segmentDuration;
    }

    public void setSegmentDuration(Duration segmentDuration) {
        if (segmentDuration == null || segmentDuration.isNegative() || segmentDuration.isZero()) {
            this.segmentDuration = Duration.ofSeconds(60);
            return;
        }
        long seconds = Math.max(5L, Math.min(300L, segmentDuration.toSeconds()));
        this.segmentDuration = Duration.ofSeconds(seconds);
    }
}
