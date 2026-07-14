package com.example.courselingo.storage;

import io.minio.MinioClient;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(MinioStorageProperties.class)
public class MinioStorageConfiguration {

    @Bean
    MinioClient minioClient(MinioStorageProperties properties) {
        properties.validate();
        MinioClient.Builder builder = MinioClient.builder()
            .endpoint(properties.endpoint())
            .credentials(properties.accessKey(), properties.secretKey());
        if (properties.hasRegion()) {
            builder.region(properties.region());
        }
        return builder.build();
    }
}
