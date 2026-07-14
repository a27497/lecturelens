package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.domain.ArtifactType;

record ValidatedArtifactFileScope(
    String taskId,
    Long userId,
    ArtifactType artifactType,
    String language
) {
}
