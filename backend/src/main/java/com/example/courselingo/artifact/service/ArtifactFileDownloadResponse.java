package com.example.courselingo.artifact.service;

import java.io.InputStream;

public record ArtifactFileDownloadResponse(
    String fileName,
    String contentType,
    long sizeBytes,
    InputStream inputStream
) {
}
