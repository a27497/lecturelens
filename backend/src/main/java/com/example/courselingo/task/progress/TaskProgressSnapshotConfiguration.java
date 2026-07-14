package com.example.courselingo.task.progress;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
@EnableConfigurationProperties(TaskProgressProperties.class)
public class TaskProgressSnapshotConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "courselingo.redis", name = "enabled", havingValue = "true")
    TaskProgressSnapshotService redisTaskProgressSnapshotService(
        StringRedisTemplate redisTemplate,
        ObjectMapper objectMapper,
        TaskProgressProperties properties
    ) {
        return new RedisTaskProgressSnapshotService(redisTemplate, objectMapper, properties);
    }

    @Bean
    @ConditionalOnMissingBean(TaskProgressSnapshotService.class)
    TaskProgressSnapshotService noopTaskProgressSnapshotService() {
        return new NoopTaskProgressSnapshotService();
    }
}
