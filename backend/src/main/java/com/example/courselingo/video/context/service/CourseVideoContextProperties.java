package com.example.courselingo.video.context.service;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.video-context")
public class CourseVideoContextProperties {

    private boolean enabled = true;
    private int chunkWindowSeconds = 240;
    private int maxChunks = 120;
    private int sourcePreviewChars = 1200;
    private int translatedPreviewChars = 1200;
    private int summaryMaxChars = 500;
    private int keywordMaxCount = 12;
    private int evidenceMaxItemsPerChunk = 8;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getChunkWindowSeconds() {
        return chunkWindowSeconds;
    }

    public void setChunkWindowSeconds(int chunkWindowSeconds) {
        this.chunkWindowSeconds = chunkWindowSeconds;
    }

    public int getMaxChunks() {
        return maxChunks;
    }

    public void setMaxChunks(int maxChunks) {
        this.maxChunks = maxChunks;
    }

    public int getSourcePreviewChars() {
        return sourcePreviewChars;
    }

    public void setSourcePreviewChars(int sourcePreviewChars) {
        this.sourcePreviewChars = sourcePreviewChars;
    }

    public int getTranslatedPreviewChars() {
        return translatedPreviewChars;
    }

    public void setTranslatedPreviewChars(int translatedPreviewChars) {
        this.translatedPreviewChars = translatedPreviewChars;
    }

    public int getSummaryMaxChars() {
        return summaryMaxChars;
    }

    public void setSummaryMaxChars(int summaryMaxChars) {
        this.summaryMaxChars = summaryMaxChars;
    }

    public int getKeywordMaxCount() {
        return keywordMaxCount;
    }

    public void setKeywordMaxCount(int keywordMaxCount) {
        this.keywordMaxCount = keywordMaxCount;
    }

    public int getEvidenceMaxItemsPerChunk() {
        return evidenceMaxItemsPerChunk;
    }

    public void setEvidenceMaxItemsPerChunk(int evidenceMaxItemsPerChunk) {
        this.evidenceMaxItemsPerChunk = evidenceMaxItemsPerChunk;
    }
}
