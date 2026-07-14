package com.example.courselingo.fusion;

import java.util.List;

public record VideoSegmentResponse(
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
}
