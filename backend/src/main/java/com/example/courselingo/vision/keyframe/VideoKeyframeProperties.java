package com.example.courselingo.vision.keyframe;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.vision.keyframe")
public class VideoKeyframeProperties {

    private boolean enabled = true;
    private int scanIntervalSeconds = 1;
    private int thumbnailWidth = 960;
    private int detectionWidth = 480;
    private int shortVideoAnchorSeconds = 30;
    private int mediumVideoAnchorSeconds = 45;
    private int longVideoAnchorSeconds = 60;
    private int mediumVideoThresholdMinutes = 60;
    private int longVideoThresholdMinutes = 120;
    private int windowSeconds = 60;
    private int maxCandidatesPerWindow = 6;
    private int preOcrMaxFramesPerWindow = 2;
    private int preOcrContentChangeMaxFramesPerWindow = 4;
    private int preOcrLowInformationMaxFramesPerWindow = 1;
    private int preOcrMaxFramesTotal = 360;
    private int frameSamplingBatchSize = 12;
    private List<Double> nearbySampleOffsetsSeconds = new ArrayList<>(List.of(-0.2d, 0.4d, 0.9d, 1.4d));
    private int analysisMaxWidth = 1600;
    private int evidenceMaxWidth = 960;
    private double sharpnessThreshold = 80.0d;
    private double blackBrightnessThreshold = 18.0d;
    private double blankVarianceThreshold = 8.0d;
    private double blankBrightnessThreshold = 245.0d;
    private int perceptualHashDistance = 5;
    private int minKeyframeGapSeconds = 3;
    private int maxKeyframesPerMinute = 4;
    private int slideMaxFramesPerMinute = 2;
    private int codeOrTerminalMaxFramesPerMinute = 4;
    private int visualDemoMaxFramesPerMinute = 3;
    private int talkingOrLowInformationMaxFramesPerMinute = 1;
    private int unknownMaxFramesPerMinute = 2;
    private int contentSlideMinimumTextCharacters = 24;
    private int contentLowInformationMaximumTextCharacters = 12;
    private double contentCodeSymbolRatioThreshold = 0.08d;
    private double contentVisualEdgeDensityThreshold = 0.035d;
    private double contentVisualSceneScoreThreshold = 0.45d;
    private double codeOcrChangeThreshold = 0.06d;
    private int maxKeyframesTotal = 240;
    private double sceneChangeThreshold = 0.30;
    private double contentChangeThreshold = 0.005;
    private int pixelDiffThreshold = 18;
    private String outputFormat = "jpg";
    private long timeoutSeconds = 1800;
    private long branchTimeoutSeconds = 3600;

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

    public int getDetectionWidth() {
        return Math.clamp(detectionWidth, 160, 1920);
    }

    public void setDetectionWidth(int detectionWidth) {
        this.detectionWidth = detectionWidth;
    }

    public int getShortVideoAnchorSeconds() {
        return Math.clamp(shortVideoAnchorSeconds, 5, 600);
    }

    public void setShortVideoAnchorSeconds(int shortVideoAnchorSeconds) {
        this.shortVideoAnchorSeconds = shortVideoAnchorSeconds;
    }

    public int getMediumVideoAnchorSeconds() {
        return Math.clamp(mediumVideoAnchorSeconds, 5, 900);
    }

    public void setMediumVideoAnchorSeconds(int mediumVideoAnchorSeconds) {
        this.mediumVideoAnchorSeconds = mediumVideoAnchorSeconds;
    }

    public int getLongVideoAnchorSeconds() {
        return Math.clamp(longVideoAnchorSeconds, 5, 1800);
    }

    public void setLongVideoAnchorSeconds(int longVideoAnchorSeconds) {
        this.longVideoAnchorSeconds = longVideoAnchorSeconds;
    }

    public int getMediumVideoThresholdMinutes() {
        return Math.clamp(mediumVideoThresholdMinutes, 1, 720);
    }

    public void setMediumVideoThresholdMinutes(int mediumVideoThresholdMinutes) {
        this.mediumVideoThresholdMinutes = mediumVideoThresholdMinutes;
    }

