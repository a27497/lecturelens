package com.example.courselingo.vision.keyframe;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.vision.keyframe")
public class VideoKeyframeProperties {

    private boolean enabled = true;
    private int scanIntervalSeconds = 1;
    private int thumbnailWidth = 320;
    private int periodicAnchorSeconds = 60;
    private int minKeyframeGapSeconds = 3;
    private int maxKeyframesPerMinute = 4;
    private int maxKeyframesTotal = 300;
    private double sceneChangeThreshold = 0.08;
    private int pixelDiffThreshold = 18;
    private String outputFormat = "jpg";
    private long timeoutSeconds = 600;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getScanIntervalSeconds() {
        return Math.max(1, scanIntervalSeconds);
    }

    public void setScanIntervalSeconds(int scanIntervalSeconds) {
        this.scanIntervalSeconds = scanIntervalSeconds;
    }

    public int getThumbnailWidth() {
        return Math.max(64, thumbnailWidth);
    }

    public void setThumbnailWidth(int thumbnailWidth) {
        this.thumbnailWidth = thumbnailWidth;
    }

    public int getPeriodicAnchorSeconds() {
        return Math.max(1, periodicAnchorSeconds);
    }

    public void setPeriodicAnchorSeconds(int periodicAnchorSeconds) {
        this.periodicAnchorSeconds = periodicAnchorSeconds;
    }

    public int getMinKeyframeGapSeconds() {
        return Math.max(0, minKeyframeGapSeconds);
    }

    public void setMinKeyframeGapSeconds(int minKeyframeGapSeconds) {
        this.minKeyframeGapSeconds = minKeyframeGapSeconds;
    }

    public int getMaxKeyframesPerMinute() {
        return Math.max(1, maxKeyframesPerMinute);
    }

    public void setMaxKeyframesPerMinute(int maxKeyframesPerMinute) {
        this.maxKeyframesPerMinute = maxKeyframesPerMinute;
    }

    public int getMaxKeyframesTotal() {
        return Math.max(1, maxKeyframesTotal);
    }

    public void setMaxKeyframesTotal(int maxKeyframesTotal) {
        this.maxKeyframesTotal = maxKeyframesTotal;
    }

    public double getSceneChangeThreshold() {
        return Math.max(0.0, sceneChangeThreshold);
    }

    public void setSceneChangeThreshold(double sceneChangeThreshold) {
        this.sceneChangeThreshold = sceneChangeThreshold;
    }

    public int getPixelDiffThreshold() {
        return Math.max(1, pixelDiffThreshold);
    }

    public void setPixelDiffThreshold(int pixelDiffThreshold) {
        this.pixelDiffThreshold = pixelDiffThreshold;
    }

    public String getOutputFormat() {
        if (outputFormat == null || outputFormat.isBlank()) {
            return "jpg";
        }
        return outputFormat.strip().toLowerCase();
    }

    public void setOutputFormat(String outputFormat) {
        this.outputFormat = outputFormat;
    }

    public long getTimeoutSeconds() {
        return Math.max(1L, timeoutSeconds);
    }

    public void setTimeoutSeconds(long timeoutSeconds) {
        this.timeoutSeconds = timeoutSeconds;
    }

    public int maxSourceFramesTotal() {
        return Math.max(getMaxKeyframesTotal(), Math.min(3_000, getMaxKeyframesTotal() * 10));
    }
}
