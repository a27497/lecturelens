package com.example.courselingo.fusion;

import java.util.List;

public record VideoSegmentResponse(
    Long segmentId,
    Integer segmentIndex,
    Long startMillis,
    Long endMillis,
    String timeText,
    String asrText,
    String translatedText,
    String ocrText,
    String visualSummary,
    String fusedSummary,
    List<String> keywords,
    VideoSegmentEvidence evidence,
    VideoSegmentSourceStatus sourceStatus,
    String status,
    Double confidence
) {
    /** Keeps source compatibility for callers that predate translated text and source provenance. */
    public VideoSegmentResponse(
        Long segmentId,
        Integer segmentIndex,
        Long startMillis,
        Long endMillis,
        String timeText,
        String asrText,
        String ocrText,
        String visualSummary,
        String fusedSummary,
        List<String> keywords,
        VideoSegmentEvidence evidence,
        String status,
        Double confidence
    ) {
        this(
            segmentId,
            segmentIndex,
            startMillis,
            endMillis,
            timeText,
            asrText,
            "",
            ocrText,
            visualSummary,
            fusedSummary,
            keywords,
            evidence,
            VideoSegmentSourceStatus.empty(),
            status,
            confidence
        );
    }
}
