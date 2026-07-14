package com.example.courselingo.video.context.dto;

import java.util.List;

public record CourseVideoContextChapterResponse(
    Integer chapterIndex,
    String title,
    String summary,
    List<String> keywords,
    Long startMillis,
    Long endMillis,
    List<Integer> coveredChunkIndexes
) {
}
