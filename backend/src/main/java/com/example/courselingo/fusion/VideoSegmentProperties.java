package com.example.courselingo.fusion;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.fusion.video-segment")
public class VideoSegmentProperties {

    private boolean enabled = false;
    private int windowSeconds = 60;
    private int maxSegments = 300;
    private boolean includeAsr = true;
    private boolean includeOcr = true;
    private boolean includeVision = true;
    private boolean useLlmSummary = false;
    private String llmProfile = "deepseek-text";
    private boolean failTaskOnError = false;
    private int maxAsrCharsPerWindow = 4000;
    private int maxOcrCharsPerWindow = 2000;
    private int maxVisualCharsPerWindow = 2000;
    private int maxKeywords = 12;

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
        this.windowSeconds = Math.max(1, windowSeconds);
    }

    public int getMaxSegments() {
        return maxSegments;
    }

    public void setMaxSegments(int maxSegments) {
        this.maxSegments = Math.max(1, maxSegments);
    }

    public boolean isIncludeAsr() {
        return includeAsr;
    }

    public void setIncludeAsr(boolean includeAsr) {
        this.includeAsr = includeAsr;
    }

    public boolean isIncludeOcr() {
        return includeOcr;
    }

    public void setIncludeOcr(boolean includeOcr) {
        this.includeOcr = includeOcr;
    }

    public boolean isIncludeVision() {
        return includeVision;
    }

    public void setIncludeVision(boolean includeVision) {
        this.includeVision = includeVision;
    }

    public boolean isUseLlmSummary() {
        return useLlmSummary;
    }

    public void setUseLlmSummary(boolean useLlmSummary) {
        this.useLlmSummary = useLlmSummary;
    }

    public String getLlmProfile() {
        return llmProfile;
    }

    public void setLlmProfile(String llmProfile) {
        this.llmProfile = llmProfile == null || llmProfile.isBlank() ? "deepseek-text" : llmProfile.strip();
    }

    public boolean isFailTaskOnError() {
        return failTaskOnError;
    }

    public void setFailTaskOnError(boolean failTaskOnError) {
        this.failTaskOnError = failTaskOnError;
    }

    public int getMaxAsrCharsPerWindow() {
        return maxAsrCharsPerWindow;
    }

    public void setMaxAsrCharsPerWindow(int maxAsrCharsPerWindow) {
        this.maxAsrCharsPerWindow = Math.max(1, maxAsrCharsPerWindow);
    }

    public int getMaxOcrCharsPerWindow() {
        return maxOcrCharsPerWindow;
    }

    public void setMaxOcrCharsPerWindow(int maxOcrCharsPerWindow) {
        this.maxOcrCharsPerWindow = Math.max(1, maxOcrCharsPerWindow);
    }

    public int getMaxVisualCharsPerWindow() {
        return maxVisualCharsPerWindow;
    }

    public void setMaxVisualCharsPerWindow(int maxVisualCharsPerWindow) {
        this.maxVisualCharsPerWindow = Math.max(1, maxVisualCharsPerWindow);
    }

    public int getMaxKeywords() {
        return maxKeywords;
    }

    public void setMaxKeywords(int maxKeywords) {
        this.maxKeywords = Math.max(1, maxKeywords);
    }
}
