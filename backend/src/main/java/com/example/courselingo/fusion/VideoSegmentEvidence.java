package com.example.courselingo.fusion;

import java.util.List;
import java.util.Map;

public record VideoSegmentEvidence(
    List<Long> subtitleSegmentIds,
    List<Long> keyframeIds,
    List<Long> ocrIds,
    List<Long> visualAnalysisIds,
    Map<String, Integer> counts
) {
    public VideoSegmentEvidence {
        subtitleSegmentIds = subtitleSegmentIds == null ? List.of() : List.copyOf(subtitleSegmentIds);
        keyframeIds = keyframeIds == null ? List.of() : List.copyOf(keyframeIds);
        ocrIds = ocrIds == null ? List.of() : List.copyOf(ocrIds);
        visualAnalysisIds = visualAnalysisIds == null ? List.of() : List.copyOf(visualAnalysisIds);
        counts = counts == null ? Map.of() : Map.copyOf(counts);
    }
}
