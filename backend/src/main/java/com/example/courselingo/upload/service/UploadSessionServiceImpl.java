package com.example.courselingo.upload.service;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.metrics.BusinessMetrics;
import com.example.courselingo.upload.dto.CreateUploadSessionRequest;
import com.example.courselingo.upload.dto.CreateUploadSessionResponse;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class UploadSessionServiceImpl implements UploadSessionService {

    private static final Set<String> ALLOWED_EXTENSIONS = Set.of("mp4", "mov", "mkv", "webm");
    private static final Pattern MD5_PATTERN = Pattern.compile("^[0-9a-fA-F]{32}$");
    private static final Pattern WINDOWS_DRIVE_PATTERN = Pattern.compile("^[A-Za-z]:.*");
    private static final String CREATED_STATUS = "CREATED";
    private static final String STORAGE_TYPE_MINIO = "MINIO";

    private final CurrentUserService currentUserService;
    private final UploadSessionMapper uploadSessionMapper;
    private final BusinessMetrics businessMetrics;

    @Autowired
    public UploadSessionServiceImpl(
        CurrentUserService currentUserService,
        UploadSessionMapper uploadSessionMapper,
        BusinessMetrics businessMetrics
    ) {
        this.currentUserService = currentUserService;
        this.uploadSessionMapper = uploadSessionMapper;
        this.businessMetrics = businessMetrics == null ? BusinessMetrics.noop() : businessMetrics;
    }

    public UploadSessionServiceImpl(CurrentUserService currentUserService, UploadSessionMapper uploadSessionMapper) {
        this(currentUserService, uploadSessionMapper, BusinessMetrics.noop());
    }

    @Override
    public CreateUploadSessionResponse create(String authorizationHeader, CreateUploadSessionRequest request) {
        validateChunkArguments(request);
        validateFilename(request.filename());
        validateMd5(request.fileMd5());

        String ext = extractAllowedExtension(request.filename());
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        String uploadId = generateUploadId();

        UploadSession uploadSession = new UploadSession();
        uploadSession.setId(uploadId);
        uploadSession.setUserId(currentUser.userId());
        uploadSession.setFilename(request.filename());
        uploadSession.setExt(ext);
        uploadSession.setTotalChunks(request.totalChunks());
        uploadSession.setChunkSizeBytes(request.chunkSizeBytes());
        uploadSession.setSizeBytes(request.sizeBytes());
        uploadSession.setFileMd5(request.fileMd5().toLowerCase(Locale.ROOT));
        uploadSession.setStatus(CREATED_STATUS);
        uploadSession.setStorageType(STORAGE_TYPE_MINIO);
        uploadSession.setObjectKey(buildObjectKey(currentUser.userId(), uploadId, ext));

        int inserted = uploadSessionMapper.insert(uploadSession);
        if (inserted != 1) {
            throw new BusinessException(ErrorCode.UPLOAD_SESSION_CREATE_FAILED);
        }
        businessMetrics.incrementUploadSessionCreated("success");
        return new CreateUploadSessionResponse(uploadId, CREATED_STATUS);
    }

    private void validateChunkArguments(CreateUploadSessionRequest request) {
        if (request.sizeBytes() == null
            || request.chunkSizeBytes() == null
            || request.totalChunks() == null
            || request.sizeBytes() <= 0
            || request.chunkSizeBytes() <= 0
            || request.totalChunks() <= 0) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_CHUNK);
        }
    }

    private void validateFilename(String filename) {
        if (filename == null
            || filename.isBlank()
            || filename.contains("/")
            || filename.contains("\\")
            || containsControlCharacter(filename)
            || WINDOWS_DRIVE_PATTERN.matcher(filename).matches()) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_FILENAME);
        }
    }

    private boolean containsControlCharacter(String filename) {
        for (int i = 0; i < filename.length(); i++) {
            if (Character.isISOControl(filename.charAt(i))) {
                return true;
            }
        }
        return false;
    }

    private void validateMd5(String fileMd5) {
        if (fileMd5 == null || !MD5_PATTERN.matcher(fileMd5).matches()) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_MD5);
        }
    }

    private String extractAllowedExtension(String filename) {
        int dotIndex = filename.lastIndexOf('.');
        if (dotIndex < 0 || dotIndex == filename.length() - 1) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_EXTENSION);
        }
        String ext = filename.substring(dotIndex + 1).toLowerCase(Locale.ROOT);
        if (!ALLOWED_EXTENSIONS.contains(ext)) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_EXTENSION);
        }
        return ext;
    }

    private String generateUploadId() {
        return "up_" + UUID.randomUUID().toString().replace("-", "");
    }

    private String buildObjectKey(Long userId, String uploadId, String ext) {
        return "raw/" + userId + "/" + uploadId + "/source." + ext;
    }
}
