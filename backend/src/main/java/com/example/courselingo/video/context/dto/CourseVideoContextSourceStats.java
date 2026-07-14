package com.example.courselingo.video.context.dto;

import java.time.LocalDateTime;

public record CourseVideoContextSourceStats(
    Integer subtitleSegmentCount,
    Integer translatedSegmentCount,
    Integer chapterCount,
    Integer chunkCount,
    Boolean hasLearningPackage,
    Boolean hasVideoSegmentAsrText,
    LocalDateTime updatedAt
) {
}
