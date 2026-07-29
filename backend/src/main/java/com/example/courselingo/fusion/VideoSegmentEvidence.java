package com.example.courselingo.fusion;

import java.util.List;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public record VideoSegmentEvidence(
    List<Long> subtitleSegmentIds,
    List<Long> keyframeIds,
    List<Long> ocrIds,
    List<Long> visualAnalysisIds,
    Map<String, Integer> counts,
    List<Long> translationSegmentIds
) {
    public VideoSegmentEvidence {
        subtitleSegmentIds = subtitleSegmentIds == null ? List.of() : List.copyOf(subtitleSegmentIds);
        keyframeIds = keyframeIds == null ? List.of() : List.copyOf(keyframeIds);
        ocrIds = ocrIds == null ? List.of() : List.copyOf(ocrIds);
        visualAnalysisIds = visualAnalysisIds == null ? List.of() : List.copyOf(visualAnalysisIds);
        counts = counts == null ? Map.of() : Collections.unmodifiableMap(new LinkedHashMap<>(counts));
        translationSegmentIds = translationSegmentIds == null ? List.of() : List.copyOf(translationSegmentIds);
    }

    /** Keeps source compatibility for callers and persisted JSON from before translated evidence was added. */
    public VideoSegmentEvidence(
        List<Long> subtitleSegmentIds,
        List<Long> keyframeIds,
        List<Long> ocrIds,
        List<Long> visualAnalysisIds,
        Map<String, Integer> counts
    ) {
        this(subtitleSegmentIds, keyframeIds, ocrIds, visualAnalysisIds, counts, List.of());
    }
}
