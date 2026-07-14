package com.example.courselingo.learning;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.learning.service.LearningPackageConfiguration;
import com.example.courselingo.learning.service.LearningPackageProperties;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class LearningPackageConfigurationTest {

    private final ApplicationContextRunner contextRunner = new ApplicationContextRunner()
        .withUserConfiguration(LearningPackageConfiguration.class);

    @Test
    void defaultLlmTimeoutIs180Seconds() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(LearningPackageProperties.class);
            assertThat(context.getBean(LearningPackageProperties.class).llmTimeout())
                .isEqualTo(Duration.ofSeconds(180));
        });
    }

    @Test
    void configuredLlmTimeoutOverridesDefault() {
        contextRunner
            .withPropertyValues("courselingo.learning-package.llm-timeout=240s")
            .run(context -> {
                assertThat(context).hasSingleBean(LearningPackageProperties.class);
                assertThat(context.getBean(LearningPackageProperties.class).llmTimeout())
                    .isEqualTo(Duration.ofSeconds(240));
            });
    }
}
