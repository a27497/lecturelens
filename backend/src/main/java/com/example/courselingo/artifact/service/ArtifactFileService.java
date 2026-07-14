package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.dto.ArtifactFileView;

public interface ArtifactFileService {

    ArtifactFileView saveArtifactFile(SaveArtifactFileCommand command);

    int deleteArtifact(String taskId, Long userId, ArtifactType artifactType, String language);
}
