package com.example.courselingo.upload;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.upload.dto.UploadChunkResponse;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import com.example.courselingo.upload.service.ChunkStagingPathResolver;
import com.example.courselingo.upload.service.ChunkStagingProperties;
import com.example.courselingo.upload.service.NoopUploadChunkStateService;
import com.example.courselingo.upload.service.UploadChunkStateService;
import com.example.courselingo.upload.service.UploadChunkService;
import com.example.courselingo.upload.service.UploadChunkServiceImpl;
import com.example.courselingo.upload.service.UploadSessionOwnerGuard;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockMultipartFile;

@ExtendWith(MockitoExtension.class)
class UploadChunkServiceTest {

    @TempDir
    private Path tempDir;

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private UploadSessionMapper uploadSessionMapper;

    @Mock
    private UploadChunkStateService chunkStateService;

    private UploadChunkService uploadChunkService;

    @BeforeEach
    void setUp() {
        ChunkStagingProperties properties = new ChunkStagingProperties(tempDir);
        uploadChunkService = new UploadChunkServiceImpl(
            currentUserService,
            new UploadSessionOwnerGuard(uploadSessionMapper),
            new ChunkStagingPathResolver(properties),
            chunkStateService
        );
    }

    @Test
    void uploadWritesPartFileAndReturnsResponse() throws Exception {
        UploadSession session = session("CREATED");
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);
        when(uploadSessionMapper.updateStatusByIdAndUserId("up_abc123", 42L, "UPLOADING")).thenReturn(1);

        UploadChunkResponse response = uploadChunkService.upload(
            "Bearer access-token",
            "up_abc123",
            0,
            chunk("original-name.mp4", bytes(8))
        );

