package com.example.courselingo.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

class PublicRuntimeConfigurationControllerTest {

    @Test
    void exposesOnlyVerifiedDemoMode() {
        PublicRuntimeConfigurationController controller = new PublicRuntimeConfigurationController(
            new MockEnvironment()
                .withProperty("courselingo.ai.asr.mock.enabled", "true")
                .withProperty("courselingo.ai.llm.demo-mock.enabled", "true")
        );

        assertThat(controller.runtimeConfiguration().data().demoMode()).isTrue();
    }

    @Test
    void reportsFalseWhenTheBackendIsNotInDemoMode() {
        PublicRuntimeConfigurationController controller = new PublicRuntimeConfigurationController(
            new MockEnvironment().withProperty("courselingo.ai.asr.mock.enabled", "true")
        );

        assertThat(controller.runtimeConfiguration().data().demoMode()).isFalse();
    }
}
