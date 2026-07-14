package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.domain.ArtifactType;

record ValidatedArtifactFileCommand(
    String taskId,
    Long userId,
    ArtifactType artifactType,
    String language,
    String fileName,
    String contentType,
    byte[] contentBytes
) {
}
