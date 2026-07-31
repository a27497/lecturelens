package com.example.courselingo.learning.service;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.learning-package")
public class LearningPackageProperties {

    public static final Duration DEFAULT_LLM_TIMEOUT = Duration.ofSeconds(180);

    private Duration llmTimeout = DEFAULT_LLM_TIMEOUT;
    private int shortCourseMinutes = 10;
    private int longCourseMinutes = 30;
    private int shortSummaryMin = 60;
    private int shortSummaryMax = 300;
    private int mediumSummaryMin = 120;
    private int mediumSummaryMax = 500;
    private int longSummaryMin = 220;
    private int longSummaryMax = 800;

    public LearningPackageProperties() {
    }

    public LearningPackageProperties(Duration llmTimeout) {
        setLlmTimeout(llmTimeout);
    }

    public Duration llmTimeout() {
        return llmTimeout;
    }

    public void setLlmTimeout(Duration llmTimeout) {
        Duration normalized = llmTimeout == null ? DEFAULT_LLM_TIMEOUT : llmTimeout;
        if (normalized.isZero() || normalized.isNegative()) {
            throw new IllegalArgumentException("llmTimeout must be positive");
        }
        this.llmTimeout = normalized;
    }

    public int shortCourseMinutes() { return shortCourseMinutes; }
    public void setShortCourseMinutes(int value) { shortCourseMinutes = Math.max(1, Math.min(value, 29)); }
    public int longCourseMinutes() { return longCourseMinutes; }
    public void setLongCourseMinutes(int value) { longCourseMinutes = Math.max(shortCourseMinutes + 1, Math.min(value, 180)); }
    public int shortSummaryMin() { return shortSummaryMin; }
    public void setShortSummaryMin(int value) { shortSummaryMin = bounded(value, 20, 300); }
    public int shortSummaryMax() { return shortSummaryMax; }
    public void setShortSummaryMax(int value) { shortSummaryMax = bounded(value, shortSummaryMin, 800); }
    public int mediumSummaryMin() { return mediumSummaryMin; }
    public void setMediumSummaryMin(int value) { mediumSummaryMin = bounded(value, 40, 500); }
    public int mediumSummaryMax() { return mediumSummaryMax; }
    public void setMediumSummaryMax(int value) { mediumSummaryMax = bounded(value, mediumSummaryMin, 1000); }
    public int longSummaryMin() { return longSummaryMin; }
    public void setLongSummaryMin(int value) { longSummaryMin = bounded(value, 80, 800); }
    public int longSummaryMax() { return longSummaryMax; }
    public void setLongSummaryMax(int value) { longSummaryMax = bounded(value, longSummaryMin, 1200); }

    private static int bounded(int value, int minimum, int maximum) {
        return Math.max(minimum, Math.min(value, maximum));
    }
}
