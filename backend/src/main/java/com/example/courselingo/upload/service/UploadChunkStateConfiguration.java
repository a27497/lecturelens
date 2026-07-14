package com.example.courselingo.upload.service;

import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
@EnableConfigurationProperties(UploadChunkStateProperties.class)
public class UploadChunkStateConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "courselingo.redis", name = "enabled", havingValue = "true")
    UploadChunkStateService redisUploadChunkStateService(
        StringRedisTemplate redisTemplate,
        UploadChunkStateProperties properties
    ) {
        return new RedisUploadChunkStateService(redisTemplate, properties);
    }

    @Bean
    @ConditionalOnMissingBean(UploadChunkStateService.class)
    UploadChunkStateService noopUploadChunkStateService() {
        return new NoopUploadChunkStateService();
    }
}
