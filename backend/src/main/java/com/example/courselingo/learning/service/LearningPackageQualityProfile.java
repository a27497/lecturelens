package com.example.courselingo.learning.service;

import com.example.courselingo.fusion.VideoSegment;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import java.util.List;

record LearningPackageQualityProfile(
    String tier,
    int summaryMin,
    int summaryMax,
    int keyPointsMin,
    int keyPointsMax,
    int glossaryMin,
    int glossaryMax,
    int qaMin,
    int qaMax,
    boolean sparseEvidence
) {
    static LearningPackageQualityProfile from(
        List<SubtitleSegment> source,
        List<VideoSegment> multimodal,
        LearningPackageProperties properties
    ) {
        long duration = 0L;
        if (source != null) {
            duration = Math.max(duration, source.stream().map(SubtitleSegment::getEndMillis)
                .filter(java.util.Objects::nonNull).mapToLong(Long::longValue).max().orElse(0L));
        }
        if (multimodal != null) {
            duration = Math.max(duration, multimodal.stream().map(VideoSegment::getEndMillis)
                .filter(java.util.Objects::nonNull).mapToLong(Long::longValue).max().orElse(0L));
        }
        int evidenceCount = (source == null ? 0 : source.size()) + (multimodal == null ? 0 : multimodal.size());
        boolean sparse = evidenceCount < 6;
        if (sparse) return new LearningPackageQualityProfile("SPARSE", 1, 300, 1, 3, 0, 3, 0, 2, true);
        long minutes = duration / 60_000L;
        if (minutes >= properties.longCourseMinutes()) {
            return new LearningPackageQualityProfile(
                "LONG", properties.longSummaryMin(), properties.longSummaryMax(), 6, 12, 8, 15, 5, 8, false
            );
        }
        if (minutes >= properties.shortCourseMinutes()) {
            return new LearningPackageQualityProfile(
                "MEDIUM", properties.mediumSummaryMin(), properties.mediumSummaryMax(), 4, 8, 5, 10, 3, 6, false
            );
        }
        return new LearningPackageQualityProfile(
            "SHORT", properties.shortSummaryMin(), properties.shortSummaryMax(), 3, 5, 3, 6, 2, 4, false
        );
    }

    String promptRequirements() {
        return "tier=" + tier + ", summary effective characters=" + summaryMin + "-" + summaryMax
            + ", keyPoints=" + keyPointsMin + "-" + keyPointsMax
            + ", glossary=" + glossaryMin + "-" + glossaryMax
            + ", qa=" + qaMin + "-" + qaMax;
    }
}
