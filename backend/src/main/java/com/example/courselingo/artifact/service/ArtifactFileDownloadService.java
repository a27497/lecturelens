package com.example.courselingo.artifact.service;

public interface ArtifactFileDownloadService {

    ArtifactFileDownloadResponse download(
        String authorizationHeader,
        String taskId,
        String artifactType,
        String language
    );
}
