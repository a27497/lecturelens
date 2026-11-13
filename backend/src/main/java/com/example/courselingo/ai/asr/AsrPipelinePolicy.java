package com.example.courselingo.ai.asr;

/** Frozen opt-in preparation policy; absence keeps legacy task serialization unchanged. */
public record AsrPipelinePolicy(int initial, int maximum, int successStreak, int requestsPerSecond,
    long cooldownMillis, boolean mergeEnabled, long mergeMinMillis, long mergeTargetMillis,
    long mergeMaxMillis, boolean cacheEnabled, long cacheTtlSeconds, int cacheMaxEntries,
    String configIdentity, String limiterKey) {
    public AsrPipelinePolicy {
        if (initial < 1 || maximum < initial || maximum > 8 || successStreak < 1 || successStreak > 100
            || requestsPerSecond < 1 || requestsPerSecond > 10 || cooldownMillis < 1 || cooldownMillis > 30000
            || mergeMinMillis < 1000 || mergeTargetMillis < mergeMinMillis || mergeMaxMillis < mergeTargetMillis
            || mergeMaxMillis > 120000 || cacheTtlSeconds < 1 || cacheTtlSeconds > 86400
            || cacheMaxEntries < 1 || cacheMaxEntries > 1024 || configIdentity == null || !configIdentity.matches("[0-9a-f]{64}")
            || limiterKey == null || !limiterKey.matches("[0-9a-f]{64}"))
            throw new IllegalArgumentException("Invalid ASR pipeline policy");
    }
}
