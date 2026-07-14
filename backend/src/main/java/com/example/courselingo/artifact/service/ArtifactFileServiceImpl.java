package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.domain.ArtifactFile;
import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.dto.ArtifactFileView;
import com.example.courselingo.artifact.mapper.ArtifactFileMapper;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.metrics.BusinessMetrics;
import com.example.courselingo.storage.StorageService;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.HexFormat;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ArtifactFileServiceImpl implements ArtifactFileService {

    private static final String STORAGE_BACKEND = "MINIO";

    private final ArtifactFileMapper mapper;
    private final StorageService storageService;
    private final Clock clock;
    private final ArtifactObjectKeyGenerator objectKeyGenerator;
    private final BusinessMetrics businessMetrics;

    @Autowired
    public ArtifactFileServiceImpl(
        ArtifactFileMapper mapper,
        StorageService storageService,
        ArtifactObjectKeyGenerator objectKeyGenerator,
        BusinessMetrics businessMetrics
    ) {
        this(mapper, storageService, Clock.systemUTC(), objectKeyGenerator, businessMetrics);
    }

    public ArtifactFileServiceImpl(
        ArtifactFileMapper mapper,
        StorageService storageService,
        ArtifactObjectKeyGenerator objectKeyGenerator
    ) {
        this(mapper, storageService, Clock.systemUTC(), objectKeyGenerator, BusinessMetrics.noop());
    }

    public ArtifactFileServiceImpl(
        ArtifactFileMapper mapper,
        StorageService storageService,
        Clock clock,
        ArtifactObjectKeyGenerator objectKeyGenerator
    ) {
        this(mapper, storageService, clock, objectKeyGenerator, BusinessMetrics.noop());
    }

    public ArtifactFileServiceImpl(
        ArtifactFileMapper mapper,
        StorageService storageService,
        Clock clock,
        ArtifactObjectKeyGenerator objectKeyGenerator,
        BusinessMetrics businessMetrics
    ) {
        this.mapper = mapper;
        this.storageService = storageService;
        this.clock = clock == null ? Clock.systemUTC() : clock;
        this.objectKeyGenerator = objectKeyGenerator == null ? new ArtifactObjectKeyGenerator() : objectKeyGenerator;
        this.businessMetrics = businessMetrics == null ? BusinessMetrics.noop() : businessMetrics;
    }

    @Override
    @Transactional
    public ArtifactFileView saveArtifactFile(SaveArtifactFileCommand command) {
        ValidatedArtifactFileCommand validated = ArtifactFileValidators.validateCommand(command);
        String sha256 = sha256(validated.contentBytes());
        String objectKey = objectKeyGenerator.generate(
            validated.userId(),
            validated.taskId(),
            validated.artifactType().name(),
            validated.language(),
            sha256,
            validated.fileName()
        );

        putObject(objectKey, validated);
        ArtifactFile old = null;
        ArtifactFile entity = toEntity(validated, objectKey, sha256);
        try {
            old = mapper.selectByScope(
                validated.taskId(),
                validated.userId(),
                validated.artifactType().name(),
                validated.language()
            );
            mapper.deleteByScope(
                validated.taskId(),
                validated.userId(),
                validated.artifactType().name(),
                validated.language()
            );
            int inserted = mapper.insert(entity);
            if (inserted != 1) {
                throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Artifact record persistence failed");
            }
        } catch (RuntimeException ex) {
            deleteObjectBestEffort(objectKey);
            throw ex;
        }

        if (old != null && old.getObjectKey() != null && !old.getObjectKey().equals(objectKey)) {
            deleteObjectBestEffort(old.getObjectKey());
        }
        businessMetrics.incrementArtifactSaved(validated.artifactType().name(), "success");
        businessMetrics.recordArtifactBytes(validated.artifactType().name(), validated.contentBytes().length);
        return ArtifactFileViewMapper.toView(entity);
    }

    @Override
    public int deleteArtifact(String taskId, Long userId, ArtifactType artifactType, String language) {
        ValidatedArtifactFileScope scope = ArtifactFileValidators.validateScope(taskId, userId, artifactType, language);
        ArtifactFile old = mapper.selectByScope(
            scope.taskId(),
            scope.userId(),
            scope.artifactType().name(),
            scope.language()
        );
        int deleted = mapper.deleteByScope(scope.taskId(), scope.userId(), scope.artifactType().name(), scope.language());
        if (deleted > 0 && old != null && old.getObjectKey() != null) {
            deleteObjectBestEffort(old.getObjectKey());
        }
        return deleted;
    }

    private void putObject(String objectKey, ValidatedArtifactFileCommand command) {
        Path tempFile = null;
        try {
            tempFile = Files.createTempFile("courselingo-artifact-", ".tmp");
            Files.write(tempFile, command.contentBytes());
            storageService.putObject(objectKey, tempFile, command.contentBytes().length, command.contentType());
        } catch (BusinessException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new BusinessException(ErrorCode.STORAGE_OPERATION_FAILED, "Artifact storage write failed", ex);
        } finally {
            if (tempFile != null) {
                try {
                    Files.deleteIfExists(tempFile);
                } catch (Exception ignored) {
                    // Best-effort temporary file cleanup.
                }
            }
        }
    }

    private ArtifactFile toEntity(ValidatedArtifactFileCommand command, String objectKey, String sha256) {
        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        ArtifactFile entity = new ArtifactFile();
        entity.setTaskId(command.taskId());
        entity.setUserId(command.userId());
        entity.setArtifactType(command.artifactType().name());
        entity.setLanguage(command.language());
        entity.setFileName(command.fileName());
        entity.setContentType(command.contentType());
        entity.setStorageBackend(STORAGE_BACKEND);
        entity.setObjectKey(objectKey);
        entity.setSizeBytes((long) command.contentBytes().length);
        entity.setSha256(sha256);
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        return entity;
    }

    private void deleteObjectBestEffort(String objectKey) {
        try {
            storageService.deleteObject(objectKey);
        } catch (RuntimeException ignored) {
            // D10 keeps storage cleanup best-effort because storage and DB are not a distributed transaction.
        }
    }

    private static String sha256(byte[] content) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content));
        } catch (java.security.NoSuchAlgorithmException ex) {
            throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Artifact checksum failed", ex);
        }
    }
}
