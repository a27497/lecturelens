package com.example.courselingo.task.ratelimit;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.task.rate-limit.analysis")
public class AnalysisRateLimitProperties {

    private boolean enabled = true;
    private int maxRequests = 10;
    private long windowSeconds = 60;

    public AnalysisRateLimitProperties() {
    }

    public AnalysisRateLimitProperties(boolean enabled, int maxRequests, long windowSeconds) {
        this.enabled = enabled;
        setMaxRequests(maxRequests);
        setWindowSeconds(windowSeconds);
    }

    public boolean enabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int maxRequests() {
        return maxRequests;
    }

    public void setMaxRequests(int maxRequests) {
        if (maxRequests <= 0) {
            throw new IllegalArgumentException("analysis rate limit maxRequests must be greater than 0");
        }
        this.maxRequests = maxRequests;
    }

    public long windowSeconds() {
        return windowSeconds;
    }

    public void setWindowSeconds(long windowSeconds) {
        if (windowSeconds <= 0) {
            throw new IllegalArgumentException("analysis rate limit windowSeconds must be greater than 0");
        }
        this.windowSeconds = windowSeconds;
    }

    public Duration window() {
        return Duration.ofSeconds(windowSeconds);
    }
}
