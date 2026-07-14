package com.example.courselingo.result.dto;

import java.time.LocalDateTime;

public record ResultArtifactFile(
    String artifactType,
    String language,
    String fileName,
    String contentType,
    long sizeBytes,
    String sha256,
    LocalDateTime createdAt
) {
}
