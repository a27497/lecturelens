package com.example.courselingo.video.context.dto;

import java.time.LocalDateTime;

public record CourseVideoContextRebuildResponse(
    String taskId,
    String targetLanguage,
    Integer chunkCount,
    String buildVersion,
    LocalDateTime rebuiltAt
) {
}
