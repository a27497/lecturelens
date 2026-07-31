package com.example.courselingo.chapter.service;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.chapter")
public class CourseChapterProperties {

    private boolean enabled = true;
    private int windowSeconds = 240;
    private int maxChapters = 20;
    private int maxEvidenceItems = 24;
    private int maxCharsPerWindow = 1200;
    private int maxPromptChars = 24000;
    private int maxTokens = 4096;
    private int maxAttempts = 3;
    private Duration llmTimeout = Duration.ofSeconds(60);
    private double minTimelineCoverage = 0.90d;
    private double minEvidenceCoverage = 0.80d;
    private int longTimelineSeconds = 600;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getWindowSeconds() {
        return windowSeconds;
    }

    public void setWindowSeconds(int windowSeconds) {
        this.windowSeconds = Math.max(60, Math.min(windowSeconds, 600));
    }

    public int getMaxChapters() {
        return maxChapters;
    }

    public void setMaxChapters(int maxChapters) {
        this.maxChapters = Math.max(1, Math.min(maxChapters, 20));
    }

    public int getMaxEvidenceItems() {
        return maxEvidenceItems;
    }

    public void setMaxEvidenceItems(int maxEvidenceItems) {
        this.maxEvidenceItems = Math.max(1, Math.min(maxEvidenceItems, 24));
    }

    public int getMaxCharsPerWindow() {
        return maxCharsPerWindow;
    }

    public void setMaxCharsPerWindow(int maxCharsPerWindow) {
        this.maxCharsPerWindow = Math.max(300, Math.min(maxCharsPerWindow, 2000));
    }

    public Duration getLlmTimeout() {
        return llmTimeout;
    }

    public void setLlmTimeout(Duration llmTimeout) {
        this.llmTimeout = llmTimeout == null || llmTimeout.isZero() || llmTimeout.isNegative()
            ? Duration.ofSeconds(60)
            : llmTimeout.compareTo(Duration.ofSeconds(60)) > 0 ? Duration.ofSeconds(60) : llmTimeout;
    }

    public int getMaxPromptChars() {
        return maxPromptChars;
    }

    public void setMaxPromptChars(int maxPromptChars) {
        this.maxPromptChars = Math.max(4000, Math.min(maxPromptChars, 24000));
    }

    public int getMaxTokens() {
        return maxTokens;
    }

    public void setMaxTokens(int maxTokens) {
        this.maxTokens = Math.max(512, Math.min(maxTokens, 4096));
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = Math.max(1, Math.min(maxAttempts, 3));
    }

    public double getMinTimelineCoverage() { return minTimelineCoverage; }

    public void setMinTimelineCoverage(double value) {
        minTimelineCoverage = Math.max(0.5d, Math.min(value, 1.0d));
    }

    public double getMinEvidenceCoverage() { return minEvidenceCoverage; }

    public void setMinEvidenceCoverage(double value) {
        minEvidenceCoverage = Math.max(0.5d, Math.min(value, 1.0d));
    }

    public int getLongTimelineSeconds() { return longTimelineSeconds; }

    public void setLongTimelineSeconds(int value) {
        longTimelineSeconds = Math.max(60, Math.min(value, 3600));
    }
}