    public int getLongVideoThresholdMinutes() {
        return Math.clamp(longVideoThresholdMinutes, getMediumVideoThresholdMinutes() + 1, 1440);
    }

    public void setLongVideoThresholdMinutes(int longVideoThresholdMinutes) {
        this.longVideoThresholdMinutes = longVideoThresholdMinutes;
    }

    public int getWindowSeconds() {
        return Math.clamp(windowSeconds, 10, 600);
    }

    public void setWindowSeconds(int windowSeconds) {
        this.windowSeconds = windowSeconds;
    }

    public int getMaxCandidatesPerWindow() {
        return Math.clamp(maxCandidatesPerWindow, 1, 24);
    }

    public void setMaxCandidatesPerWindow(int maxCandidatesPerWindow) {
        this.maxCandidatesPerWindow = maxCandidatesPerWindow;
    }

    public int getPreOcrMaxFramesPerWindow() {
        return Math.clamp(preOcrMaxFramesPerWindow, 1, 12);
    }

    public void setPreOcrMaxFramesPerWindow(int value) {
        this.preOcrMaxFramesPerWindow = value;
    }

    public int getPreOcrContentChangeMaxFramesPerWindow() {
        return Math.clamp(preOcrContentChangeMaxFramesPerWindow, getPreOcrMaxFramesPerWindow(), 24);
    }

    public void setPreOcrContentChangeMaxFramesPerWindow(int value) {
        this.preOcrContentChangeMaxFramesPerWindow = value;
    }

    public int getPreOcrLowInformationMaxFramesPerWindow() {
        return Math.clamp(preOcrLowInformationMaxFramesPerWindow, 1, getPreOcrMaxFramesPerWindow());
    }

    public void setPreOcrLowInformationMaxFramesPerWindow(int value) {
        this.preOcrLowInformationMaxFramesPerWindow = value;
    }

    public int getPreOcrMaxFramesTotal() {
        return Math.clamp(preOcrMaxFramesTotal, 1, 2_000);
    }

    public void setPreOcrMaxFramesTotal(int value) {
        this.preOcrMaxFramesTotal = value;
    }

    public int getFrameSamplingBatchSize() {
        return Math.clamp(frameSamplingBatchSize, 1, 64);
    }

    public void setFrameSamplingBatchSize(int value) {
        this.frameSamplingBatchSize = value;
    }

    public List<Double> getNearbySampleOffsetsSeconds() {
        List<Double> values = nearbySampleOffsetsSeconds == null
            ? List.of()
            : nearbySampleOffsetsSeconds.stream()
                .filter(java.util.Objects::nonNull)
                .map(value -> Math.max(-5.0d, Math.min(5.0d, value)))
                .distinct()
                .limit(8)
                .toList();
        return values.isEmpty() ? List.of(-0.2d, 0.4d, 0.9d, 1.4d) : values;
    }

    public void setNearbySampleOffsetsSeconds(List<Double> nearbySampleOffsetsSeconds) {
        this.nearbySampleOffsetsSeconds = nearbySampleOffsetsSeconds;
    }

    public int getAnalysisMaxWidth() {
        return Math.clamp(analysisMaxWidth, 640, 3840);
    }

    public void setAnalysisMaxWidth(int analysisMaxWidth) {
        this.analysisMaxWidth = analysisMaxWidth;
    }

    public int getEvidenceMaxWidth() {
        return Math.clamp(evidenceMaxWidth, 320, 1920);
    }

    public void setEvidenceMaxWidth(int evidenceMaxWidth) {
        this.evidenceMaxWidth = evidenceMaxWidth;
    }

    public double getSharpnessThreshold() {
        return Math.max(0.0d, Math.min(100_000.0d, sharpnessThreshold));
    }

    public void setSharpnessThreshold(double sharpnessThreshold) {
        this.sharpnessThreshold = sharpnessThreshold;
    }

    public double getBlackBrightnessThreshold() {
        return Math.max(0.0d, Math.min(80.0d, blackBrightnessThreshold));
    }

    public void setBlackBrightnessThreshold(double blackBrightnessThreshold) {
        this.blackBrightnessThreshold = blackBrightnessThreshold;
    }

