package com.example.courselingo.subtitle.pipeline;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.ai.asr.AsrPipelinePolicy;
import com.example.courselingo.task.runner.AsrChunkingProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;

class PipelineAsrPropertiesDefaultTest {
    private final ApplicationContextRunner runner = new ApplicationContextRunner()
        .withUserConfiguration(Config.class)
        .withInitializer(context -> {
            try {
                var sources = new YamlPropertySourceLoader().load("base", new ClassPathResource("application.yml"));
                sources.forEach(source -> context.getEnvironment().getPropertySources().addLast(source));
            } catch (Exception failure) {
                throw new IllegalStateException(failure);
            }
        });

    @Test
    void yamlDefaultsEnableMergeAndCapConcurrencyAtFour() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            var asr = context.getBean(PipelineTranslationProperties.class).getAsr();
            assertThat(asr.isEnabled()).isFalse();
            assertThat(asr.isMergeEnabled()).isTrue();
            assertThat(asr.isCacheEnabled()).isFalse();
            assertThat(asr.getInitial()).isEqualTo(2);
            assertThat(asr.getMaximum()).isEqualTo(4);
            assertThat(asr.getRequestsPerSecond()).isEqualTo(10);
            var chunking = context.getBean(AsrChunkingProperties.class);
            assertThat(chunking.getConcurrency()).isEqualTo(4);
            assertThat(chunking.effectiveConcurrency()).isEqualTo(4);
        });
    }

    @Test
    void freezePipelineAttachesMergeWithoutAdaptiveScheduling() {
        var settings = new PipelineTranslationProperties();
        settings.setEnabled(true);
        settings.setCheckpointEnabled(true);
        var policy = settings.freezePipeline(
            java.time.Duration.ofSeconds(120), java.time.Duration.ofMinutes(15), 1, 1000, 16000, 1, 4, 4 * 1024 * 1024, 3,
            java.util.List.of(2000L, 5000L, 10000L)
        );
        assertThat(policy.asr()).isNull();
        assertThat(policy.audioClipMerge()).isEqualTo(new com.example.courselingo.media.AudioClipMergePolicy(60000, 90000, 120000));
    }

    @Test
    void yamlOverridesCanDisableMergeAndLowerConcurrency() {
        runner.withPropertyValues(
            "PIPELINE_ASR_ADAPTIVE_ENABLED=false",
            "PIPELINE_ASR_MERGE_ENABLED=false",
            "PIPELINE_ASR_CONCURRENCY_INITIAL=2",
            "ASR_CHUNK_CONCURRENCY=2"
        ).run(context -> {
            var asr = context.getBean(PipelineTranslationProperties.class).getAsr();
            assertThat(asr.isEnabled()).isFalse();
            assertThat(asr.isMergeEnabled()).isFalse();
            assertThat(asr.getInitial()).isEqualTo(2);
            assertThat(context.getBean(AsrChunkingProperties.class).effectiveConcurrency()).isEqualTo(2);
        });
    }

    @Test
    void adaptivePolicyRejectsAPeakAboveTheHardCap() {
        assertThatThrownBy(() -> new AsrPipelinePolicy(
            4, 9, 3, 10, 1, true, 60000, 90000, 120000, false, 86400, 256, "a".repeat(64), "b".repeat(64)
        )).isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("Invalid ASR pipeline policy");
    }

    @Configuration
    @EnableConfigurationProperties({PipelineTranslationProperties.class, AsrChunkingProperties.class})
    static class Config { }
}
