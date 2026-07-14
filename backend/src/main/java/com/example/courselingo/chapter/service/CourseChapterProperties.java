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
    private Duration llmTimeout = Duration.ofSeconds(90);

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
            ? Duration.ofSeconds(90)
            : llmTimeout;
    }
}
