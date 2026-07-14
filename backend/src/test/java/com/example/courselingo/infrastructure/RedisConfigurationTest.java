package com.example.courselingo.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.upload.service.NoopUploadChunkStateService;
import com.example.courselingo.upload.service.RedisUploadChunkStateService;
import com.example.courselingo.upload.service.UploadChunkStateConfiguration;
import com.example.courselingo.task.progress.NoopTaskProgressSnapshotService;
import com.example.courselingo.task.progress.RedisTaskProgressSnapshotService;
import com.example.courselingo.task.progress.TaskProgressSnapshotConfiguration;
import com.example.courselingo.task.claim.NoopTaskClaimService;
import com.example.courselingo.task.claim.RedisTaskClaimService;
import com.example.courselingo.task.claim.TaskClaimConfiguration;
import com.example.courselingo.task.ratelimit.AnalysisRateLimitConfiguration;
import com.example.courselingo.task.ratelimit.NoopAnalysisRateLimitService;
import com.example.courselingo.task.ratelimit.RedisAnalysisRateLimitService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

class RedisConfigurationTest {

    private final ApplicationContextRunner contextRunner = new ApplicationContextRunner()
        .withUserConfiguration(
            JacksonAutoConfiguration.class,
            RedisConfiguration.class,
            UploadChunkStateConfiguration.class,
            TaskProgressSnapshotConfiguration.class,
            TaskClaimConfiguration.class,
            AnalysisRateLimitConfiguration.class
        );

    @Test
    void redisDisabledByDefaultUsesNoopChunkStateAndDoesNotCreateConnectionFactory() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(NoopUploadChunkStateService.class);
            assertThat(context).hasSingleBean(NoopTaskProgressSnapshotService.class);
            assertThat(context).hasSingleBean(NoopTaskClaimService.class);
            assertThat(context).hasSingleBean(NoopAnalysisRateLimitService.class);
            assertThat(context).doesNotHaveBean(LettuceConnectionFactory.class);
        });
    }

    @Test
    void redisEnabledCreatesConnectionFactoryAndRedisChunkStateService() {
        contextRunner
            .withPropertyValues(
                "courselingo.redis.enabled=true",
                "courselingo.redis.host=127.0.0.1",
                "courselingo.redis.port=6379",
                "courselingo.redis.database=0",
                "courselingo.redis.timeout-ms=2000",
                "courselingo.upload.chunk-state.redis-key-ttl-seconds=60",
                "courselingo.task.progress.redis-key-ttl-seconds=60",
                "courselingo.task.claim.redis-key-ttl-seconds=60",
                "courselingo.task.rate-limit.analysis.enabled=true",
                "courselingo.task.rate-limit.analysis.max-requests=10",
                "courselingo.task.rate-limit.analysis.window-seconds=60"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(LettuceConnectionFactory.class);
                assertThat(context).hasSingleBean(RedisUploadChunkStateService.class);
                assertThat(context).hasSingleBean(RedisTaskProgressSnapshotService.class);
                assertThat(context).hasSingleBean(RedisTaskClaimService.class);
                assertThat(context).hasSingleBean(RedisAnalysisRateLimitService.class);
            });
    }

    @Test
    void rateLimitDisabledUsesNoopEvenWhenRedisIsEnabled() {
        contextRunner
            .withPropertyValues(
                "courselingo.redis.enabled=true",
                "courselingo.task.rate-limit.analysis.enabled=false"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(NoopAnalysisRateLimitService.class);
                assertThat(context).doesNotHaveBean(RedisAnalysisRateLimitService.class);
            });
    }
}
