package com.example.courselingo.video.context.service;

import com.example.courselingo.video.context.dto.CourseVideoContextChapterResponse;
import com.example.courselingo.video.context.dto.CourseVideoContextSourceStats;
import java.time.LocalDateTime;
import java.util.List;

public record CourseVideoContextSourceSnapshot(
    Integer subtitleSegmentCount,
    Integer translatedSegmentCount,
    Integer chapterCount,
    Integer chunkCount,
    Boolean hasLearningPackage,
    Boolean hasVideoSegmentAsrText,
    LocalDateTime updatedAt,
    List<CourseVideoContextChapterResponse> chapters,
    String globalSummary,
    List<String> globalKeywords
) {

    public CourseVideoContextSourceStats toStats() {
        return new CourseVideoContextSourceStats(
            subtitleSegmentCount,
            translatedSegmentCount,
            chapterCount,
            chunkCount,
            hasLearningPackage,
            hasVideoSegmentAsrText,
            updatedAt
        );
    }
}
