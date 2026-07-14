package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.domain.ArtifactFile;
import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.dto.ArtifactFileView;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;

final class ArtifactFileViewMapper {

    private ArtifactFileViewMapper() {
    }

    static ArtifactFileView toView(ArtifactFile entity) {
        if (entity == null
            || entity.getTaskId() == null
            || entity.getTaskId().isBlank()
            || entity.getArtifactType() == null
            || entity.getArtifactType().isBlank()
            || entity.getLanguage() == null
            || entity.getLanguage().isBlank()
            || entity.getFileName() == null
            || entity.getFileName().isBlank()
            || entity.getContentType() == null
            || entity.getContentType().isBlank()
            || entity.getStorageBackend() == null
            || entity.getStorageBackend().isBlank()
            || entity.getSizeBytes() == null
            || entity.getSha256() == null
            || entity.getSha256().isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Artifact row is invalid");
        }
        return new ArtifactFileView(
            entity.getTaskId(),
            ArtifactType.valueOf(entity.getArtifactType()),
            entity.getLanguage(),
            entity.getFileName(),
            entity.getContentType(),
            entity.getStorageBackend(),
            entity.getSizeBytes(),
            entity.getSha256(),
            entity.getCreatedAt(),
            entity.getUpdatedAt()
        );
    }
}
