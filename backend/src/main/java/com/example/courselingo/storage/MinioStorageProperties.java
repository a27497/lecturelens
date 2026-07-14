package com.example.courselingo.storage;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.storage.minio")
public record MinioStorageProperties(
    String endpoint,
    String accessKey,
    String secretKey,
    String bucket,
    String region
) {

    public void validate() {
        if (isBlank(endpoint) || isBlank(accessKey) || isBlank(secretKey) || isBlank(bucket)) {
            throw new BusinessException(ErrorCode.STORAGE_CONFIGURATION_INVALID);
        }
    }

    boolean hasRegion() {
        return !isBlank(region);
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
