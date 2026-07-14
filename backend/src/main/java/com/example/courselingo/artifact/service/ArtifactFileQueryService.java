package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.dto.ArtifactFileView;
import java.util.List;
import java.util.Optional;

public interface ArtifactFileQueryService {

    List<ArtifactFileView> listByTaskId(String taskId, Long userId);

    Optional<ArtifactFileView> getByTaskTypeAndLanguage(
        String taskId,
        Long userId,
        ArtifactType artifactType,
        String language
    );

    long countByScope(String taskId, Long userId, ArtifactType artifactType, String language);
}
