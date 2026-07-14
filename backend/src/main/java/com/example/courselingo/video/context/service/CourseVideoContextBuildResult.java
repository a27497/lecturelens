package com.example.courselingo.video.context.service;

import com.example.courselingo.video.context.dto.CourseVideoContextChapterResponse;
import com.example.courselingo.video.context.dto.CourseVideoContextChunkResponse;
import java.util.List;

public record CourseVideoContextBuildResult(
    String taskId,
    String targetLanguage,
    Long durationMillis,
    Integer chunkWindowSeconds,
    String buildVersion,
    CourseVideoContextSourceSnapshot sourceStats,
    String globalSummary,
    List<String> globalKeywords,
    List<CourseVideoContextChapterResponse> chapters,
    List<CourseVideoContextChunkResponse> chunks
) {
}
