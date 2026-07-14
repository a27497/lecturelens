package com.example.courselingo.artifact.service;

import org.springframework.stereotype.Component;

@Component
public class ArtifactObjectKeyGenerator {

    public String generate(
        Long userId,
        String taskId,
        String artifactType,
        String language,
        String sha256,
        String fileName
    ) {
        String safeFileName = ArtifactFileNameSanitizer.toObjectKeySegment(fileName);
        return "artifacts/%d/%s/%s/%s/%s-%s".formatted(
            userId,
            taskId,
            artifactType,
            language,
            sha256,
            safeFileName
        );
    }
}
