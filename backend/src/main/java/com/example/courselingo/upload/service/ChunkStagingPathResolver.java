package com.example.courselingo.upload.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.nio.file.Path;
import org.springframework.stereotype.Component;

@Component
public class ChunkStagingPathResolver {

    private final Path stagingRoot;

    public ChunkStagingPathResolver(ChunkStagingProperties properties) {
        this.stagingRoot = properties.chunkStagingDir().toAbsolutePath().normalize();
    }

    public Path resolve(Long userId, String uploadId, Integer chunkIndex) {
        Path path = resolveSessionDirectory(userId, uploadId)
            .resolve(chunkIndex + ".part")
            .normalize();
        if (!path.startsWith(stagingRoot)) {
            throw new BusinessException(ErrorCode.UPLOAD_CHUNK_SAVE_FAILED);
        }
        return path;
    }

    public Path resolveSessionDirectory(Long userId, String uploadId) {
        Path path = stagingRoot
            .resolve(String.valueOf(userId))
            .resolve(uploadId)
            .normalize();
        if (!path.startsWith(stagingRoot)) {
            throw new BusinessException(ErrorCode.UPLOAD_CHUNK_SAVE_FAILED);
        }
        return path;
    }

    public Path resolveAssembledFile(Long userId, String uploadId, String ext) {
        Path path = resolveSessionDirectory(userId, uploadId)
            .resolve("assembled")
            .resolve("source." + ext)
            .normalize();
        if (!path.startsWith(stagingRoot)) {
            throw new BusinessException(ErrorCode.UPLOAD_CHUNK_SAVE_FAILED);
        }
        return path;
    }
}
