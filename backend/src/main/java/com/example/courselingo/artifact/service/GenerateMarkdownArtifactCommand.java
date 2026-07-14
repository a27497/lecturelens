package com.example.courselingo.artifact.service;

public record GenerateMarkdownArtifactCommand(
    String taskId,
    Long userId,
    String targetLanguage
) {
}
