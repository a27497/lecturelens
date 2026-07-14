package com.example.courselingo.subtitle.service;

import java.time.Duration;

public record SubtitleTranslationAiCallResult(
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
}
