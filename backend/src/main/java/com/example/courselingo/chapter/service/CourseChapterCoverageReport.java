package com.example.courselingo.chapter.service;

import java.util.List;

public record CourseChapterCoverageReport(
    boolean valid,
    double timelineCoverageRatio,
    double evidenceCoverageRatio,
    long maxGapMillis,
    List<Integer> missingEvidenceIndexes,
    List<String> missingTimeRanges,
    List<Integer> chaptersWithoutEvidence,
    List<String> violations
) {
    public CourseChapterCoverageReport {
        missingEvidenceIndexes = missingEvidenceIndexes == null ? List.of() : List.copyOf(missingEvidenceIndexes);
        missingTimeRanges = missingTimeRanges == null ? List.of() : List.copyOf(missingTimeRanges);
        chaptersWithoutEvidence = chaptersWithoutEvidence == null ? List.of() : List.copyOf(chaptersWithoutEvidence);
        violations = violations == null ? List.of() : List.copyOf(violations);
    }

    static CourseChapterCoverageReport structuralFailure(String violation) {
        return new CourseChapterCoverageReport(
            false, 0.0d, 0.0d, 0L, List.of(), List.of(), List.of(), List.of(violation)
        );
    }
}
