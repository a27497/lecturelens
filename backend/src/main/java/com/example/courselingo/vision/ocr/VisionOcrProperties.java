package com.example.courselingo.vision.ocr;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.vision.ocr")
public class VisionOcrProperties {

    private boolean enabled = false;
    private String provider = "tesseract";
    private String command = "tesseract";
    private String language = "chi_sim+eng";
    private int timeoutSeconds = 30;
    private int maxTextLength = 8000;
    private int maxKeyframesPerTask = 120;
    private boolean failTaskOnError = false;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getProvider() {
        return blankToDefault(provider, "tesseract");
    }

    public void setProvider(String provider) {
        this.provider = provider;
    }

    public String getCommand() {
        return blankToDefault(command, "tesseract");
    }

    public void setCommand(String command) {
        this.command = command;
    }

    public String getLanguage() {
        return blankToDefault(language, "chi_sim+eng");
    }

    public void setLanguage(String language) {
        this.language = language;
    }

    public int getTimeoutSeconds() {
        return Math.clamp(timeoutSeconds, 1, 300);
    }

    public void setTimeoutSeconds(int timeoutSeconds) {
        this.timeoutSeconds = timeoutSeconds;
    }

    public int getMaxTextLength() {
        return Math.clamp(maxTextLength, 1, 50_000);
    }

    public void setMaxTextLength(int maxTextLength) {
        this.maxTextLength = maxTextLength;
    }

    public int getMaxKeyframesPerTask() {
        return Math.clamp(maxKeyframesPerTask, 1, 1_000);
    }

    public void setMaxKeyframesPerTask(int maxKeyframesPerTask) {
        this.maxKeyframesPerTask = maxKeyframesPerTask;
    }

    public boolean isFailTaskOnError() {
        return failTaskOnError;
    }

    public void setFailTaskOnError(boolean failTaskOnError) {
        this.failTaskOnError = failTaskOnError;
    }

    private static String blankToDefault(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value.strip();
    }
}
