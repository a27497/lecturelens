package com.example.courselingo.task.claim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
@EnableConfigurationProperties(RedisTaskClaimProperties.class)
public class TaskClaimConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "courselingo.redis", name = "enabled", havingValue = "true")
    TaskClaimService redisTaskClaimService(
        StringRedisTemplate redisTemplate,
        ObjectMapper objectMapper,
        RedisTaskClaimProperties properties
    ) {
        return new RedisTaskClaimService(redisTemplate, objectMapper, properties, Clock.systemUTC());
    }

    @Bean
    @ConditionalOnMissingBean(TaskClaimService.class)
    TaskClaimService noopTaskClaimService() {
        return new NoopTaskClaimService();
    }
}
