package com.example.courselingo.learning.service;

import java.time.Duration;

public record LearningPackageAiCallResult(
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
