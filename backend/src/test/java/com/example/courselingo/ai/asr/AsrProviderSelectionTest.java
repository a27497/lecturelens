package com.example.courselingo.ai.asr;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.task.runner.AsrChunkingProperties;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;

class AsrProviderSelectionTest {
    private final ApplicationContextRunner runner = new ApplicationContextRunner().withUserConfiguration(
        BailianAsrConfiguration.class, SiliconFlowAsrConfiguration.class, MockAsrConfiguration.class, ChunkConfig.class);

    @ParameterizedTest
    @ValueSource(strings = {"bailian", "siliconflow", "mock"})
    void explicitSelectionOverridesLegacyFlagsWithoutAmbiguousBean(String name) {
        runner.withPropertyValues("courselingo.ai.asr.provider=" + name,
            "courselingo.ai.asr.silicon-flow.enabled=true", "courselingo.ai.asr.mock.enabled=true",
            "courselingo.ai.asr.bailian.enabled=true").run(context -> {
                assertThat(context).hasNotFailed().hasSingleBean(SpeechToTextProvider.class);
                assertThat(context.getBean(SpeechToTextProvider.class).providerName()).isEqualTo(name);
            });
    }

    @ParameterizedTest
    @ValueSource(strings = {"bailian", "silicon-flow", "mock"})
    void legacySingleFlagRemainsCompatible(String name) {
        runner.withPropertyValues("courselingo.ai.asr." + name + ".enabled=true").run(context -> {
            assertThat(context).hasNotFailed().hasSingleBean(SpeechToTextProvider.class);
            assertThat(context.getBean(SpeechToTextProvider.class).providerName()).isEqualTo(name.replace("-", ""));
        });
    }

    @Test
    void disabledAndInvalidSelectionsAreDeterministic() {
        runner.run(context -> assertThat(context).hasNotFailed().doesNotHaveBean(SpeechToTextProvider.class));
        runner.withPropertyValues("courselingo.ai.asr.provider=none", "courselingo.ai.asr.mock.enabled=true")
            .run(context -> assertThat(context).hasNotFailed().doesNotHaveBean(SpeechToTextProvider.class));
        runner.withPropertyValues("courselingo.ai.asr.provider=unknown")
            .run(context -> assertThat(context).hasFailed());
        runner.withPropertyValues("courselingo.ai.asr.bailian.enabled=true", "courselingo.ai.asr.silicon-flow.enabled=true")
            .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void recommendationIsOptInAndAllowsDurationOverride() throws Exception {
        var source = new YamlPropertySourceLoader().load("recommendation", new ClassPathResource("application-asr-bailian.yml")).getFirst();
        var base = new YamlPropertySourceLoader().load("base", new ClassPathResource("application.yml")).getFirst();
        var profile = runner.withInitializer(context -> {
            context.getEnvironment().getPropertySources().addLast(source);
            context.getEnvironment().getPropertySources().addLast(base);
        });
        profile.run(context -> {
            assertThat(context).hasNotFailed().hasSingleBean(BailianAsrProvider.class);
            var asr = context.getBean(BailianAsrProperties.class);
            assertThat(asr.getModel()).isEqualTo("qwen-audio-3.1-asr-flash");
            assertThat(asr.getEndpoint()).isEqualTo("https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation");
            assertThat(asr.getApiKey()).isEmpty();
            var properties = context.getBean(AsrChunkingProperties.class);
            assertThat(properties.getChunkDuration()).isEqualTo(Duration.ofSeconds(180));
            assertThat(properties.getConcurrency()).isEqualTo(2);
            assertThat(properties.getMaxChunkFileSize().toBytes()).isGreaterThan(180L * 32000 + 44);
        });
        profile.withPropertyValues("ASR_CHUNK_DURATION=120s", "ASR_CHUNK_CONCURRENCY=1").run(context -> {
            assertThat(context.getBean(AsrChunkingProperties.class).getChunkDuration()).isEqualTo(Duration.ofSeconds(120));
            assertThat(context.getBean(AsrChunkingProperties.class).getConcurrency()).isEqualTo(1);
        });
        runner.withPropertyValues("courselingo.ai.asr.provider=siliconflow").run(context ->
            assertThat(context.getBean(AsrChunkingProperties.class).getChunkDuration()).isEqualTo(Duration.ofSeconds(60)));
    }

    @Configuration
    @EnableConfigurationProperties(AsrChunkingProperties.class)
    static class ChunkConfig { }
}
