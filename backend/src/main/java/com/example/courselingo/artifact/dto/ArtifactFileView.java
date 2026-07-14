package com.example.courselingo.artifact.dto;

import com.example.courselingo.artifact.domain.ArtifactType;
import java.time.LocalDateTime;

public record ArtifactFileView(
    String taskId,
    ArtifactType artifactType,
    String language,
    String fileName,
    String contentType,
    String storageBackend,
    long sizeBytes,
    String sha256,
    LocalDateTime createdAt,
    LocalDateTime updatedAt
) {
}
