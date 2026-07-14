package com.example.courselingo.upload;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.upload.dto.CompleteUploadResponse;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import com.example.courselingo.upload.service.BasicVideoHeaderValidator;
import com.example.courselingo.upload.service.ChunkStagingPathResolver;
import com.example.courselingo.upload.service.ChunkStagingProperties;
import com.example.courselingo.upload.service.CompleteUploadService;
import com.example.courselingo.upload.service.CompleteUploadServiceImpl;
import com.example.courselingo.upload.service.UploadChunkStateService;
import com.example.courselingo.upload.service.UploadSessionOwnerGuard;
import java.io.ByteArrayOutputStream;
import java.lang.reflect.RecordComponent;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CompleteUploadServiceTest {

    private static final byte[] VALID_MP4 = concat(
        new byte[] {0, 0, 0, 16, 'f', 't', 'y', 'p', 'i', 's', 'o', 'm', 0, 0, 0, 1},
        "payload".getBytes(java.nio.charset.StandardCharsets.UTF_8)
    );
    private static final String VALID_MD5 = md5Hex(VALID_MP4);

    @TempDir
    private Path tempDir;

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private UploadSessionMapper uploadSessionMapper;

    @Mock
    private UploadChunkStateService chunkStateService;

    @Mock
    private StorageService storageService;

    private CompleteUploadService completeUploadService;

    @BeforeEach
    void setUp() {
        completeUploadService = new CompleteUploadServiceImpl(
            currentUserService,
            new UploadSessionOwnerGuard(uploadSessionMapper),
            new ChunkStagingPathResolver(new ChunkStagingProperties(tempDir)),
            new BasicVideoHeaderValidator(),
            chunkStateService,
            storageService
        );
    }

    @Test
    void completeMergesChunksInIndexOrderAndReturnsResponse() throws Exception {
        UploadSession session = session("UPLOADING", "mp4", 3, (long) VALID_MP4.length, VALID_MD5);
        stubCurrentUserAndSession(session);
        when(uploadSessionMapper.updateStatusByIdAndUserId("up_abc123", 42L, "STORED")).thenReturn(1);
        writeChunksOutOfOrder(VALID_MP4);

        CompleteUploadResponse response = completeUploadService.complete("Bearer access-token", "up_abc123");

        Path assembled = assembledPath();
        assertThat(Files.readAllBytes(assembled)).isEqualTo(VALID_MP4);
        assertThat(assembled.normalize()).startsWith(tempDir.normalize());
        assertThat(response.uploadId()).isEqualTo("up_abc123");
        assertThat(response.status()).isEqualTo("STORED");
        assertThat(response.sizeBytes()).isEqualTo((long) VALID_MP4.length);
        assertThat(response.fileMd5()).isEqualTo(VALID_MD5);
        verify(chunkStateService).clear("up_abc123");
        verify(storageService).putObject(
            eq("raw/42/up_abc123/source.mp4"),
            eq(assembled),
            eq((long) VALID_MP4.length),
            eq("video/mp4")
        );
    }

    @Test
    void completeUpdatesSessionStatusToStoredOnlyAfterStoragePutWithoutChangingObjectKey() throws Exception {
        UploadSession session = session("CREATED", "mp4", 3, (long) VALID_MP4.length, VALID_MD5);
        stubCurrentUserAndSession(session);
        when(uploadSessionMapper.updateStatusByIdAndUserId("up_abc123", 42L, "STORED")).thenReturn(1);
        writeValidChunks();

        completeUploadService.complete("Bearer access-token", "up_abc123");

        InOrder persistenceOrder = org.mockito.Mockito.inOrder(storageService, uploadSessionMapper);
        persistenceOrder.verify(storageService).putObject(
            eq(session.getObjectKey()),
            any(Path.class),
            eq((long) VALID_MP4.length),
            eq("video/mp4")
        );
        persistenceOrder.verify(uploadSessionMapper).updateStatusByIdAndUserId("up_abc123", 42L, "STORED");
        verify(uploadSessionMapper, never()).updateById(any(UploadSession.class));
        assertThat(session.getStatus()).isEqualTo("STORED");
        assertThat(session.getObjectKey()).isEqualTo("raw/42/up_abc123/source.mp4");
    }

    @Test
    void storagePutFailurePreservesFilesStateAndDoesNotReportCompletion() throws Exception {
        UploadSession session = session("UPLOADING", "mp4", 3, (long) VALID_MP4.length, VALID_MD5);
        stubCurrentUserAndSession(session);
        writeValidChunks();
        doThrow(new BusinessException(ErrorCode.STORAGE_OPERATION_FAILED))
            .when(storageService).putObject(eq(session.getObjectKey()), any(Path.class), eq((long) VALID_MP4.length), eq("video/mp4"));

        assertThatThrownBy(() -> completeUploadService.complete("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> assertThat(error.getMessage()).doesNotContain(session.getObjectKey()));

        assertThat(session.getStatus()).isEqualTo("UPLOADING");
        assertThat(assembledPath()).exists();
        assertThat(sessionDirectory().resolve("0.part")).exists();
        verify(uploadSessionMapper, never()).updateStatusByIdAndUserId(any(), any(), any());
        verify(chunkStateService, never()).clear(any());
    }

    @Test
    void completeRejectsMissingSession() {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_missing", 42L)).thenReturn(null);

        assertThatThrownBy(() -> completeUploadService.complete("Bearer access-token", "up_missing"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_NOT_FOUND);
    }

    @Test
    void completeRejectsSessionOwnedByAnotherUserWithoutUpdatingStatusOrWritingAssembledFile() throws Exception {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(null);
        Path assembled = assembledPath();

        assertThatThrownBy(() -> completeUploadService.complete("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_NOT_FOUND);
        verify(uploadSessionMapper, never()).updateStatusByIdAndUserId(any(), any(), any());
        verify(uploadSessionMapper, never()).updateById(any(UploadSession.class));
        assertThat(assembled).doesNotExist();
    }

    @Test
    void completeRejectsSessionOwnedByAnotherUserWithoutOverwritingExistingAssembledFile() throws Exception {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(null);
        Path assembled = assembledPath();
        Files.createDirectories(assembled.getParent());
        byte[] existingContent = "existing owner file".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        Files.write(assembled, existingContent);

        assertThatThrownBy(() -> completeUploadService.complete("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_NOT_FOUND);

        assertThat(Files.readAllBytes(assembled)).isEqualTo(existingContent);
        verify(uploadSessionMapper, never()).updateStatusByIdAndUserId(any(), any(), any());
    }

    @Test
    void completeRejectsInvalidUploadIdFormat() {
        assertThatThrownBy(() -> completeUploadService.complete("Bearer access-token", "../bad"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_SESSION_ID);
    }

    @Test
    void completeFailsWhenSessionDirectoryDoesNotExist() {
        UploadSession session = session("UPLOADING", "mp4", 3, (long) VALID_MP4.length, VALID_MD5);
        stubCurrentUserAndSession(session);

        assertThatThrownBy(() -> completeUploadService.complete("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_CHUNK_MISSING);
        verify(uploadSessionMapper, never()).updateStatusByIdAndUserId(any(), any(), any());
    }

    @Test
    void completeFailsWhenAnyChunkIsMissing() throws Exception {
        UploadSession session = session("UPLOADING", "mp4", 3, (long) VALID_MP4.length, VALID_MD5);
        stubCurrentUserAndSession(session);
        writeChunk(0, "AAAA");
        writeChunk(2, "CCCC");

        assertThatThrownBy(() -> completeUploadService.complete("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("missingChunks=[1]")
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_CHUNK_MISSING);
        verify(uploadSessionMapper, never()).updateStatusByIdAndUserId(any(), any(), any());
    }

    @Test
    void completeFailsWhenAssembledSizeDoesNotMatchSessionSize() throws Exception {
        UploadSession session = session("UPLOADING", "mp4", 3, VALID_MP4.length + 1L, VALID_MD5);
        stubCurrentUserAndSession(session);
        writeValidChunks();

        assertThatThrownBy(() -> completeUploadService.complete("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_ASSEMBLED_SIZE_MISMATCH);
        verify(uploadSessionMapper, never()).updateStatusByIdAndUserId(any(), any(), any());
    }

    @Test
    void completeFailsWhenAssembledMd5DoesNotMatchSessionMd5() throws Exception {
        UploadSession session = session("UPLOADING", "mp4", 3, (long) VALID_MP4.length, "00000000000000000000000000000000");
        stubCurrentUserAndSession(session);
        writeValidChunks();

        assertThatThrownBy(() -> completeUploadService.complete("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_ASSEMBLED_MD5_MISMATCH);
        verify(uploadSessionMapper, never()).updateStatusByIdAndUserId(any(), any(), any());
    }

    @Test
    void completeRejectsRepeatedComplete() throws Exception {
        UploadSession session = session("UPLOADED", "mp4", 3, (long) VALID_MP4.length, VALID_MD5);
        stubCurrentUserAndSession(session);
        writeValidChunks();

        assertThatThrownBy(() -> completeUploadService.complete("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);
        verify(uploadSessionMapper, never()).updateStatusByIdAndUserId(any(), any(), any());
    }

    @Test
    void completeRejectsIllegalStatuses() throws Exception {
        for (String status : new String[] {"MERGING", "COMPLETED", "FAILED", "CANCELLED"}) {
            UploadSession session = session(status, "mp4", 3, (long) VALID_MP4.length, VALID_MD5);
            stubCurrentUserAndSession(session);
            writeValidChunks();

            assertThatThrownBy(() -> completeUploadService.complete("Bearer access-token", "up_abc123"))
                .isInstanceOf(BusinessException.class)
                .extracting("errorCode")
                .isEqualTo(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);
        }
    }

    @Test
    void completeResponseDoesNotExposeObjectKeyLocalPathOrUserId() throws Exception {
        UploadSession session = session("UPLOADING", "mp4", 3, (long) VALID_MP4.length, VALID_MD5);
        stubCurrentUserAndSession(session);
        when(uploadSessionMapper.updateStatusByIdAndUserId("up_abc123", 42L, "STORED")).thenReturn(1);
        writeValidChunks();

        CompleteUploadResponse response = completeUploadService.complete("Bearer access-token", "up_abc123");

        assertThat(response.getClass().getRecordComponents())
            .extracting(RecordComponent::getName)
            .containsExactly("uploadId", "status", "sizeBytes", "fileMd5");
    }

    @Test
    void completeKeepsSourceChunksAfterSuccessfulMerge() throws Exception {
        UploadSession session = session("UPLOADING", "mp4", 3, (long) VALID_MP4.length, VALID_MD5);
        stubCurrentUserAndSession(session);
        when(uploadSessionMapper.updateStatusByIdAndUserId("up_abc123", 42L, "STORED")).thenReturn(1);
        writeValidChunks();

        completeUploadService.complete("Bearer access-token", "up_abc123");

        assertThat(sessionDirectory().resolve("0.part")).exists();
        assertThat(sessionDirectory().resolve("1.part")).exists();
        assertThat(sessionDirectory().resolve("2.part")).exists();
    }

    @Test
    void completeDoesNotTrustRedisStateWhenLocalChunkFileIsMissing() throws Exception {
        UploadSession session = session("UPLOADING", "mp4", 3, (long) VALID_MP4.length, VALID_MD5);
        stubCurrentUserAndSession(session);
        writeChunk(0, java.util.Arrays.copyOfRange(VALID_MP4, 0, 8));
        writeChunk(2, java.util.Arrays.copyOfRange(VALID_MP4, 16, VALID_MP4.length));

        assertThatThrownBy(() -> completeUploadService.complete("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_CHUNK_MISSING);
        verify(chunkStateService, never()).clear("up_abc123");
    }

    @Test
    void completeDoesNotClearChunkStateWhenCompleteFails() throws Exception {
        UploadSession session = session("UPLOADING", "mp4", 3, VALID_MP4.length + 1L, VALID_MD5);
        stubCurrentUserAndSession(session);
        writeValidChunks();

        assertThatThrownBy(() -> completeUploadService.complete("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_ASSEMBLED_SIZE_MISMATCH);
        verify(chunkStateService, never()).clear("up_abc123");
    }

    @Test
    void completeAcceptsMovFileWithFtypHeader() throws Exception {
        byte[] content = bmff("qt  ");
        UploadSession session = session("UPLOADING", "mov", 3, (long) content.length, md5Hex(content));
        stubCurrentUserAndSession(session);
        when(uploadSessionMapper.updateStatusByIdAndUserId("up_abc123", 42L, "STORED")).thenReturn(1);
        writeChunksOutOfOrder(content);

        CompleteUploadResponse response = completeUploadService.complete("Bearer access-token", "up_abc123");

        assertThat(response.status()).isEqualTo("STORED");
        verify(storageService).putObject(eq(session.getObjectKey()), any(Path.class), eq((long) content.length), eq("video/quicktime"));
        assertThat(assembledPath("mov")).hasBinaryContent(content);
    }

    @Test
    void completeAcceptsMkvFileWithEbmlHeader() throws Exception {
        byte[] content = ebmlContent();
        UploadSession session = session("UPLOADING", "mkv", 3, (long) content.length, md5Hex(content));
        stubCurrentUserAndSession(session);
        when(uploadSessionMapper.updateStatusByIdAndUserId("up_abc123", 42L, "STORED")).thenReturn(1);
        writeChunksOutOfOrder(content);

        CompleteUploadResponse response = completeUploadService.complete("Bearer access-token", "up_abc123");

        assertThat(response.status()).isEqualTo("STORED");
        verify(storageService).putObject(eq(session.getObjectKey()), any(Path.class), eq((long) content.length), eq("video/x-matroska"));
        assertThat(assembledPath("mkv")).hasBinaryContent(content);
    }

    @Test
    void completeAcceptsWebmFileWithEbmlHeader() throws Exception {
        byte[] content = ebmlContent();
        UploadSession session = session("UPLOADING", "webm", 3, (long) content.length, md5Hex(content));
        stubCurrentUserAndSession(session);
        when(uploadSessionMapper.updateStatusByIdAndUserId("up_abc123", 42L, "STORED")).thenReturn(1);
        writeChunksOutOfOrder(content);

        CompleteUploadResponse response = completeUploadService.complete("Bearer access-token", "up_abc123");

        assertThat(response.status()).isEqualTo("STORED");
        verify(storageService).putObject(eq(session.getObjectKey()), any(Path.class), eq((long) content.length), eq("video/webm"));
        assertThat(assembledPath("webm")).hasBinaryContent(content);
    }

    @Test
    void completeRejectsMp4DisguisedPlainTextWithoutUpdatingStatus() throws Exception {
        assertInvalidVideoHeader("mp4", "plain text pretending to be video".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    @Test
    void completeRejectsMovWithoutFtypWithoutUpdatingStatus() throws Exception {
        assertInvalidVideoHeader("mov", concat(new byte[] {0, 0, 0, 12, 'm', 'd', 'a', 't'}, bytes(8)));
    }

    @Test
    void completeRejectsMkvWithoutEbmlMagicWithoutUpdatingStatus() throws Exception {
        assertInvalidVideoHeader("mkv", concat(new byte[] {0, 0, 0, 16, 'f', 't', 'y', 'p'}, bytes(8)));
    }

    @Test
    void completeRejectsWebmWithoutEbmlMagicWithoutUpdatingStatus() throws Exception {
        assertInvalidVideoHeader("webm", concat(new byte[] {0, 0, 0, 16, 'f', 't', 'y', 'p'}, bytes(8)));
    }

    @Test
    void completeRejectsTooSmallVideoHeaderWithoutUpdatingStatus() throws Exception {
        assertInvalidVideoHeader("mp4", new byte[] {0, 0, 0, 1});
    }

    private void stubCurrentUserAndSession(UploadSession session) {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(session);
    }

    private void writeValidChunks() throws Exception {
        writeChunksOutOfOrder(VALID_MP4);
    }

    private void writeChunksOutOfOrder(byte[] content) throws Exception {
        int firstLength = Math.min(8, content.length);
        int secondLength = Math.min(8, content.length - firstLength);
        writeChunk(1, java.util.Arrays.copyOfRange(content, firstLength, firstLength + secondLength));
        writeChunk(0, java.util.Arrays.copyOfRange(content, 0, firstLength));
        writeChunk(2, java.util.Arrays.copyOfRange(content, firstLength + secondLength, content.length));
    }

    private void writeChunk(int index, String content) throws Exception {
        writeChunk(index, content.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    private void writeChunk(int index, byte[] content) throws Exception {
        Path dir = sessionDirectory();
        Files.createDirectories(dir);
        Files.write(dir.resolve(index + ".part"), content);
    }

    private Path sessionDirectory() {
        return tempDir.resolve("42").resolve("up_abc123");
    }

    private Path assembledPath() {
        return assembledPath("mp4");
    }

    private Path assembledPath(String ext) {
        return sessionDirectory().resolve("assembled").resolve("source." + ext);
    }

    private void assertInvalidVideoHeader(String ext, byte[] content) throws Exception {
        UploadSession session = session("UPLOADING", ext, 3, (long) content.length, md5Hex(content));
        stubCurrentUserAndSession(session);
        writeChunksOutOfOrder(content);

        assertThatThrownBy(() -> completeUploadService.complete("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_INVALID_VIDEO_HEADER);
        assertThat(session.getStatus()).isEqualTo("UPLOADING");
        verify(uploadSessionMapper, never()).updateStatusByIdAndUserId(any(), any(), any());
        assertThat(sessionDirectory().resolve("0.part")).exists();
        assertThat(sessionDirectory().resolve("1.part")).exists();
        assertThat(sessionDirectory().resolve("2.part")).exists();
    }

    private static UploadSession session(String status, String ext, int totalChunks, long sizeBytes, String fileMd5) {
        UploadSession session = new UploadSession();
        session.setId("up_abc123");
        session.setUserId(42L);
        session.setFilename("lesson." + ext);
        session.setExt(ext);
        session.setTotalChunks(totalChunks);
        session.setChunkSizeBytes(8L);
        session.setSizeBytes(sizeBytes);
        session.setFileMd5(fileMd5);
        session.setStatus(status);
        session.setStorageType("MINIO");
        session.setObjectKey("raw/42/up_abc123/source." + ext);
        return session;
    }

    private static byte[] bmff(String majorBrand) {
        return concat(
            new byte[] {0, 0, 0, 16, 'f', 't', 'y', 'p'},
            majorBrand.getBytes(java.nio.charset.StandardCharsets.US_ASCII),
            new byte[] {0, 0, 0, 1},
            "video".getBytes(java.nio.charset.StandardCharsets.UTF_8)
        );
    }

    private static byte[] ebmlContent() {
        return concat(new byte[] {0x1A, 0x45, (byte) 0xDF, (byte) 0xA3}, "ebml-video".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    private static byte[] bytes(int length) {
        byte[] value = new byte[length];
        for (int i = 0; i < length; i++) {
            value[i] = (byte) i;
        }
        return value;
    }

    private static byte[] concat(byte[]... chunks) {
        try {
            ByteArrayOutputStream outputStream = new ByteArrayOutputStream();
            for (byte[] chunk : chunks) {
                outputStream.write(chunk);
            }
            return outputStream.toByteArray();
        } catch (java.io.IOException exception) {
            throw new IllegalStateException(exception);
        }
    }

    private static String md5Hex(byte[] content) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("MD5").digest(content));
        } catch (java.security.NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }
}
