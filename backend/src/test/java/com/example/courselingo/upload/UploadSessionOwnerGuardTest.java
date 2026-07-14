package com.example.courselingo.upload;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import com.example.courselingo.upload.service.UploadSessionOwnerGuard;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class UploadSessionOwnerGuardTest {

    @Mock
    private UploadSessionMapper uploadSessionMapper;

    private UploadSessionOwnerGuard ownerGuard;

    @BeforeEach
    void setUp() {
        ownerGuard = new UploadSessionOwnerGuard(uploadSessionMapper);
    }

    @Test
    void requireOwnerLoadsSessionWithUploadIdAndCurrentUserIdScope() {
        UploadSession session = session();
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);

        UploadSession result = ownerGuard.requireOwner("up_abc123", 42L);

        assertThat(result).isSameAs(session);
        verify(uploadSessionMapper).selectByIdAndUserId("up_abc123", 42L);
        verify(uploadSessionMapper, never()).selectById("up_abc123");
    }

    @Test
    void requireOwnerUsesNotFoundForMissingOrOtherOwnerSession() {
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(null);

        assertThatThrownBy(() -> ownerGuard.requireOwner("up_abc123", 42L))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_NOT_FOUND);
    }

    @Test
    void requireOwnerRejectsInvalidScopeBeforeMapperAccess() {
        assertThatThrownBy(() -> ownerGuard.requireOwner("../up_abc123", 42L))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_SESSION_ID);
        assertThatThrownBy(() -> ownerGuard.requireOwner("up_abc123", null))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_UNAUTHORIZED);
        assertThatThrownBy(() -> ownerGuard.requireOwner("up_abc123", 0L))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_UNAUTHORIZED);

        verify(uploadSessionMapper, never()).selectByIdAndUserId(any(), any());
    }

    @Test
    void updateStatusScopesUpdateByUploadIdAndCurrentUserId() {
        when(uploadSessionMapper.updateStatusByIdAndUserId("up_abc123", 42L, "UPLOADING")).thenReturn(1);

        ownerGuard.updateStatus("up_abc123", 42L, "UPLOADING");

        verify(uploadSessionMapper).updateStatusByIdAndUserId("up_abc123", 42L, "UPLOADING");
    }

    @Test
    void updateStatusFailsWhenNoOwnedRowWasUpdated() {
        when(uploadSessionMapper.updateStatusByIdAndUserId("up_abc123", 42L, "UPLOADED")).thenReturn(0);

        assertThatThrownBy(() -> ownerGuard.updateStatus("up_abc123", 42L, "UPLOADED"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);
    }

    @Test
    void updateStatusRejectsInvalidScopeBeforeMapperAccess() {
        assertThatThrownBy(() -> ownerGuard.updateStatus("up_abc123/other", 42L, "UPLOADED"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_SESSION_ID);
        assertThatThrownBy(() -> ownerGuard.updateStatus("up_abc123", -1L, "UPLOADED"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_UNAUTHORIZED);
        assertThatThrownBy(() -> ownerGuard.updateStatus("up_abc123", 42L, " "))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);

        verify(uploadSessionMapper, never()).updateStatusByIdAndUserId(any(), any(), any());
    }

    private static UploadSession session() {
        UploadSession session = new UploadSession();
        session.setId("up_abc123");
        session.setUserId(42L);
        return session;
    }
}
