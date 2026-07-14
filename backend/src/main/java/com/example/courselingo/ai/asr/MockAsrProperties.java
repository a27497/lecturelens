package com.example.courselingo.ai.asr;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.ai.asr.mock")
public class MockAsrProperties {

    public static final String DEFAULT_LANGUAGE = "zh-CN";
    public static final String DEFAULT_TEXT = "This is a mock ASR transcript for local development and testing.";
    public static final long DEFAULT_SEGMENT_DURATION_MILLIS = 3_000L;

    private boolean enabled;
    private String defaultLanguage = DEFAULT_LANGUAGE;
    private String defaultText = DEFAULT_TEXT;
    private long segmentDurationMillis = DEFAULT_SEGMENT_DURATION_MILLIS;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getDefaultLanguage() {
        return defaultLanguage;
    }

    public void setDefaultLanguage(String defaultLanguage) {
        this.defaultLanguage = defaultLanguage;
    }

    public String getDefaultText() {
        return defaultText;
    }

    public void setDefaultText(String defaultText) {
        this.defaultText = defaultText;
    }

    public long getSegmentDurationMillis() {
        return segmentDurationMillis;
    }

    public void setSegmentDurationMillis(long segmentDurationMillis) {
        this.segmentDurationMillis = segmentDurationMillis;
    }
}
