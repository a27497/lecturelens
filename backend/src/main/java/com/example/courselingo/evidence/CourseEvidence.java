package com.example.courselingo.evidence;

import java.util.List;

/** Immutable, owner-scoped source snapshot. Raw text is preserved even when excluded from retrieval. */
public record CourseEvidence(
    String evidenceId, String courseId, Long ownerId, long revision,
    String sourceType, String sourceId, List<String> sourceRefs,
    long startMs, long endMs, String language, String rawText, String normalizedText,
    String imageRef, boolean derived, String normalizationVersion, String contentHash,
    boolean retrievable, String qualityReason, Double extractionConfidence, boolean rawTextTruncated
) { }
