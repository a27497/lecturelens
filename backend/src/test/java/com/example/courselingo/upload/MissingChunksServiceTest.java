package com.example.courselingo.upload;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.upload.dto.MissingChunksResponse;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import com.example.courselingo.upload.service.ChunkStagingPathResolver;
import com.example.courselingo.upload.service.ChunkStagingProperties;
import com.example.courselingo.upload.service.MissingChunksService;
import com.example.courselingo.upload.service.MissingChunksServiceImpl;
import com.example.courselingo.upload.service.UploadChunkStateService;
import com.example.courselingo.upload.service.UploadSessionOwnerGuard;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class MissingChunksServiceTest {

    @TempDir
    private Path tempDir;

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private UploadSessionMapper uploadSessionMapper;

    @Mock
    private UploadChunkStateService chunkStateService;

    private MissingChunksService missingChunksService;

    @BeforeEach
    void setUp() {
        missingChunksService = new MissingChunksServiceImpl(
            currentUserService,
            new UploadSessionOwnerGuard(uploadSessionMapper),
            new ChunkStagingPathResolver(new ChunkStagingProperties(tempDir)),
            chunkStateService
        );
    }

    @Test
    void missingChunksReturnsAllIndexesWhenSessionDirectoryDoesNotExist() {
        stubCurrentUserAndSession(session("CREATED", 5));
        when(chunkStateService.findUploadedChunks("up_abc123", 5)).thenReturn(Optional.empty());

        MissingChunksResponse response = missingChunksService.findMissingChunks("Bearer access-token", "up_abc123");

        assertThat(response.uploadId()).isEqualTo("up_abc123");
        assertThat(response.totalChunks()).isEqualTo(5);
        assertThat(response.uploadedChunks()).isEmpty();
        assertThat(response.missingChunks()).containsExactly(0, 1, 2, 3, 4);
        assertThat(response.allUploaded()).isFalse();
        assertThat(response.status()).isEqualTo("CREATED");
    }

    @Test
    void missingChunksReturnsUploadedAndMissingIndexesInAscendingOrder() throws Exception {
        stubCurrentUserAndSession(session("UPLOADING", 5));
        when(chunkStateService.findUploadedChunks("up_abc123", 5)).thenReturn(Optional.empty());
        Path dir = sessionDirectory();
        Files.createDirectories(dir);
        Files.write(dir.resolve("2.part"), new byte[] {2});
        Files.write(dir.resolve("0.part"), new byte[] {0});
        Files.write(dir.resolve("4.part"), new byte[] {4});

        MissingChunksResponse response = missingChunksService.findMissingChunks("Bearer access-token", "up_abc123");

        assertThat(response.uploadedChunks()).containsExactly(0, 2, 4);
        assertThat(response.missingChunks()).containsExactly(1, 3);
        assertThat(response.allUploaded()).isFalse();
    }

    @Test
    void missingChunksIgnoresNonNumericAndOutOfRangePartFiles() throws Exception {
        stubCurrentUserAndSession(session("UPLOADING", 3));
        when(chunkStateService.findUploadedChunks("up_abc123", 3)).thenReturn(Optional.empty());
        Path dir = sessionDirectory();
        Files.createDirectories(dir);
        Files.write(dir.resolve("0.part"), new byte[] {0});
        Files.write(dir.resolve("abc.part"), new byte[] {1});
        Files.write(dir.resolve("1.tmp"), new byte[] {1});
        Files.write(dir.resolve("999.part"), new byte[] {1});
        Files.write(dir.resolve("-1.part"), new byte[] {1});

        MissingChunksResponse response = missingChunksService.findMissingChunks("Bearer access-token", "up_abc123");

        assertThat(response.uploadedChunks()).containsExactly(0);
        assertThat(response.missingChunks()).containsExactly(1, 2);
    }

    @Test
    void missingChunksSetsAllUploadedTrueWhenEveryChunkExists() throws Exception {
        stubCurrentUserAndSession(session("COMPLETED", 3));
        when(chunkStateService.findUploadedChunks("up_abc123", 3)).thenReturn(Optional.empty());
        Path dir = sessionDirectory();
        Files.createDirectories(dir);
        Files.write(dir.resolve("0.part"), new byte[] {0});
        Files.write(dir.resolve("1.part"), new byte[] {1});
        Files.write(dir.resolve("2.part"), new byte[] {2});

        MissingChunksResponse response = missingChunksService.findMissingChunks("Bearer access-token", "up_abc123");

        assertThat(response.uploadedChunks()).containsExactly(0, 1, 2);
        assertThat(response.missingChunks()).isEmpty();
        assertThat(response.allUploaded()).isTrue();
        assertThat(response.status()).isEqualTo("COMPLETED");
        verify(uploadSessionMapper, never()).updateStatusByIdAndUserId(any(), any(), any());
    }

    @Test
    void missingChunksRejectsSessionOwnedByAnotherUser() {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(null);

        assertThatThrownBy(() -> missingChunksService.findMissingChunks("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_NOT_FOUND);
        assertThat(tempDir.resolve("99").resolve("up_abc123")).doesNotExist();
    }

    @Test
    void missingChunksRejectsMissingSession() {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_missing", 42L)).thenReturn(null);

        assertThatThrownBy(() -> missingChunksService.findMissingChunks("Bearer access-token", "up_missing"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_NOT_FOUND);
    }

    @Test
    void missingChunksRejectsInvalidUploadIdBeforePathResolution() {
        assertThatThrownBy(() -> missingChunksService.findMissingChunks("Bearer access-token", "../bad"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_SESSION_ID);
    }

    @Test
    void missingChunksReadsOnlyConfiguredStagingDirectory() throws Exception {
        stubCurrentUserAndSession(session("UPLOADING", 2));
        when(chunkStateService.findUploadedChunks("up_abc123", 2)).thenReturn(Optional.empty());
        Path configuredDir = sessionDirectory();
        Files.createDirectories(configuredDir);
        Files.write(configuredDir.resolve("0.part"), new byte[] {0});
        Path outsideDir = tempDir.resolve("outside").resolve("42").resolve("up_abc123");
        Files.createDirectories(outsideDir);
        Files.write(outsideDir.resolve("1.part"), new byte[] {1});

        MissingChunksResponse response = missingChunksService.findMissingChunks("Bearer access-token", "up_abc123");

        assertThat(response.uploadedChunks()).containsExactly(0);
        assertThat(response.missingChunks()).containsExactly(1);
    }

    @Test
    void missingChunksResponseDoesNotExposeObjectKeyLocalPathOrUserId() throws Exception {
        stubCurrentUserAndSession(session("UPLOADING", 1));
        when(chunkStateService.findUploadedChunks("up_abc123", 1)).thenReturn(Optional.empty());
        Path dir = sessionDirectory();
        Files.createDirectories(dir);
        Files.write(dir.resolve("0.part"), new byte[] {0});

        MissingChunksResponse response = missingChunksService.findMissingChunks("Bearer access-token", "up_abc123");

        assertThat(response.getClass().getRecordComponents())
            .extracting(java.lang.reflect.RecordComponent::getName)
            .containsExactly("uploadId", "totalChunks", "uploadedChunks", "missingChunks", "allUploaded", "status");
    }

    @Test
    void missingChunksUsesRedisStateWhenKeyExists() throws Exception {
        stubCurrentUserAndSession(session("UPLOADING", 5));
        when(chunkStateService.findUploadedChunks("up_abc123", 5)).thenReturn(Optional.of(List.of(0, 2, 4)));
        Path dir = sessionDirectory();
        Files.createDirectories(dir);
        Files.write(dir.resolve("1.part"), new byte[] {1});

        MissingChunksResponse response = missingChunksService.findMissingChunks("Bearer access-token", "up_abc123");

        assertThat(response.uploadedChunks()).containsExactly(0, 2, 4);
        assertThat(response.missingChunks()).containsExactly(1, 3);
    }

    @Test
    void missingChunksFallsBackToStagingWhenRedisKeyDoesNotExist() throws Exception {
        stubCurrentUserAndSession(session("UPLOADING", 3));
        when(chunkStateService.findUploadedChunks("up_abc123", 3)).thenReturn(Optional.empty());
        Path dir = sessionDirectory();
        Files.createDirectories(dir);
        Files.write(dir.resolve("0.part"), new byte[] {0});

        MissingChunksResponse response = missingChunksService.findMissingChunks("Bearer access-token", "up_abc123");

        assertThat(response.uploadedChunks()).containsExactly(0);
        assertThat(response.missingChunks()).containsExactly(1, 2);
    }

    @Test
    void missingChunksFallsBackToStagingWhenRedisReadFails() throws Exception {
        stubCurrentUserAndSession(session("UPLOADING", 3));
        when(chunkStateService.findUploadedChunks("up_abc123", 3))
            .thenThrow(new IllegalStateException("redis unavailable"));
        Path dir = sessionDirectory();
        Files.createDirectories(dir);
        Files.write(dir.resolve("1.part"), new byte[] {1});

        MissingChunksResponse response = missingChunksService.findMissingChunks("Bearer access-token", "up_abc123");

        assertThat(response.uploadedChunks()).containsExactly(1);
        assertThat(response.missingChunks()).containsExactly(0, 2);
    }

    private void stubCurrentUserAndSession(UploadSession session) {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);
    }

    private Path sessionDirectory() {
        return tempDir.resolve("42").resolve("up_abc123");
    }

    private static UploadSession session(String status, int totalChunks) {
        UploadSession session = new UploadSession();
        session.setId("up_abc123");
        session.setUserId(42L);
        session.setFilename("lesson.mp4");
        session.setExt("mp4");
        session.setTotalChunks(totalChunks);
        session.setChunkSizeBytes(8L);
        session.setSizeBytes(8L * totalChunks);
        session.setFileMd5("d41d8cd98f00b204e9800998ecf8427e");
        session.setStatus(status);
        session.setStorageType("MINIO");
        session.setObjectKey("raw/42/up_abc123/source.mp4");
        return session;
    }
}
