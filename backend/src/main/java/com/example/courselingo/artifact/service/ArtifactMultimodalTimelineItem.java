package com.example.courselingo.artifact.service;

import com.example.courselingo.fusion.VideoSegmentSourceStatus;
import java.util.List;

public record ArtifactMultimodalTimelineItem(
    Integer segmentIndex,
    long startMillis,
    long endMillis,
    String timeText,
    String asrText,
    String translatedText,
    String ocrText,
    String visualSummary,
    String fusedSummary,
    List<String> keywords,
    List<Long> evidenceKeyframeIds,
    VideoSegmentSourceStatus sourceStatus,
    Double confidence
) {
    public ArtifactMultimodalTimelineItem {
        keywords = keywords == null ? List.of() : List.copyOf(keywords);
        evidenceKeyframeIds = evidenceKeyframeIds == null ? List.of() : List.copyOf(evidenceKeyframeIds);
        sourceStatus = sourceStatus == null ? VideoSegmentSourceStatus.empty() : sourceStatus;
    }
}
