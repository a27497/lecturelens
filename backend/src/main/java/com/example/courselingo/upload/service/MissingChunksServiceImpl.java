package com.example.courselingo.upload.service;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.upload.dto.MissingChunksResponse;
import com.example.courselingo.upload.entity.UploadSession;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class MissingChunksServiceImpl implements MissingChunksService {

    private static final Logger log = LoggerFactory.getLogger(MissingChunksServiceImpl.class);
    private static final Pattern UPLOAD_ID_PATTERN = Pattern.compile("^up_[A-Za-z0-9_-]+$");
    private static final Pattern PART_FILE_PATTERN = Pattern.compile("^([0-9]+)\\.part$");

    private final CurrentUserService currentUserService;
    private final UploadSessionOwnerGuard ownerGuard;
    private final ChunkStagingPathResolver pathResolver;
    private final UploadChunkStateService chunkStateService;

    public MissingChunksServiceImpl(
        CurrentUserService currentUserService,
        UploadSessionOwnerGuard ownerGuard,
        ChunkStagingPathResolver pathResolver,
        UploadChunkStateService chunkStateService
    ) {
        this.currentUserService = currentUserService;
        this.ownerGuard = ownerGuard;
        this.pathResolver = pathResolver;
        this.chunkStateService = chunkStateService;
    }

    @Override
    public MissingChunksResponse findMissingChunks(String authorizationHeader, String uploadId) {
        validateUploadId(uploadId);
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        UploadSession uploadSession = ownerGuard.requireOwner(uploadId, currentUser.userId());

        List<Integer> uploadedChunks = findUploadedChunks(currentUser.userId(), uploadId, uploadSession.getTotalChunks());
        List<Integer> missingChunks = missingChunks(uploadedChunks, uploadSession.getTotalChunks());
        return new MissingChunksResponse(
            uploadId,
            uploadSession.getTotalChunks(),
            uploadedChunks,
            missingChunks,
            missingChunks.isEmpty(),
            uploadSession.getStatus()
        );
    }

    private void validateUploadId(String uploadId) {
        if (uploadId == null || !UPLOAD_ID_PATTERN.matcher(uploadId).matches()) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_SESSION_ID);
        }
    }

    private List<Integer> findUploadedChunks(Long userId, String uploadId, Integer totalChunks) {
        try {
            return chunkStateService.findUploadedChunks(uploadId, totalChunks)
                .orElseGet(() -> scanUploadedChunks(userId, uploadId, totalChunks));
        } catch (RuntimeException exception) {
            log.warn("Upload chunk state read failed for uploadId={}", uploadId, exception);
            return scanUploadedChunks(userId, uploadId, totalChunks);
        }
    }

    private List<Integer> scanUploadedChunks(Long userId, String uploadId, Integer totalChunks) {
        Path sessionDirectory = pathResolver.resolveSessionDirectory(userId, uploadId);
        if (!Files.isDirectory(sessionDirectory)) {
            return List.of();
        }
        Set<Integer> uploaded = new TreeSet<>();
        try (Stream<Path> paths = Files.list(sessionDirectory)) {
            paths
                .filter(Files::isRegularFile)
                .map(path -> path.getFileName().toString())
                .map(this::parseChunkIndex)
                .filter(index -> index != null && index >= 0 && index < totalChunks)
                .forEach(uploaded::add);
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.UPLOAD_CHUNK_SAVE_FAILED, exception);
        }
        return List.copyOf(uploaded);
    }

    private Integer parseChunkIndex(String filename) {
        java.util.regex.Matcher matcher = PART_FILE_PATTERN.matcher(filename);
        if (!matcher.matches()) {
            return null;
        }
        try {
            return Integer.valueOf(matcher.group(1));
        } catch (NumberFormatException exception) {
            return null;
        }
    }

    private List<Integer> missingChunks(List<Integer> uploadedChunks, Integer totalChunks) {
        Set<Integer> uploaded = Set.copyOf(uploadedChunks);
        List<Integer> missing = new ArrayList<>();
        for (int i = 0; i < totalChunks; i++) {
            if (!uploaded.contains(i)) {
                missing.add(i);
            }
        }
        return missing;
    }
}
