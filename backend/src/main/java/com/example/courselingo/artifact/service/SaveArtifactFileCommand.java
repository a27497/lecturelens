package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.domain.ArtifactType;
import java.util.Arrays;

public record SaveArtifactFileCommand(
    String taskId,
    Long userId,
    ArtifactType artifactType,
    String language,
    String fileName,
    String contentType,
    byte[] contentBytes
) {

    public SaveArtifactFileCommand {
        contentBytes = contentBytes == null ? null : Arrays.copyOf(contentBytes, contentBytes.length);
    }

    @Override
    public byte[] contentBytes() {
        return contentBytes == null ? null : Arrays.copyOf(contentBytes, contentBytes.length);
    }
}
