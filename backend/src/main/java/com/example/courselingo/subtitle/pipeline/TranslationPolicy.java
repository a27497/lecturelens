package com.example.courselingo.subtitle.pipeline;

/** Immutable execution parameters, distinct from the system model binding version. */
public record TranslationPolicy(
    String engineVersion, String tokenCounter, long requestTimeoutMillis, long totalTimeoutMillis,
    int outputMin, int outputMax, double outputRatio, int outputSlack, double safetyFactor,
    int contextReserve, int contextLimit, int maxDepth, int maxAttempts, int maxCalls,
    long tokenBudget, int batchMaxSegments, int batchMaxInputChars
) {
    public TranslationPolicy {
        if (!"translation-v2.1".equals(engineVersion) || !"UTF8_CONSERVATIVE_V1".equals(tokenCounter)
            || requestTimeoutMillis < 1 || requestTimeoutMillis > 120000
            || totalTimeoutMillis < 1 || totalTimeoutMillis > 900000
            || outputMin < 1 || outputMin > outputMax || outputMax > 8192
            || !Double.isFinite(outputRatio) || outputRatio < 1 || outputRatio > 4
            || outputSlack < 0 || outputSlack > 1024 || !Double.isFinite(safetyFactor)
            || safetyFactor < 1 || safetyFactor > 2 || contextReserve < 0 || contextReserve > 8192
            || contextLimit < 1024 || contextLimit > 1000000 || maxDepth < 0 || maxDepth > 6
            || maxAttempts < 1 || maxAttempts > 3 || maxCalls < 1 || maxCalls > 256
            || tokenBudget < 1 || tokenBudget > 200000 || batchMaxSegments < 1
            || batchMaxSegments > 10000 || batchMaxInputChars < 1 || batchMaxInputChars > 100000)
            throw new IllegalArgumentException("Invalid translation policy");
    }
}
