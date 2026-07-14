package com.example.courselingo.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalStateException;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

class DemoAiModeGuardTest {

    @Test
    void acceptsExplicitLocalDemoMode() {
        MockEnvironment environment = new MockEnvironment()
            .withProperty("courselingo.ai.asr.mock.enabled", "true")
            .withProperty("courselingo.ai.llm.demo-mock.enabled", "true")
            .withProperty("courselingo.ai.asr.silicon-flow.enabled", "false")
            .withProperty("courselingo.ai.llm.openai-compatible.enabled", "false")
            .withProperty("courselingo.ai.llm.langchain4j.enabled", "false");

        DemoAiModeGuard.validate(environment);

        assertThat(DemoAiModeGuard.isDemoMode(environment)).isTrue();
    }

    @Test
    void rejectsMixedDemoAndRealAsr() {
        MockEnvironment environment = new MockEnvironment()
            .withProperty("courselingo.ai.asr.mock.enabled", "true")
            .withProperty("courselingo.ai.asr.silicon-flow.enabled", "true");

        assertThatIllegalStateException().isThrownBy(() -> DemoAiModeGuard.validate(environment))
            .withMessageContaining("Demo Mock ASR");
    }

    @Test
    void rejectsMixedDemoAndRealLlm() {
        MockEnvironment environment = new MockEnvironment()
            .withProperty("courselingo.ai.llm.demo-mock.enabled", "true")
            .withProperty("courselingo.ai.llm.openai-compatible.enabled", "true");

        assertThatIllegalStateException().isThrownBy(() -> DemoAiModeGuard.validate(environment))
            .withMessageContaining("Demo Mock LLM");
    }

    @Test
    void realAiModeDoesNotReportDemo() {
        MockEnvironment environment = new MockEnvironment()
            .withProperty("courselingo.ai.asr.mock.enabled", "false")
            .withProperty("courselingo.ai.llm.demo-mock.enabled", "false")
            .withProperty("courselingo.ai.asr.silicon-flow.enabled", "true")
            .withProperty("courselingo.ai.llm.openai-compatible.enabled", "true");

        DemoAiModeGuard.validate(environment);

        assertThat(DemoAiModeGuard.isDemoMode(environment)).isFalse();
    }
}
