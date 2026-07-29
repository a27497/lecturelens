package com.example.courselingo.fusion;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Safe, explainable provenance for a fused timeline segment. Values describe availability rather than
 * containing provider payloads, paths, or object-storage keys.
 */
public record VideoSegmentSourceStatus(
    Map<String, String> sources,
    Map<String, Double> confidenceComponents,
    boolean degraded
) {
    public VideoSegmentSourceStatus {
        sources = sources == null ? Map.of() : Collections.unmodifiableMap(new LinkedHashMap<>(sources));
        confidenceComponents = confidenceComponents == null
            ? Map.of()
            : Collections.unmodifiableMap(new LinkedHashMap<>(confidenceComponents));
    }

    public static VideoSegmentSourceStatus empty() {
        return new VideoSegmentSourceStatus(Map.of(), Map.of(), false);
    }
}
