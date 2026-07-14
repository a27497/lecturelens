package com.example.courselingo.upload.service;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.metrics.BusinessMetrics;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.upload.dto.CompleteUploadResponse;
import com.example.courselingo.upload.entity.UploadSession;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class CompleteUploadServiceImpl implements CompleteUploadService {

    private static final Logger log = LoggerFactory.getLogger(CompleteUploadServiceImpl.class);
    private static final Pattern UPLOAD_ID_PATTERN = Pattern.compile("^up_[A-Za-z0-9_-]+$");
    private static final String CREATED_STATUS = "CREATED";
    private static final String UPLOADING_STATUS = "UPLOADING";
    private static final String STORED_STATUS = "STORED";
    private static final Set<String> ALLOWED_STATUSES = Set.of(CREATED_STATUS, UPLOADING_STATUS);

    private final CurrentUserService currentUserService;
    private final UploadSessionOwnerGuard ownerGuard;
    private final ChunkStagingPathResolver pathResolver;
    private final BasicVideoHeaderValidator videoHeaderValidator;
    private final UploadChunkStateService chunkStateService;
    private final StorageService storageService;
    private final BusinessMetrics businessMetrics;

    @Autowired
    public CompleteUploadServiceImpl(
        CurrentUserService currentUserService,
        UploadSessionOwnerGuard ownerGuard,
        ChunkStagingPathResolver pathResolver,
        BasicVideoHeaderValidator videoHeaderValidator,
        UploadChunkStateService chunkStateService,
        StorageService storageService,
        BusinessMetrics businessMetrics
    ) {
        this.currentUserService = currentUserService;
        this.ownerGuard = ownerGuard;
        this.pathResolver = pathResolver;
        this.videoHeaderValidator = videoHeaderValidator;
        this.chunkStateService = chunkStateService;
        this.storageService = storageService;
        this.businessMetrics = businessMetrics == null ? BusinessMetrics.noop() : businessMetrics;
    }

    public CompleteUploadServiceImpl(
        CurrentUserService currentUserService,
        UploadSessionOwnerGuard ownerGuard,
        ChunkStagingPathResolver pathResolver,
        BasicVideoHeaderValidator videoHeaderValidator,
        UploadChunkStateService chunkStateService,
        StorageService storageService
    ) {
        this(
            currentUserService,
            ownerGuard,
            pathResolver,
            videoHeaderValidator,
            chunkStateService,
            storageService,
            BusinessMetrics.noop()
        );
    }

    @Override
    public CompleteUploadResponse complete(String authorizationHeader, String uploadId) {
        validateUploadId(uploadId);
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        UploadSession uploadSession = ownerGuard.requireOwner(uploadId, currentUser.userId());
        validateStatus(uploadSession);

        List<Path> chunks = resolveExistingChunks(currentUser.userId(), uploadId, uploadSession.getTotalChunks());
        Path assembledFile = pathResolver.resolveAssembledFile(currentUser.userId(), uploadId, uploadSession.getExt());
        mergeChunks(chunks, assembledFile);
        validateSize(uploadSession, assembledFile);
        validateMd5(uploadSession, assembledFile);
        videoHeaderValidator.validate(assembledFile, uploadSession.getExt());
        storageService.putObject(
            uploadSession.getObjectKey(),
            assembledFile,
            uploadSession.getSizeBytes(),
            resolveContentType(uploadSession.getExt())
        );
        markStored(uploadSession, currentUser.userId());
        clearChunkState(uploadId);
        businessMetrics.incrementUploadCompleted("success");

        return new CompleteUploadResponse(
            uploadId,
            uploadSession.getStatus(),
            uploadSession.getSizeBytes(),
            uploadSession.getFileMd5()
        );
    }

    private void validateUploadId(String uploadId) {
        if (uploadId == null || !UPLOAD_ID_PATTERN.matcher(uploadId).matches()) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_SESSION_ID);
        }
    }

    private void validateStatus(UploadSession uploadSession) {
        if (!ALLOWED_STATUSES.contains(uploadSession.getStatus())) {
            throw new BusinessException(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);
        }
    }

    private List<Path> resolveExistingChunks(Long userId, String uploadId, Integer totalChunks) {
        List<Path> chunks = new ArrayList<>();
        List<Integer> missingChunks = new ArrayList<>();
        for (int index = 0; index < totalChunks; index++) {
            Path chunk = pathResolver.resolve(userId, uploadId, index);
            if (!Files.isRegularFile(chunk)) {
                missingChunks.add(index);
            } else {
                chunks.add(chunk);
            }
        }
        if (!missingChunks.isEmpty()) {
            throw new BusinessException(
                ErrorCode.UPLOAD_CHUNK_MISSING,
                ErrorCode.UPLOAD_CHUNK_MISSING.defaultMessage() + ": missingChunks=" + missingChunks
            );
        }
        return chunks;
    }

    private void mergeChunks(List<Path> chunks, Path assembledFile) {
        try {
            Files.createDirectories(assembledFile.getParent());
            try (OutputStream outputStream = Files.newOutputStream(assembledFile)) {
                for (Path chunk : chunks) {
                    Files.copy(chunk, outputStream);
                }
            }
        } catch (IOException | RuntimeException exception) {
            throw new BusinessException(ErrorCode.UPLOAD_MERGE_FAILED, exception);
        }
    }

    private void validateSize(UploadSession uploadSession, Path assembledFile) {
        try {
            if (Files.size(assembledFile) != uploadSession.getSizeBytes()) {
                throw new BusinessException(ErrorCode.UPLOAD_ASSEMBLED_SIZE_MISMATCH);
            }
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.UPLOAD_MERGE_FAILED, exception);
        }
    }

    private void validateMd5(UploadSession uploadSession, Path assembledFile) {
        String actualMd5 = md5Hex(assembledFile);
        if (!actualMd5.equalsIgnoreCase(uploadSession.getFileMd5())) {
            throw new BusinessException(ErrorCode.UPLOAD_ASSEMBLED_MD5_MISMATCH);
        }
    }

    private String md5Hex(Path file) {
        try {
            MessageDigest messageDigest = MessageDigest.getInstance("MD5");
            try (InputStream inputStream = Files.newInputStream(file);
                 DigestInputStream digestInputStream = new DigestInputStream(inputStream, messageDigest)) {
                digestInputStream.transferTo(OutputStream.nullOutputStream());
            }
            return HexFormat.of().formatHex(messageDigest.digest());
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.UPLOAD_MERGE_FAILED, exception);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("MD5 algorithm is not available", exception);
        }
    }

    private static String resolveContentType(String ext) {
        return switch (ext.toLowerCase(java.util.Locale.ROOT)) {
            case "mp4" -> "video/mp4";
            case "mov" -> "video/quicktime";
            case "mkv" -> "video/x-matroska";
            case "webm" -> "video/webm";
            default -> throw new BusinessException(ErrorCode.STORAGE_SOURCE_FILE_INVALID);
        };
    }

    private void markStored(UploadSession uploadSession, Long currentUserId) {
        ownerGuard.updateStatus(uploadSession.getId(), currentUserId, STORED_STATUS);
        uploadSession.setStatus(STORED_STATUS);
    }

    private void clearChunkState(String uploadId) {
        try {
            chunkStateService.clear(uploadId);
        } catch (RuntimeException exception) {
            log.warn("Upload chunk state clear failed for uploadId={}", uploadId, exception);
        }
    }
}
