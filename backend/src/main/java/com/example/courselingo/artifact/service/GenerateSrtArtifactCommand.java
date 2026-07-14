package com.example.courselingo.artifact.service;

public record GenerateSrtArtifactCommand(
    String taskId,
    Long userId,
    String language
) {
}
