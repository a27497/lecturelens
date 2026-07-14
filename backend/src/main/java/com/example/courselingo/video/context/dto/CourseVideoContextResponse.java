package com.example.courselingo.video.context.dto;

import java.util.List;

public record CourseVideoContextResponse(
    String taskId,
    String targetLanguage,
    Long durationMillis,
    Integer chunkWindowSeconds,
    String buildVersion,
    CourseVideoContextSourceStats sourceStats,
    String globalSummary,
    List<String> globalKeywords,
    List<CourseVideoContextChapterResponse> chapters,
    List<CourseVideoContextChunkResponse> chunks
) {
}
