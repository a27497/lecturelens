package com.example.courselingo.upload.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class UploadSessionOwnerGuard {

    private static final Pattern UPLOAD_ID_PATTERN = Pattern.compile("^up_[A-Za-z0-9_-]+$");

    private final UploadSessionMapper uploadSessionMapper;

    public UploadSessionOwnerGuard(UploadSessionMapper uploadSessionMapper) {
        this.uploadSessionMapper = uploadSessionMapper;
    }

    public UploadSession requireOwner(String uploadId, Long currentUserId) {
        validateScope(uploadId, currentUserId);
        UploadSession uploadSession = uploadSessionMapper.selectByIdAndUserId(uploadId, currentUserId);
        if (uploadSession == null) {
            throw new BusinessException(ErrorCode.UPLOAD_SESSION_NOT_FOUND);
        }
        return uploadSession;
    }

    public void updateStatus(String uploadId, Long currentUserId, String status) {
        validateScope(uploadId, currentUserId);
        if (status == null || status.isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        int updated = uploadSessionMapper.updateStatusByIdAndUserId(uploadId, currentUserId, status);
        if (updated != 1) {
            throw new BusinessException(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);
        }
    }

    private void validateScope(String uploadId, Long currentUserId) {
        if (uploadId == null || !UPLOAD_ID_PATTERN.matcher(uploadId).matches()) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_SESSION_ID);
        }
        if (currentUserId == null || currentUserId <= 0) {
            throw new BusinessException(ErrorCode.COMMON_UNAUTHORIZED);
        }
    }
}
