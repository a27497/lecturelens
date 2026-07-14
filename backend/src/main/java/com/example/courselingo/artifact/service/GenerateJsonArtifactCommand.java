package com.example.courselingo.artifact.service;

public record GenerateJsonArtifactCommand(
    String taskId,
    Long userId,
    String targetLanguage
) {
}
