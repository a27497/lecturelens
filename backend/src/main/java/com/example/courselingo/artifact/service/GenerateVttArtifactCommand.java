package com.example.courselingo.artifact.service;

public record GenerateVttArtifactCommand(
    String taskId,
    Long userId,
    String language
) {
}
