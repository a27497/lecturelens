package com.example.courselingo.task.runner;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import com.example.courselingo.upload.service.ChunkStagingPathResolver;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Objects;
import java.util.regex.Pattern;

public class ResolveUploadedSourceStep implements PipelineAnalysisTaskStep {

    private static final String UPLOADED_STATUS = "UPLOADED";
    private static final String STORED_STATUS = "STORED";
    private static final String MINIO_STORAGE_TYPE = "MINIO";
    private static final Pattern SAFE_EXTENSION = Pattern.compile("[A-Za-z0-9][A-Za-z0-9_-]{0,15}");

    private final UploadSessionMapper uploadSessionMapper;
    private final ChunkStagingPathResolver pathResolver;
    private final StorageService storageService;

    public ResolveUploadedSourceStep(
        UploadSessionMapper uploadSessionMapper,
        ChunkStagingPathResolver pathResolver,
        StorageService storageService
    ) {
        this.uploadSessionMapper = uploadSessionMapper;
        this.pathResolver = pathResolver;
        this.storageService = storageService;
    }

    @Override
    public PipelineAnalysisTaskStepName name() {
        return PipelineAnalysisTaskStepName.RESOLVE_UPLOADED_SOURCE;
    }

    @Override
    public void execute(PipelineAnalysisTaskStepContext context) {
        UploadSession session = uploadSessionMapper.selectById(context.uploadId());
        validateOwner(context, session);
        validateSupportedStatus(session);
        String ext = validateExtension(session.getExt());
        Path sourcePath = pathResolver.resolveAssembledFile(context.userId(), context.uploadId(), ext);
        if (STORED_STATUS.equals(session.getStatus())) {
            resolveStoredSource(session, sourcePath);
        } else if (!Files.isRegularFile(sourcePath)) {
            throw invalidSource();
        }
        context.setUploadedSourcePath(sourcePath);
    }

    private static void validateOwner(PipelineAnalysisTaskStepContext context, UploadSession session) {
        if (session == null || !Objects.equals(session.getUserId(), context.userId())) {
            throw new BusinessException(ErrorCode.UPLOAD_SESSION_NOT_FOUND);
        }
    }

    private static void validateSupportedStatus(UploadSession session) {
        if (!STORED_STATUS.equals(session.getStatus()) && !UPLOADED_STATUS.equals(session.getStatus())) {
            throw new BusinessException(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);
        }
    }

    private void resolveStoredSource(UploadSession session, Path sourcePath) {
        if (!MINIO_STORAGE_TYPE.equals(session.getStorageType())
            || session.getObjectKey() == null
            || session.getObjectKey().isBlank()
            || session.getSizeBytes() == null
            || session.getSizeBytes() < 0) {
            throw invalidSource();
        }
        boolean objectExists;
        try {
            objectExists = storageService.objectExists(session.getObjectKey());
        } catch (RuntimeException exception) {
            throw invalidSource(exception);
        }
        if (!objectExists) {
            throw invalidSource();
        }
        if (isValidCache(sourcePath, session.getSizeBytes())) {
            return;
        }
        restoreCache(session, sourcePath);
    }

    private static boolean isValidCache(Path sourcePath, long expectedSize) {
        try {
            return Files.isRegularFile(sourcePath) && Files.size(sourcePath) == expectedSize;
        } catch (IOException exception) {
            return false;
        }
    }

    private void restoreCache(UploadSession session, Path sourcePath) {
        Path temporaryFile = null;
        try {
            Files.createDirectories(sourcePath.getParent());
            temporaryFile = Files.createTempFile(sourcePath.getParent(), ".source-", ".tmp");
            long copied;
            try (InputStream inputStream = storageService.openObject(session.getObjectKey())) {
                copied = Files.copy(inputStream, temporaryFile, StandardCopyOption.REPLACE_EXISTING);
            }
            if (copied != session.getSizeBytes() || Files.size(temporaryFile) != session.getSizeBytes()) {
                throw invalidSource();
            }
            replaceCache(temporaryFile, sourcePath);
            temporaryFile = null;
        } catch (BusinessException exception) {
            throw invalidSource(exception);
        } catch (IOException | RuntimeException exception) {
            throw invalidSource(exception);
        } finally {
            if (temporaryFile != null) {
                try {
                    Files.deleteIfExists(temporaryFile);
                } catch (IOException ignored) {
                    // Best-effort cleanup; the sanitized failure remains the public result.
                }
            }
        }
    }

    private static void replaceCache(Path temporaryFile, Path sourcePath) throws IOException {
        try {
            Files.move(
                temporaryFile,
                sourcePath,
                StandardCopyOption.ATOMIC_MOVE,
                StandardCopyOption.REPLACE_EXISTING
            );
        } catch (AtomicMoveNotSupportedException exception) {
            Files.move(temporaryFile, sourcePath, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private static String validateExtension(String ext) {
        if (ext == null || ext.isBlank() || !SAFE_EXTENSION.matcher(ext).matches()) {
            throw invalidSource();
        }
        return ext;
    }

    private static BusinessException invalidSource() {
        return new BusinessException(
            ErrorCode.STORAGE_SOURCE_FILE_INVALID,
            "Uploaded source is not available for pipeline execution"
        );
    }

    private static BusinessException invalidSource(Throwable cause) {
        return new BusinessException(ErrorCode.STORAGE_SOURCE_FILE_INVALID, cause);
    }
}