        Path saved = tempDir.resolve("42").resolve("up_abc123").resolve("0.part");
        assertThat(Files.readAllBytes(saved)).isEqualTo(bytes(8));
        assertThat(response.uploadId()).isEqualTo("up_abc123");
        assertThat(response.chunkIndex()).isZero();
        assertThat(response.uploaded()).isTrue();
        assertThat(response.status()).isEqualTo("UPLOADING");
        assertThat(session.getStatus()).isEqualTo("UPLOADING");
        verify(uploadSessionMapper).updateStatusByIdAndUserId("up_abc123", 42L, "UPLOADING");
        verify(chunkStateService).markUploaded("up_abc123", 0);
    }

    @Test
    void uploadMarksChunkStateAfterChunkIsSaved() throws Exception {
        UploadSession session = session("UPLOADING");
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);

        uploadChunkService.upload("Bearer access-token", "up_abc123", 1, chunk("lesson.mp4", bytes(8)));

        assertThat(tempDir.resolve("42").resolve("up_abc123").resolve("1.part")).exists();
        verify(chunkStateService).markUploaded("up_abc123", 1);
    }

    @Test
    void uploadDoesNotMarkChunkStateWhenSavingChunkFails() throws Exception {
        Path regularFileAsRoot = tempDir.resolve("not-a-directory-for-state-test");
        assertThatCode(() -> Files.write(regularFileAsRoot, bytes(1))).doesNotThrowAnyException();
        UploadChunkService service = new UploadChunkServiceImpl(
            currentUserService,
            new UploadSessionOwnerGuard(uploadSessionMapper),
            new ChunkStagingPathResolver(new ChunkStagingProperties(regularFileAsRoot)),
            chunkStateService
        );
        UploadSession session = session("UPLOADING");
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);

        assertThatThrownBy(() -> service.upload("Bearer access-token", "up_abc123", 0, chunk("lesson.mp4", bytes(8))))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_CHUNK_SAVE_FAILED);
        verify(chunkStateService, never()).markUploaded(any(), anyInt());
    }

    @Test
    void uploadContinuesWhenChunkStateWriteFailsAfterLocalSave() throws Exception {
        UploadSession session = session("UPLOADING");
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);
        org.mockito.Mockito.doThrow(new IllegalStateException("redis unavailable"))
            .when(chunkStateService).markUploaded("up_abc123", 0);

        UploadChunkResponse response = uploadChunkService.upload("Bearer access-token", "up_abc123", 0, chunk("lesson.mp4", bytes(8)));

        assertThat(response.uploaded()).isTrue();
        assertThat(tempDir.resolve("42").resolve("up_abc123").resolve("0.part")).exists();
    }

    @Test
    void uploadAllowsRetryByOverwritingSameChunkFile() throws Exception {
        UploadSession session = session("UPLOADING");
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);

        uploadChunkService.upload("Bearer access-token", "up_abc123", 0, chunk("first.mp4", bytes(8)));
        uploadChunkService.upload("Bearer access-token", "up_abc123", 0, chunk("second.mp4", filledBytes(8, 9)));

        Path saved = tempDir.resolve("42").resolve("up_abc123").resolve("0.part");
        assertThat(Files.readAllBytes(saved)).isEqualTo(filledBytes(8, 9));
        verify(uploadSessionMapper, never()).updateStatusByIdAndUserId(any(), any(), any());
    }

    @Test
    void uploadUsesCurrentUserIdInsteadOfRequestProvidedOwner() throws Exception {
        UploadSession session = session("UPLOADING");
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);

        uploadChunkService.upload("Bearer access-token", "up_abc123", 0, chunk("lesson.mp4", bytes(8)));

        assertThat(tempDir.resolve("42").resolve("up_abc123").resolve("0.part")).exists();
        assertThat(tempDir.resolve("99").resolve("up_abc123").resolve("0.part")).doesNotExist();
    }

    @Test
    void uploadRejectsSessionOwnedByAnotherUser() {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(null);

        assertThatThrownBy(() -> uploadChunkService.upload("Bearer access-token", "up_abc123", 0, chunk("lesson.mp4", bytes(8))))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_NOT_FOUND);
        assertThat(tempDir.resolve("42").resolve("up_abc123").resolve("0.part")).doesNotExist();
        verify(uploadSessionMapper, never()).updateStatusByIdAndUserId(any(), any(), any());
        verify(uploadSessionMapper, never()).updateById(any(UploadSession.class));
    }

    @Test
    void uploadRejectsMissingSession() {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_missing", 42L)).thenReturn(null);

        assertThatThrownBy(() -> uploadChunkService.upload("Bearer access-token", "up_missing", 0, chunk("lesson.mp4", bytes(8))))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_NOT_FOUND);
    }

    @Test
    void uploadKeepsUploadingStatusAfterSuccessfulUpload() {
        UploadSession session = session("UPLOADING");
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);

        UploadChunkResponse response = uploadChunkService.upload("Bearer access-token", "up_abc123", 0, chunk("lesson.mp4", bytes(8)));

        assertThat(response.status()).isEqualTo("UPLOADING");
        assertThat(session.getStatus()).isEqualTo("UPLOADING");
        verify(uploadSessionMapper, never()).updateStatusByIdAndUserId(any(), any(), any());
    }

    @Test
    void uploadRejectsTerminalOrInvalidStatuses() {
        for (String status : new String[] {"MERGING", "COMPLETED", "FAILED", "CANCELLED"}) {
            UploadSession session = session(status);
            when(currentUserService.currentUser("Bearer access-token"))
                .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
            when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);

            assertThatThrownBy(() -> uploadChunkService.upload("Bearer access-token", "up_abc123", 0, chunk("lesson.mp4", bytes(8))))
                .isInstanceOf(BusinessException.class)
                .extracting("errorCode")
                .isEqualTo(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);
        }
    }

    @Test
    void uploadRejectsNonLastChunkWhenSizeDoesNotEqualChunkSize() {
        UploadSession session = session("UPLOADING");
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);

        assertThatThrownBy(() -> uploadChunkService.upload("Bearer access-token", "up_abc123", 0, chunk("lesson.mp4", bytes(7))))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_CHUNK);
    }

    @Test
    void uploadRequiresLastChunkSizeToEqualRemainingBytes() {
        UploadSession session = session("UPLOADING");
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);

        UploadChunkResponse response = uploadChunkService.upload("Bearer access-token", "up_abc123", 2, chunk("lesson.mp4", bytes(4)));

        assertThat(response.chunkIndex()).isEqualTo(2);
        assertThat(tempDir.resolve("42").resolve("up_abc123").resolve("2.part")).exists();
    }

    @Test
    void uploadRejectsLastChunkWhenSizeDoesNotEqualRemainingBytes() {
        UploadSession session = session("UPLOADING");
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);

        assertThatThrownBy(() -> uploadChunkService.upload("Bearer access-token", "up_abc123", 2, chunk("lesson.mp4", bytes(5))))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_CHUNK);
    }

    @Test
    void uploadRejectsChunkIndexOutsideSessionRange() {
        UploadSession session = session("UPLOADING");
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);

        assertThatThrownBy(() -> uploadChunkService.upload("Bearer access-token", "up_abc123", 3, chunk("lesson.mp4", bytes(8))))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_CHUNK);
    }

    @Test
    void uploadPathDoesNotUseOriginalFilenameOrObjectKeyAndStaysUnderStagingDir() {
        UploadSession session = session("UPLOADING");
        session.setObjectKey("raw/42/up_abc123/source.mp4");
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);

        uploadChunkService.upload("Bearer access-token", "up_abc123", 0, chunk("evil\\name.mp4", bytes(8)));

        Path saved = tempDir.resolve("42").resolve("up_abc123").resolve("0.part");
        assertThat(saved).exists();
        assertThat(saved.normalize()).startsWith(tempDir.normalize());
        assertThat(saved.toString()).doesNotContain("evil");
        assertThat(saved.toString()).doesNotContain("source.mp4");
        assertThat(saved.toString()).doesNotContain("raw");
    }

    @Test
    void uploadRejectsInvalidUploadIdFormat() {
        assertThatThrownBy(() -> uploadChunkService.upload("Bearer access-token", "../bad", 0, chunk("lesson.mp4", bytes(8))))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_NOT_FOUND);
    }

    @Test
    void uploadWrapsSaveFailure() {
        Path regularFileAsRoot = tempDir.resolve("not-a-directory");
        assertThatCode(() -> Files.write(regularFileAsRoot, bytes(1))).doesNotThrowAnyException();
        UploadChunkService service = new UploadChunkServiceImpl(
            currentUserService,
            new UploadSessionOwnerGuard(uploadSessionMapper),
            new ChunkStagingPathResolver(new ChunkStagingProperties(regularFileAsRoot)),
            new NoopUploadChunkStateService()
        );
        UploadSession session = session("UPLOADING");
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);

        assertThatThrownBy(() -> service.upload("Bearer access-token", "up_abc123", 0, chunk("lesson.mp4", bytes(8))))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_CHUNK_SAVE_FAILED);
    }

    @Test
    void uploadUpdatesCreatedSessionToUploadingAfterSavingChunk() {
        UploadSession session = session("CREATED");
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);
        when(uploadSessionMapper.updateStatusByIdAndUserId("up_abc123", 42L, "UPLOADING")).thenReturn(1);

        uploadChunkService.upload("Bearer access-token", "up_abc123", 0, chunk("lesson.mp4", bytes(8)));

        verify(uploadSessionMapper).updateStatusByIdAndUserId("up_abc123", 42L, "UPLOADING");
        assertThat(session.getStatus()).isEqualTo("UPLOADING");
    }

    private static UploadSession session(String status) {
        UploadSession session = new UploadSession();
        session.setId("up_abc123");
        session.setUserId(42L);
        session.setFilename("lesson.mp4");
        session.setExt("mp4");
        session.setTotalChunks(3);
        session.setChunkSizeBytes(8L);
        session.setSizeBytes(20L);
        session.setFileMd5("d41d8cd98f00b204e9800998ecf8427e");
        session.setStatus(status);
        session.setStorageType("MINIO");
        session.setObjectKey("raw/42/up_abc123/source.mp4");
        return session;
    }

    private static MockMultipartFile chunk(String originalFilename, byte[] content) {
        return new MockMultipartFile("file", originalFilename, "application/octet-stream", content);
    }

    private static byte[] bytes(int size) {
        byte[] content = new byte[size];
        for (int i = 0; i < size; i++) {
            content[i] = (byte) i;
        }
        return content;
    }

    private static byte[] filledBytes(int size, int value) {
        byte[] content = new byte[size];
        for (int i = 0; i < size; i++) {
            content[i] = (byte) value;
        }
        return content;
    }
}
