package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import com.example.courselingo.upload.service.ChunkStagingPathResolver;
import com.example.courselingo.upload.service.ChunkStagingProperties;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ResolveUploadedSourceStepTest {

    private static final byte[] VIDEO = "video".getBytes(StandardCharsets.UTF_8);

    @TempDir
    private Path tempDir;

    @Test
    void storedSessionUsesValidCacheOnlyAfterRemoteObjectExists() throws Exception {
        Fixture fixture = fixture("STORED");
        Path assembled = fixture.assembled();
        Files.createDirectories(assembled.getParent());
        Files.write(assembled, VIDEO);
        when(fixture.storage().objectExists("raw/7/up_1/source.mp4")).thenReturn(true);

        PipelineAnalysisTaskStepContext context = context();
        fixture.step().execute(context);

        assertThat(context.uploadedSourcePath()).contains(assembled);
        verify(fixture.storage()).objectExists("raw/7/up_1/source.mp4");
        verify(fixture.storage(), never()).openObject("raw/7/up_1/source.mp4");
        assertThat(context.toString())
            .doesNotContain(assembled.toString())
            .doesNotContain("raw/7/up_1/source.mp4")
            .doesNotContainIgnoringCase("objectKey");
    }

    @Test
    void storedSessionFailsWhenRemoteObjectIsMissingEvenWithValidCache() throws Exception {
        Fixture fixture = fixture("STORED");
        Files.createDirectories(fixture.assembled().getParent());
        Files.write(fixture.assembled(), VIDEO);
        when(fixture.storage().objectExists("raw/7/up_1/source.mp4")).thenReturn(false);

        assertStorageFailure(fixture);
        verify(fixture.storage(), never()).openObject("raw/7/up_1/source.mp4");
    }

    @Test
    void storedSessionRestoresMissingCacheFromMinio() throws Exception {
        Fixture fixture = fixture("STORED");
        when(fixture.storage().objectExists("raw/7/up_1/source.mp4")).thenReturn(true);
        when(fixture.storage().openObject("raw/7/up_1/source.mp4"))
            .thenReturn(new ByteArrayInputStream(VIDEO));

        PipelineAnalysisTaskStepContext context = context();
        fixture.step().execute(context);

        assertThat(fixture.assembled()).hasBinaryContent(VIDEO);
        assertThat(context.uploadedSourcePath()).contains(fixture.assembled());
        assertNoTemporaryFiles(fixture.assembled().getParent());
    }

    @Test
    void storedSessionReplacesWrongSizedCacheFromMinio() throws Exception {
        Fixture fixture = fixture("STORED");
        Files.createDirectories(fixture.assembled().getParent());
        Files.writeString(fixture.assembled(), "bad", StandardCharsets.UTF_8);
        when(fixture.storage().objectExists("raw/7/up_1/source.mp4")).thenReturn(true);
        when(fixture.storage().openObject("raw/7/up_1/source.mp4"))
            .thenReturn(new ByteArrayInputStream(VIDEO));

        fixture.step().execute(context());

        assertThat(fixture.assembled()).hasBinaryContent(VIDEO);
        assertNoTemporaryFiles(fixture.assembled().getParent());
    }

    @Test
    void wrongDownloadedSizeFailsWithoutPartialOrTemporaryFile() throws Exception {
        Fixture fixture = fixture("STORED");
        when(fixture.storage().objectExists("raw/7/up_1/source.mp4")).thenReturn(true);
        when(fixture.storage().openObject("raw/7/up_1/source.mp4"))
            .thenReturn(new ByteArrayInputStream("bad".getBytes(StandardCharsets.UTF_8)));

        assertStorageFailure(fixture);

        assertThat(fixture.assembled()).doesNotExist();
        assertNoTemporaryFiles(fixture.assembled().getParent());
    }

    @Test
    void openObjectFailureLeavesNoPartialOrTemporaryFile() throws Exception {
        Fixture fixture = fixture("STORED");
        when(fixture.storage().objectExists("raw/7/up_1/source.mp4")).thenReturn(true);
        when(fixture.storage().openObject("raw/7/up_1/source.mp4"))
            .thenThrow(new BusinessException(ErrorCode.STORAGE_OPERATION_FAILED));

        assertStorageFailure(fixture);

        assertThat(fixture.assembled()).doesNotExist();
        assertNoTemporaryFiles(fixture.assembled().getParent());
    }

    @Test
    void legacyUploadedSessionUsesOnlyLocalAssembledFile() throws Exception {
        Fixture fixture = fixture("UPLOADED");
        Files.createDirectories(fixture.assembled().getParent());
        Files.write(fixture.assembled(), VIDEO);

        PipelineAnalysisTaskStepContext context = context();
        fixture.step().execute(context);

        assertThat(context.uploadedSourcePath()).contains(fixture.assembled());
        verify(fixture.storage(), never()).objectExists("raw/7/up_1/source.mp4");
        verify(fixture.storage(), never()).openObject("raw/7/up_1/source.mp4");
    }

    @Test
    void legacyUploadedSessionFailsWhenLocalFileIsMissing() {
        assertStorageFailure(fixture("UPLOADED"));
    }

    @Test
    void missingUploadOwnerMismatchInvalidMetadataAndOtherStatusesFailSafely() {
        UploadSessionMapper mapper = mock(UploadSessionMapper.class);
        StorageService storage = mock(StorageService.class);
        when(mapper.selectById("up_1")).thenReturn(null);
        assertThatThrownBy(() -> step(mapper, storage).execute(context()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode").isEqualTo(ErrorCode.UPLOAD_SESSION_NOT_FOUND);

        for (String status : new String[] {"CREATED", "UPLOADING", "MERGING", "FAILED", "CANCELLED", "UNKNOWN"}) {
            when(mapper.selectById("up_1")).thenReturn(session(7L, status, "mp4"));
            assertThatThrownBy(() -> step(mapper, storage).execute(context()))
                .isInstanceOf(BusinessException.class)
                .extracting("errorCode").isEqualTo(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);
        }

        when(mapper.selectById("up_1")).thenReturn(session(99L, "STORED", "mp4"));
        assertThatThrownBy(() -> step(mapper, storage).execute(context()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode").isEqualTo(ErrorCode.UPLOAD_SESSION_NOT_FOUND);

        UploadSession wrongStorage = session(7L, "STORED", "mp4");
        wrongStorage.setStorageType("LOCAL");
        when(mapper.selectById("up_1")).thenReturn(wrongStorage);
        assertThatThrownBy(() -> step(mapper, storage).execute(context()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode").isEqualTo(ErrorCode.STORAGE_SOURCE_FILE_INVALID);

        UploadSession missingKey = session(7L, "STORED", "mp4");
        missingKey.setObjectKey(" ");
        when(mapper.selectById("up_1")).thenReturn(missingKey);
        assertThatThrownBy(() -> step(mapper, storage).execute(context()))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> assertThat(error.getMessage()).doesNotContain("raw/"));
    }

    private void assertStorageFailure(Fixture fixture) {
        assertThatThrownBy(() -> fixture.step().execute(context()))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                assertThat(((BusinessException) error).errorCode()).isEqualTo(ErrorCode.STORAGE_SOURCE_FILE_INVALID);
                assertThat(error.getMessage()).doesNotContain("raw/7/up_1/source.mp4");
                assertThat(error.getMessage()).doesNotContain(tempDir.toString());
            });
    }

    private void assertNoTemporaryFiles(Path directory) throws Exception {
        if (!Files.exists(directory)) {
            return;
        }
        try (var files = Files.list(directory)) {
            assertThat(files.filter(path -> !path.equals(directory.resolve("source.mp4")))).isEmpty();
        }
    }

    private Fixture fixture(String status) {
        UploadSessionMapper mapper = mock(UploadSessionMapper.class);
        StorageService storage = mock(StorageService.class);
        UploadSession session = session(7L, status, "mp4");
        when(mapper.selectById("up_1")).thenReturn(session);
        ChunkStagingPathResolver resolver = pathResolver();
        return new Fixture(storage, resolver.resolveAssembledFile(7L, "up_1", "mp4"), step(mapper, storage));
    }

    private ResolveUploadedSourceStep step(UploadSessionMapper mapper, StorageService storage) {
        return new ResolveUploadedSourceStep(mapper, pathResolver(), storage);
    }

    private ChunkStagingPathResolver pathResolver() {
        return new ChunkStagingPathResolver(new ChunkStagingProperties(tempDir.resolve("chunks")));
    }

    private static PipelineAnalysisTaskStepContext context() {
        return new PipelineAnalysisTaskStepContext(
            new AnalysisTaskExecutionContext("task_1", "up_1", 7L, "zh-CN", "req_1")
        );
    }

    private static UploadSession session(Long userId, String status, String ext) {
        UploadSession session = new UploadSession();
        session.setId("up_1");
        session.setUserId(userId);
        session.setStatus(status);
        session.setExt(ext);
        session.setSizeBytes((long) VIDEO.length);
        session.setStorageType("MINIO");
        session.setObjectKey("raw/" + userId + "/up_1/source." + ext);
        return session;
    }

    private record Fixture(StorageService storage, Path assembled, ResolveUploadedSourceStep step) {
    }
}
