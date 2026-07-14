package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.domain.ArtifactFile;
import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.mapper.ArtifactFileMapper;
import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.io.InputStream;
import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class ArtifactFileDownloadServiceImpl implements ArtifactFileDownloadService {

    private final CurrentUserService currentUserService;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final ArtifactFileMapper artifactFileMapper;
    private final StorageService storageService;

    public ArtifactFileDownloadServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        ArtifactFileMapper artifactFileMapper,
        StorageService storageService
    ) {
        this.currentUserService = currentUserService;
        this.analysisTaskMapper = analysisTaskMapper;
        this.artifactFileMapper = artifactFileMapper;
        this.storageService = storageService;
    }

    @Override
    public ArtifactFileDownloadResponse download(
        String authorizationHeader,
        String taskId,
        String artifactType,
        String language
    ) {
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        ArtifactType normalizedType = parseArtifactType(artifactType);
        ValidatedArtifactFileScope scope = ArtifactFileValidators.validateScope(
            taskId,
            currentUser.userId(),
            normalizedType,
            language
        );
        if (analysisTaskMapper.selectByIdAndUserId(scope.taskId(), scope.userId()) == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        ArtifactFile artifact = artifactFileMapper.selectByScope(
            scope.taskId(),
            scope.userId(),
            scope.artifactType().name(),
            scope.language()
        );
        if (artifact == null) {
            throw new BusinessException(ErrorCode.ARTIFACT_NOT_FOUND);
        }
        InputStream inputStream = storageService.openObject(artifact.getObjectKey());
        return new ArtifactFileDownloadResponse(
            artifact.getFileName(),
            artifact.getContentType(),
            artifact.getSizeBytes() == null ? 0L : artifact.getSizeBytes(),
            inputStream
        );
    }

    private static ArtifactType parseArtifactType(String artifactType) {
        if (artifactType == null || artifactType.isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Artifact type is required");
        }
        try {
            return ArtifactType.valueOf(artifactType.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException exception) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Artifact type is invalid");
        }
    }
}