    public double getBlankVarianceThreshold() {
        return Math.max(0.0d, Math.min(100.0d, blankVarianceThreshold));
    }

    public void setBlankVarianceThreshold(double blankVarianceThreshold) {
        this.blankVarianceThreshold = blankVarianceThreshold;
    }

    public double getBlankBrightnessThreshold() {
        return Math.max(180.0d, Math.min(255.0d, blankBrightnessThreshold));
    }

    public void setBlankBrightnessThreshold(double blankBrightnessThreshold) {
        this.blankBrightnessThreshold = blankBrightnessThreshold;
    }

    public int getPerceptualHashDistance() {
        return Math.clamp(perceptualHashDistance, 0, 32);
    }

    public void setPerceptualHashDistance(int perceptualHashDistance) {
        this.perceptualHashDistance = perceptualHashDistance;
    }

    public int getPeriodicAnchorSeconds() {
        return getLongVideoAnchorSeconds();
    }

    public void setPeriodicAnchorSeconds(int periodicAnchorSeconds) {
        this.longVideoAnchorSeconds = periodicAnchorSeconds;
    }

    public int getMinKeyframeGapSeconds() {
        return Math.clamp(minKeyframeGapSeconds, 0, 600);
    }

    public void setMinKeyframeGapSeconds(int minKeyframeGapSeconds) {
        this.minKeyframeGapSeconds = minKeyframeGapSeconds;
    }

    public int getMaxKeyframesPerMinute() {
        return Math.clamp(maxKeyframesPerMinute, 1, 12);
    }

    public void setMaxKeyframesPerMinute(int maxKeyframesPerMinute) {
        this.maxKeyframesPerMinute = maxKeyframesPerMinute;
    }

    public int getMaxKeyframesTotal() {
        return Math.clamp(maxKeyframesTotal, 1, 1_000);
    }

    public void setMaxKeyframesTotal(int maxKeyframesTotal) {
        this.maxKeyframesTotal = maxKeyframesTotal;
    }

    public double getSceneChangeThreshold() {
        return Math.max(0.0d, Math.min(1.0d, sceneChangeThreshold));
    }

    public void setSceneChangeThreshold(double sceneChangeThreshold) {
        this.sceneChangeThreshold = sceneChangeThreshold;
    }

    public double getContentChangeThreshold() {
        return Math.min(Math.max(0.001d, getSceneChangeThreshold()), Math.max(0.001d, Math.min(1.0d, contentChangeThreshold)));
    }

    public void setContentChangeThreshold(double contentChangeThreshold) {
        this.contentChangeThreshold = contentChangeThreshold;
    }

    public int getPixelDiffThreshold() {
        return Math.clamp(pixelDiffThreshold, 1, 255);
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
        return Math.clamp(timeoutSeconds, 1L, 14_400L);
    }

    public void setTimeoutSeconds(long timeoutSeconds) {
        this.timeoutSeconds = timeoutSeconds;
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

    public long getBranchTimeoutSeconds() {
        return Math.clamp(branchTimeoutSeconds, 30L, 14_400L);
    }

    public void setBranchTimeoutSeconds(long branchTimeoutSeconds) {
        this.branchTimeoutSeconds = branchTimeoutSeconds;
    }

    public Duration branchTimeout() {
        return Duration.ofSeconds(getBranchTimeoutSeconds());
    }

    public int anchorIntervalSeconds(long durationMillis) {
        long durationMinutes = Math.max(0L, durationMillis) / 60_000L;
        if (durationMinutes <= getMediumVideoThresholdMinutes()) {
            return getShortVideoAnchorSeconds();
        }
        if (durationMinutes <= getLongVideoThresholdMinutes()) {
            return getMediumVideoAnchorSeconds();
        }
        return getLongVideoAnchorSeconds();
    }

    public int maxSourceFramesTotal() {
        return Math.max(getMaxKeyframesTotal(), Math.min(3_000, getPreOcrMaxFramesTotal() * 3));
    }

    private static double unit(double value) {
        return Double.isFinite(value) ? Math.max(0.0d, Math.min(1.0d, value)) : 0.0d;
    }
}
