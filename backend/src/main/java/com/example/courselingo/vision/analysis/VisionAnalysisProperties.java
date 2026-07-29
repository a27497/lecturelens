package com.example.courselingo.vision.analysis;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.vision.analysis")
public class VisionAnalysisProperties {

    private boolean enabled = false;
    private String provider = "openai-compatible-vision";
    private String profile = "qwen-vl";
    private int maxFramesTotal = 80;
    private int maxFramesPerMinute = 4;
    private int slideMaxFramesPerMinute = 1;
    private int codeOrTerminalMaxFramesPerMinute = 2;
    private int visualDemoMaxFramesPerMinute = 2;
    private int talkingOrLowInformationMaxFramesPerMinute = 1;
    private int unknownMaxFramesPerMinute = 1;
    private int contentSlideMinimumTextCharacters = 24;
    private int contentLowInformationMaximumTextCharacters = 12;
    private double contentCodeSymbolRatioThreshold = 0.08d;
    private double contentVisualEdgeDensityThreshold = 0.035d;
    private double contentVisualSceneScoreThreshold = 0.45d;
    private double codeOcrChangeThreshold = 0.06d;
    private int minGapSeconds = 10;
    private double ocrTextChangeThreshold = 0.35d;
    private int maxImageWidth = 1600;
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
        return Math.clamp(maxFramesTotal, 0, 1_000);
    }

    public void setMaxFramesTotal(int maxFramesTotal) {
        this.maxFramesTotal = maxFramesTotal;
    }

    public int getMaxFramesPerMinute() {
        return Math.clamp(maxFramesPerMinute, 0, 12);
    }

    public void setMaxFramesPerMinute(int maxFramesPerMinute) {
        this.maxFramesPerMinute = maxFramesPerMinute;
    }

    public int getSlideMaxFramesPerMinute() {
        return Math.clamp(slideMaxFramesPerMinute, 1, 12);
    }

    public void setSlideMaxFramesPerMinute(int value) {
        this.slideMaxFramesPerMinute = value;
    }

    public int getCodeOrTerminalMaxFramesPerMinute() {
        return Math.clamp(codeOrTerminalMaxFramesPerMinute, 1, 12);
    }

    public void setCodeOrTerminalMaxFramesPerMinute(int value) {
        this.codeOrTerminalMaxFramesPerMinute = value;
    }

    public int getVisualDemoMaxFramesPerMinute() {
        return Math.clamp(visualDemoMaxFramesPerMinute, 1, 12);
    }

    public void setVisualDemoMaxFramesPerMinute(int value) {
        this.visualDemoMaxFramesPerMinute = value;
    }

    public int getTalkingOrLowInformationMaxFramesPerMinute() {
        return Math.clamp(talkingOrLowInformationMaxFramesPerMinute, 1, 12);
    }

    public void setTalkingOrLowInformationMaxFramesPerMinute(int value) {
        this.talkingOrLowInformationMaxFramesPerMinute = value;
    }

    public int getUnknownMaxFramesPerMinute() {
        return Math.clamp(unknownMaxFramesPerMinute, 1, 12);
    }

    public void setUnknownMaxFramesPerMinute(int value) {
        this.unknownMaxFramesPerMinute = value;
    }

    public int getContentSlideMinimumTextCharacters() {
        return Math.clamp(contentSlideMinimumTextCharacters, 1, 2_000);
    }

    public void setContentSlideMinimumTextCharacters(int value) {
        this.contentSlideMinimumTextCharacters = value;
    }

    public int getContentLowInformationMaximumTextCharacters() {
        return Math.clamp(contentLowInformationMaximumTextCharacters, 0, 1_000);
    }

    public void setContentLowInformationMaximumTextCharacters(int value) {
        this.contentLowInformationMaximumTextCharacters = value;
    }

    public double getContentCodeSymbolRatioThreshold() {
        return unit(contentCodeSymbolRatioThreshold);
    }

    public void setContentCodeSymbolRatioThreshold(double value) {
        this.contentCodeSymbolRatioThreshold = value;
    }

    public double getContentVisualEdgeDensityThreshold() {
        return unit(contentVisualEdgeDensityThreshold);
    }

    public void setContentVisualEdgeDensityThreshold(double value) {
        this.contentVisualEdgeDensityThreshold = value;
    }

    public double getContentVisualSceneScoreThreshold() {
        return unit(contentVisualSceneScoreThreshold);
    }

    public void setContentVisualSceneScoreThreshold(double value) {
        this.contentVisualSceneScoreThreshold = value;
    }

    public double getCodeOcrChangeThreshold() {
        return unit(codeOcrChangeThreshold);
    }

    public void setCodeOcrChangeThreshold(double value) {
        this.codeOcrChangeThreshold = value;
    }

    public int getMinGapSeconds() {
        return Math.clamp(minGapSeconds, 0, 600);
    }

    public void setMinGapSeconds(int minGapSeconds) {
        this.minGapSeconds = minGapSeconds;
    }

    public double getOcrTextChangeThreshold() {
        return ocrTextChangeThreshold;
    }

    public void setOcrTextChangeThreshold(double ocrTextChangeThreshold) {
        this.ocrTextChangeThreshold = Math.max(0.0d, Math.min(1.0d, ocrTextChangeThreshold));
    }

    public int getMaxImageWidth() {
        return Math.clamp(maxImageWidth, 320, 3840);
    }

    public void setMaxImageWidth(int maxImageWidth) {
        this.maxImageWidth = maxImageWidth;
    }

    public double getJpegQuality() {
        return jpegQuality;
    }

    public void setJpegQuality(double jpegQuality) {
        this.jpegQuality = Math.max(0.1d, Math.min(1.0d, jpegQuality));
    }

    public Duration getTimeout() {
        if (timeout == null || timeout.isZero() || timeout.isNegative()) {
            return Duration.ofSeconds(60);
        }
        return timeout.compareTo(Duration.ofMinutes(10)) > 0 ? Duration.ofMinutes(10) : timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public boolean isFailTaskOnError() {
        return failTaskOnError;
    }

    public void setFailTaskOnError(boolean failTaskOnError) {
        this.failTaskOnError = failTaskOnError;
    }

    private static double unit(double value) {
        return Double.isFinite(value) ? Math.max(0.0d, Math.min(1.0d, value)) : 0.0d;
    }
}
