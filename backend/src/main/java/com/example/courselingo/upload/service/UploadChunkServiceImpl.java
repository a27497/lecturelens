package com.example.courselingo.upload.service;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.metrics.BusinessMetrics;
import com.example.courselingo.upload.dto.UploadChunkResponse;
import com.example.courselingo.upload.entity.UploadSession;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Set;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class UploadChunkServiceImpl implements UploadChunkService {

    private static final Logger log = LoggerFactory.getLogger(UploadChunkServiceImpl.class);
    private static final Pattern UPLOAD_ID_PATTERN = Pattern.compile("^up_[A-Za-z0-9_-]+$");
    private static final String CREATED_STATUS = "CREATED";
    private static final String UPLOADING_STATUS = "UPLOADING";
    private static final Set<String> ALLOWED_STATUSES = Set.of(CREATED_STATUS, UPLOADING_STATUS);

    private final CurrentUserService currentUserService;
    private final UploadSessionOwnerGuard ownerGuard;
    private final ChunkStagingPathResolver pathResolver;
    private final UploadChunkStateService chunkStateService;
    private final BusinessMetrics businessMetrics;

    @Autowired
    public UploadChunkServiceImpl(
        CurrentUserService currentUserService,
        UploadSessionOwnerGuard ownerGuard,
        ChunkStagingPathResolver pathResolver,
        UploadChunkStateService chunkStateService,
        BusinessMetrics businessMetrics
    ) {
        this.currentUserService = currentUserService;
        this.ownerGuard = ownerGuard;
        this.pathResolver = pathResolver;
        this.chunkStateService = chunkStateService;
        this.businessMetrics = businessMetrics == null ? BusinessMetrics.noop() : businessMetrics;
    }

    public UploadChunkServiceImpl(
        CurrentUserService currentUserService,
        UploadSessionOwnerGuard ownerGuard,
        ChunkStagingPathResolver pathResolver,
        UploadChunkStateService chunkStateService
    ) {
        this(currentUserService, ownerGuard, pathResolver, chunkStateService, BusinessMetrics.noop());
    }

    @Override
    public UploadChunkResponse upload(
        String authorizationHeader,
        String uploadId,
        Integer chunkIndex,
        MultipartFile file
    ) {
        validateUploadId(uploadId);
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        UploadSession uploadSession = ownerGuard.requireOwner(uploadId, currentUser.userId());
        validateStatus(uploadSession);
        validateChunkIndex(uploadSession, chunkIndex);
        validateFile(uploadSession, chunkIndex, file);

        saveChunk(currentUser.userId(), uploadId, chunkIndex, file);
        markChunkUploaded(uploadId, chunkIndex);
        String status = ensureUploadingStatus(uploadSession, currentUser.userId());
        businessMetrics.incrementUploadChunkReceived("success");
        return new UploadChunkResponse(uploadId, chunkIndex, true, status);
    }

    private void validateUploadId(String uploadId) {
        if (uploadId == null || !UPLOAD_ID_PATTERN.matcher(uploadId).matches()) {
            throw new BusinessException(ErrorCode.UPLOAD_SESSION_NOT_FOUND);
        }
    }

    private void validateStatus(UploadSession uploadSession) {
        if (!ALLOWED_STATUSES.contains(uploadSession.getStatus())) {
            throw new BusinessException(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);
        }
    }

    private void validateChunkIndex(UploadSession uploadSession, Integer chunkIndex) {
        if (chunkIndex == null || chunkIndex < 0 || chunkIndex >= uploadSession.getTotalChunks()) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_CHUNK);
        }
    }

    private void validateFile(UploadSession uploadSession, Integer chunkIndex, MultipartFile file) {
        if (file == null || file.isEmpty() || file.getSize() <= 0) {
            throw new BusinessException(ErrorCode.UPLOAD_EMPTY_CHUNK);
        }
        long expectedSize = expectedChunkSize(uploadSession, chunkIndex);
        if (file.getSize() > uploadSession.getChunkSizeBytes() || file.getSize() != expectedSize) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_CHUNK);
        }
    }

    private long expectedChunkSize(UploadSession uploadSession, Integer chunkIndex) {
        if (chunkIndex.equals(uploadSession.getTotalChunks() - 1)) {
            return uploadSession.getSizeBytes()
                - uploadSession.getChunkSizeBytes() * (uploadSession.getTotalChunks() - 1L);
        }
        return uploadSession.getChunkSizeBytes();
    }

    private void saveChunk(Long userId, String uploadId, Integer chunkIndex, MultipartFile file) {
        Path target = pathResolver.resolve(userId, uploadId, chunkIndex);
        try {
            Files.createDirectories(target.getParent());
            try (InputStream inputStream = file.getInputStream()) {
                Files.copy(inputStream, target, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException | RuntimeException exception) {
            throw new BusinessException(ErrorCode.UPLOAD_CHUNK_SAVE_FAILED, exception);
        }
    }

    private void markChunkUploaded(String uploadId, Integer chunkIndex) {
        try {
            chunkStateService.markUploaded(uploadId, chunkIndex);
        } catch (RuntimeException exception) {
            log.warn("Upload chunk state write failed for uploadId={}", uploadId, exception);
        }
    }

    private String ensureUploadingStatus(UploadSession uploadSession, Long currentUserId) {
        if (CREATED_STATUS.equals(uploadSession.getStatus())) {
            ownerGuard.updateStatus(uploadSession.getId(), currentUserId, UPLOADING_STATUS);
            uploadSession.setStatus(UPLOADING_STATUS);
        }
        return UPLOADING_STATUS;
    }
}
