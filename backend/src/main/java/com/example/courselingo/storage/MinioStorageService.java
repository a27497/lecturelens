package com.example.courselingo.storage;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import io.minio.BucketExistsArgs;
import io.minio.GetObjectArgs;
import io.minio.MakeBucketArgs;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import io.minio.RemoveObjectArgs;
import io.minio.StatObjectArgs;
import io.minio.errors.ErrorResponseException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.stereotype.Service;

@Service
public class MinioStorageService implements StorageService {

    private final MinioClient minioClient;
    private final MinioStorageProperties properties;
    private final StorageObjectKeyValidator objectKeyValidator;

    public MinioStorageService(
        MinioClient minioClient,
        MinioStorageProperties properties,
        StorageObjectKeyValidator objectKeyValidator
    ) {
        this.minioClient = minioClient;
        this.properties = properties;
        this.objectKeyValidator = objectKeyValidator;
    }

    @Override
    public void putObject(String objectKey, Path sourceFile, long sizeBytes, String contentType) {
        objectKeyValidator.validate(objectKey);
        validateSourceFile(sourceFile, sizeBytes);
        try {
            ensureBucketExists();
            try (InputStream inputStream = Files.newInputStream(sourceFile)) {
                minioClient.putObject(PutObjectArgs.builder()
                    .bucket(properties.bucket())
                    .object(objectKey)
                    .stream(inputStream, sizeBytes, -1)
                    .contentType(contentType)
                    .build());
            }
        } catch (Exception exception) {
            throw storageOperationFailed(exception);
        }
    }

    @Override
    public InputStream openObject(String objectKey) {
        objectKeyValidator.validate(objectKey);
        try {
            return minioClient.getObject(GetObjectArgs.builder()
                .bucket(properties.bucket())
                .object(objectKey)
                .build());
        } catch (ErrorResponseException exception) {
            if (isNotFound(exception)) {
                throw new BusinessException(ErrorCode.ARTIFACT_NOT_FOUND);
            }
            throw storageOperationFailed(exception);
        } catch (Exception exception) {
            throw storageOperationFailed(exception);
        }
    }

    @Override
    public boolean objectExists(String objectKey) {
        objectKeyValidator.validate(objectKey);
        try {
            minioClient.statObject(StatObjectArgs.builder()
                .bucket(properties.bucket())
                .object(objectKey)
                .build());
            return true;
        } catch (ErrorResponseException exception) {
            if (isNotFound(exception)) {
                return false;
            }
            throw storageOperationFailed(exception);
        } catch (Exception exception) {
            throw storageOperationFailed(exception);
        }
    }

    @Override
    public void deleteObject(String objectKey) {
        objectKeyValidator.validate(objectKey);
        try {
            minioClient.removeObject(RemoveObjectArgs.builder()
                .bucket(properties.bucket())
                .object(objectKey)
                .build());
        } catch (Exception exception) {
            throw storageOperationFailed(exception);
        }
    }

    private void ensureBucketExists() throws Exception {
        boolean bucketExists = minioClient.bucketExists(BucketExistsArgs.builder()
            .bucket(properties.bucket())
            .build());
        if (!bucketExists) {
            minioClient.makeBucket(MakeBucketArgs.builder()
                .bucket(properties.bucket())
                .build());
        }
    }

    private void validateSourceFile(Path sourceFile, long sizeBytes) {
        if (sourceFile == null || !Files.isRegularFile(sourceFile)) {
            throw new BusinessException(ErrorCode.STORAGE_SOURCE_FILE_INVALID);
        }
        try {
            if (Files.size(sourceFile) != sizeBytes) {
                throw new BusinessException(ErrorCode.STORAGE_SOURCE_FILE_INVALID);
            }
        } catch (BusinessException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new BusinessException(ErrorCode.STORAGE_SOURCE_FILE_INVALID);
        }
    }

    private static boolean isNotFound(ErrorResponseException exception) {
        String code = exception.errorResponse().code();
        return "NoSuchKey".equals(code) || "NoSuchObject".equals(code) || "NoSuchBucket".equals(code);
    }

    private static BusinessException storageOperationFailed(Exception exception) {
        return new BusinessException(ErrorCode.STORAGE_OPERATION_FAILED, exception);
    }
}
