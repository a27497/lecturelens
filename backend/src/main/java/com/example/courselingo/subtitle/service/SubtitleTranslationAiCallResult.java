package com.example.courselingo.subtitle.service;

import java.time.Duration;

public record SubtitleTranslationAiCallResult(
    int savedCount,
    String provider,
    String model,
    Duration duration,
    Duration providerDuration,
    Integer batchCount,
    Integer retryCount,
    Integer promptTokens,
    Integer completionTokens,
    Integer totalTokens,
    Integer inputUnits,
    Integer outputUnits,
    String requestFingerprint,
    String responseFingerprint
) {

    public SubtitleTranslationAiCallResult(
        int savedCount,
        String provider,
        String model,
        Duration duration,
        Integer promptTokens,
        Integer completionTokens,
        Integer totalTokens,
        Integer inputUnits,
        Integer outputUnits,
        String requestFingerprint,
        String responseFingerprint
    ) {
        this(
            savedCount,
            provider,
            model,
            duration,
            duration,
            null,
            null,
            promptTokens,
            completionTokens,
            totalTokens,
            inputUnits,
            outputUnits,
            requestFingerprint,
            responseFingerprint
        );
    }
}
