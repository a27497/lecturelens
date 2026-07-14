package com.example.courselingo.storage;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import io.minio.BucketExistsArgs;
import io.minio.MakeBucketArgs;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import io.minio.RemoveObjectArgs;
import io.minio.StatObjectArgs;
import io.minio.errors.ErrorResponseException;
import io.minio.messages.ErrorResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class MinioStorageServiceTest {

    @TempDir
    private Path tempDir;

    @Mock
    private MinioClient minioClient;

    private MinioStorageProperties properties;
    private MinioStorageService storageService;

    @BeforeEach
    void setUp() {
        properties = new MinioStorageProperties(
            "http://localhost:9000",
            "test-access-key",
            "very-secret-key",
            "courselingo",
            ""
        );
        storageService = new MinioStorageService(
            minioClient,
            properties,
            new StorageObjectKeyValidator()
        );
    }

    @Test
    void putObjectInitializesMissingBucketAndUploadsFileWithConfiguredBucketAndObjectKey() throws Exception {
        Path sourceFile = fileWithContent("source.mp4", "video");
        when(minioClient.bucketExists(any(BucketExistsArgs.class))).thenReturn(false);

        storageService.putObject("raw/1/up_test/source.mp4", sourceFile, Files.size(sourceFile), "video/mp4");

        ArgumentCaptor<MakeBucketArgs> makeBucketArgs = ArgumentCaptor.forClass(MakeBucketArgs.class);
        ArgumentCaptor<PutObjectArgs> putObjectArgs = ArgumentCaptor.forClass(PutObjectArgs.class);
        verify(minioClient).makeBucket(makeBucketArgs.capture());
        verify(minioClient).putObject(putObjectArgs.capture());
        assertThat(makeBucketArgs.getValue().bucket()).isEqualTo("courselingo");
        assertThat(putObjectArgs.getValue().bucket()).isEqualTo("courselingo");
        assertThat(putObjectArgs.getValue().object()).isEqualTo("raw/1/up_test/source.mp4");
        assertThat(putObjectArgs.getValue().contentType()).isEqualTo("video/mp4");
    }

    @Test
    void putObjectDoesNotCreateBucketWhenBucketAlreadyExists() throws Exception {
        Path sourceFile = fileWithContent("source.mp4", "video");
        when(minioClient.bucketExists(any(BucketExistsArgs.class))).thenReturn(true);

        storageService.putObject("raw/1/up_test/source.mp4", sourceFile, Files.size(sourceFile), "video/mp4");

        verify(minioClient, never()).makeBucket(any(MakeBucketArgs.class));
        verify(minioClient).putObject(any(PutObjectArgs.class));
    }

    @Test
    void putObjectRejectsMissingSourceFile() {
        Path missingFile = tempDir.resolve("missing.mp4");

        assertThatThrownBy(() -> storageService.putObject("raw/1/up_test/source.mp4", missingFile, 1L, "video/mp4"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.STORAGE_SOURCE_FILE_INVALID);
    }

    @Test
    void putObjectRejectsNullSourceFile() {
        assertThatThrownBy(() -> storageService.putObject("raw/1/up_test/source.mp4", null, 1L, "video/mp4"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.STORAGE_SOURCE_FILE_INVALID);
    }

    @Test
    void putObjectRejectsSourceDirectory() throws Exception {
        Path directory = Files.createDirectories(tempDir.resolve("source-dir"));

        assertThatThrownBy(() -> storageService.putObject("raw/1/up_test/source.mp4", directory, 1L, "video/mp4"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.STORAGE_SOURCE_FILE_INVALID);
    }

    @Test
    void putObjectRejectsMismatchedSizeBytes() throws Exception {
        Path sourceFile = fileWithContent("source.mp4", "video");

        assertThatThrownBy(() -> storageService.putObject("raw/1/up_test/source.mp4", sourceFile, 99L, "video/mp4"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.STORAGE_SOURCE_FILE_INVALID);
    }

    @Test
    void putObjectRejectsInvalidObjectKeyBeforeCallingMinio() throws Exception {
        Path sourceFile = fileWithContent("source.mp4", "video");

        assertThatThrownBy(() -> storageService.putObject("../source.mp4", sourceFile, Files.size(sourceFile), "video/mp4"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.STORAGE_INVALID_OBJECT_KEY);
        verify(minioClient, never()).putObject(any(PutObjectArgs.class));
    }

    @Test
    void objectExistsReturnsTrueWhenStatObjectSucceeds() throws Exception {
        assertThat(storageService.objectExists("raw/1/up_test/source.mp4")).isTrue();

        ArgumentCaptor<StatObjectArgs> captor = ArgumentCaptor.forClass(StatObjectArgs.class);
        verify(minioClient).statObject(captor.capture());
        assertThat(captor.getValue().bucket()).isEqualTo("courselingo");
        assertThat(captor.getValue().object()).isEqualTo("raw/1/up_test/source.mp4");
    }

    @Test
    void objectExistsReturnsFalseWhenMinioReportsNoSuchKey() throws Exception {
        when(minioClient.statObject(any(StatObjectArgs.class))).thenThrow(errorResponseException("NoSuchKey"));

        assertThat(storageService.objectExists("raw/1/up_test/source.mp4")).isFalse();
    }

    @Test
    void deleteObjectCallsMinioRemoveObjectWithConfiguredBucket() throws Exception {
        storageService.deleteObject("raw/1/up_test/source.mp4");

        ArgumentCaptor<RemoveObjectArgs> captor = ArgumentCaptor.forClass(RemoveObjectArgs.class);
        verify(minioClient).removeObject(captor.capture());
        assertThat(captor.getValue().bucket()).isEqualTo("courselingo");
        assertThat(captor.getValue().object()).isEqualTo("raw/1/up_test/source.mp4");
    }

    @Test
    void minioSdkExceptionIsWrappedWithoutLeakingSecretKey() throws Exception {
        Path sourceFile = fileWithContent("source.mp4", "video");
        when(minioClient.bucketExists(any(BucketExistsArgs.class))).thenThrow(new InvalidKeyException("bad very-secret-key"));

        assertThatThrownBy(() -> storageService.putObject("raw/1/up_test/source.mp4", sourceFile, Files.size(sourceFile), "video/mp4"))
            .isInstanceOf(BusinessException.class)
            .extracting(Throwable::getMessage)
            .asString()
            .doesNotContain("very-secret-key");
    }

    @Test
    void storageServiceInterfaceIsImplemented() {
        assertThat(storageService).isInstanceOf(StorageService.class);
    }

    @Test
    void minioPropertiesRejectBlankBucket() {
        assertThatThrownBy(() -> new MinioStorageProperties(
            "http://localhost:9000",
            "access",
            "secret",
            " ",
            ""
        ).validate())
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.STORAGE_CONFIGURATION_INVALID);
    }

    @Test
    void minioPropertiesAcceptConfiguredValues() {
        MinioStorageProperties valid = new MinioStorageProperties(
            "http://localhost:9000",
            "access",
            "secret",
            "courselingo",
            "us-east-1"
        );

        assertThatCode(valid::validate).doesNotThrowAnyException();
    }

    private Path fileWithContent(String filename, String content) throws Exception {
        Path file = tempDir.resolve(filename);
        Files.writeString(file, content);
        return file;
    }

    private ErrorResponseException errorResponseException(String code) throws NoSuchAlgorithmException, InvalidKeyException {
        ErrorResponse errorResponse = new ErrorResponse(
            code,
            "not found",
            properties.bucket(),
            "raw/1/up_test/source.mp4",
            "raw/1/up_test/source.mp4",
            "request-id",
            "host-id"
        );
        return new ErrorResponseException(errorResponse, null, "http");
    }
}
