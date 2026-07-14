package com.example.courselingo.upload;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.upload.dto.CreateUploadSessionRequest;
import com.example.courselingo.upload.dto.CreateUploadSessionResponse;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import com.example.courselingo.upload.service.UploadSessionService;
import com.example.courselingo.upload.service.UploadSessionServiceImpl;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class UploadSessionServiceTest {

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private UploadSessionMapper uploadSessionMapper;

    private UploadSessionService uploadSessionService;

    @BeforeEach
    void setUp() {
        uploadSessionService = new UploadSessionServiceImpl(currentUserService, uploadSessionMapper);
    }

    @Test
    void createWritesUploadSessionUsingCurrentUserAndReturnsUploadId() {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.insert(any(UploadSession.class))).thenReturn(1);

        CreateUploadSessionResponse response = uploadSessionService.create("Bearer access-token", validRequest());

        ArgumentCaptor<UploadSession> captor = ArgumentCaptor.forClass(UploadSession.class);
        verify(uploadSessionMapper).insert(captor.capture());
        UploadSession saved = captor.getValue();

        assertThat(response.uploadId()).isEqualTo(saved.getId());
        assertThat(response.status()).isEqualTo("CREATED");
        assertThat(saved.getId()).startsWith("up_");
        assertThat(saved.getUserId()).isEqualTo(42L);
        assertThat(saved.getFilename()).isEqualTo("Lesson-01.MP4");
        assertThat(saved.getExt()).isEqualTo("mp4");
        assertThat(saved.getTotalChunks()).isEqualTo(100);
        assertThat(saved.getChunkSizeBytes()).isEqualTo(5_242_880L);
        assertThat(saved.getSizeBytes()).isEqualTo(524_288_000L);
        assertThat(saved.getFileMd5()).isEqualTo("d41d8cd98f00b204e9800998ecf8427e");
        assertThat(saved.getStatus()).isEqualTo("CREATED");
        assertThat(saved.getStorageType()).isEqualTo("MINIO");
        assertThat(saved.getObjectKey()).isEqualTo("raw/42/" + saved.getId() + "/source.mp4");
        assertThat(saved.getObjectKey()).doesNotContain("Lesson-01");
        assertThat(saved.getObjectKey()).doesNotContain("\\");
        assertThat(saved.getCreatedAt()).isNull();
        assertThat(saved.getUpdatedAt()).isNull();
    }

    @Test
    void createNormalizesUppercaseMd5ToLowercase() {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.insert(any(UploadSession.class))).thenReturn(1);
        CreateUploadSessionRequest request = new CreateUploadSessionRequest(
            "lesson-01.webm",
            524_288_000L,
            5_242_880L,
            100,
            "D41D8CD98F00B204E9800998ECF8427E"
        );

        uploadSessionService.create("Bearer access-token", request);

        ArgumentCaptor<UploadSession> captor = ArgumentCaptor.forClass(UploadSession.class);
        verify(uploadSessionMapper).insert(captor.capture());
        assertThat(captor.getValue().getFileMd5()).isEqualTo("d41d8cd98f00b204e9800998ecf8427e");
    }

    @Test
    void createRejectsUnsupportedExtension() {
        assertThatThrownBy(() -> uploadSessionService.create("Bearer access-token", requestWithFilename("lesson-01.exe")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_EXTENSION);
    }

    @Test
    void createRejectsFilenameWithoutExtension() {
        assertThatThrownBy(() -> uploadSessionService.create("Bearer access-token", requestWithFilename("lesson-01")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_EXTENSION);
    }

    @Test
    void createRejectsFilenameContainingSlash() {
        assertThatThrownBy(() -> uploadSessionService.create("Bearer access-token", requestWithFilename("course/lesson-01.mp4")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_FILENAME);
    }

    @Test
    void createRejectsFilenameContainingBackslash() {
        assertThatThrownBy(() -> uploadSessionService.create("Bearer access-token", requestWithFilename("course\\lesson-01.mp4")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_FILENAME);
    }

    @Test
    void createRejectsParentDirectoryTraversalWithSlash() {
        assertThatThrownBy(() -> uploadSessionService.create("Bearer access-token", requestWithFilename("../lesson-01.mp4")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_FILENAME);
    }

    @Test
    void createRejectsParentDirectoryTraversalWithBackslash() {
        assertThatThrownBy(() -> uploadSessionService.create("Bearer access-token", requestWithFilename("..\\lesson-01.mp4")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_FILENAME);
    }

    @Test
    void createRejectsWindowsDriveStyleFilename() {
        assertThatThrownBy(() -> uploadSessionService.create("Bearer access-token", requestWithFilename("C:\\lesson-01.mp4")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_FILENAME);
    }

    @Test
    void createRejectsUnixAbsolutePathFilename() {
        assertThatThrownBy(() -> uploadSessionService.create("Bearer access-token", requestWithFilename("/tmp/lesson-01.mp4")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_FILENAME);
    }

    @Test
    void createRejectsFilenameContainingControlCharacter() {
        assertThatThrownBy(() -> uploadSessionService.create("Bearer access-token", requestWithFilename("lesson-\u0001.mp4")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_FILENAME);
    }

    @Test
    void createAcceptsSafeFilenameAfterB11Hardening() {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.insert(any(UploadSession.class))).thenReturn(1);

        CreateUploadSessionResponse response = uploadSessionService.create(
            "Bearer access-token",
            requestWithFilename("lesson_01-final.webm")
        );

        assertThat(response.status()).isEqualTo("CREATED");
    }

    @Test
    void createRejectsInvalidMd5() {
        CreateUploadSessionRequest request = new CreateUploadSessionRequest(
            "lesson-01.mp4",
            524_288_000L,
            5_242_880L,
            100,
            "not-md5"
        );

        assertThatThrownBy(() -> uploadSessionService.create("Bearer access-token", request))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_MD5);
    }

    @Test
    void createRejectsNonPositiveChunkArguments() {
        CreateUploadSessionRequest request = new CreateUploadSessionRequest(
            "lesson-01.mp4",
            524_288_000L,
            0L,
            100,
            "d41d8cd98f00b204e9800998ecf8427e"
        );

        assertThatThrownBy(() -> uploadSessionService.create("Bearer access-token", request))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_CHUNK);
    }

    @Test
    void createWrapsMapperFailureAsUploadSessionCreateFailed() {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.insert(any(UploadSession.class))).thenReturn(0);

        assertThatThrownBy(() -> uploadSessionService.create("Bearer access-token", validRequest()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_CREATE_FAILED);
    }

    private CreateUploadSessionRequest validRequest() {
        return new CreateUploadSessionRequest(
            "Lesson-01.MP4",
            524_288_000L,
            5_242_880L,
            100,
            "d41d8cd98f00b204e9800998ecf8427e"
        );
    }

    private CreateUploadSessionRequest requestWithFilename(String filename) {
        return new CreateUploadSessionRequest(
            filename,
            524_288_000L,
            5_242_880L,
            100,
            "d41d8cd98f00b204e9800998ecf8427e"
        );
    }
}
