package com.example.courselingo.vision.analysis;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.vision.analysis")
public class VisionAnalysisProperties {

    private boolean enabled = false;
    private String provider = "openai-compatible-vision";
    private String profile = "qwen-vl";
    private int maxFramesTotal = 80;
    private int maxFramesPerMinute = 2;
    private int minGapSeconds = 10;
    private double ocrTextChangeThreshold = 0.35d;
    private int maxImageWidth = 1024;
    private double jpegQuality = 0.8d;
    private Duration timeout = Duration.ofSeconds(60);
    private boolean failTaskOnError = false;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getProvider() {
        return provider;
    }

    public void setProvider(String provider) {
        this.provider = provider;
    }

    public String getProfile() {
        return profile;
    }

    public void setProfile(String profile) {
        this.profile = profile;
    }

    public int getMaxFramesTotal() {
        return maxFramesTotal;
    }

    public void setMaxFramesTotal(int maxFramesTotal) {
        this.maxFramesTotal = Math.max(0, maxFramesTotal);
    }

    public int getMaxFramesPerMinute() {
        return maxFramesPerMinute;
    }

    public void setMaxFramesPerMinute(int maxFramesPerMinute) {
        this.maxFramesPerMinute = Math.max(0, maxFramesPerMinute);
    }

    public int getMinGapSeconds() {
        return minGapSeconds;
    }

    public void setMinGapSeconds(int minGapSeconds) {
        this.minGapSeconds = Math.max(0, minGapSeconds);
    }

    public double getOcrTextChangeThreshold() {
        return ocrTextChangeThreshold;
    }

    public void setOcrTextChangeThreshold(double ocrTextChangeThreshold) {
        this.ocrTextChangeThreshold = Math.max(0.0d, Math.min(1.0d, ocrTextChangeThreshold));
    }

    public int getMaxImageWidth() {
        return maxImageWidth;
    }

    public void setMaxImageWidth(int maxImageWidth) {
        this.maxImageWidth = Math.max(1, maxImageWidth);
    }

    public double getJpegQuality() {
        return jpegQuality;
    }

    public void setJpegQuality(double jpegQuality) {
        this.jpegQuality = Math.max(0.1d, Math.min(1.0d, jpegQuality));
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout == null || timeout.isZero() || timeout.isNegative()
            ? Duration.ofSeconds(60)
            : timeout;
    }

    public boolean isFailTaskOnError() {
        return failTaskOnError;
    }

    public void setFailTaskOnError(boolean failTaskOnError) {
        this.failTaskOnError = failTaskOnError;
    }
}
