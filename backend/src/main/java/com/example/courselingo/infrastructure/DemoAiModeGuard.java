package com.example.courselingo.infrastructure;

import org.springframework.core.env.Environment;

/** Validates the explicit local Demo profile before provider beans are created. */
public final class DemoAiModeGuard {

    private DemoAiModeGuard() {
    }

    public static void validate(Environment environment) {
        boolean mockAsr = enabled(environment, "courselingo.ai.asr.mock.enabled");
        boolean siliconFlowAsr = enabled(environment, "courselingo.ai.asr.silicon-flow.enabled");
        boolean demoLlm = enabled(environment, "courselingo.ai.llm.demo-mock.enabled");
        boolean openAiCompatibleLlm = enabled(environment, "courselingo.ai.llm.openai-compatible.enabled");
        boolean langChain4jLlm = enabled(environment, "courselingo.ai.llm.langchain4j.enabled");

        if (openAiCompatibleLlm && langChain4jLlm) {
            throw new IllegalStateException("Only one real text LLM provider may be enabled.");
        }
        boolean consumer = enabled(environment, "courselingo.mq.rocketmq.enabled");
        if (consumer && !enabled(environment, "courselingo.task.runner.pipeline.enabled")) {
            throw new IllegalStateException("An enabled task consumer requires the analysis pipeline.");
        }

        if (consumer && !enabled(environment, "spring.flyway.enabled")) {
            throw new IllegalStateException("An enabled task consumer requires Flyway and durable task tables.");
        }
        if (consumer && !(mockAsr || siliconFlowAsr)) {
            throw new IllegalStateException("An enabled task consumer requires an ASR provider.");
        }
        if (consumer && !(demoLlm || openAiCompatibleLlm || langChain4jLlm)) {
            throw new IllegalStateException("An enabled task consumer requires a text LLM provider.");
        }

        if (mockAsr && siliconFlowAsr) {
            throw new IllegalStateException(
                "Invalid AI provider configuration: Demo Mock ASR and SiliconFlow ASR cannot both be enabled."
            );
        }
        if (demoLlm && (openAiCompatibleLlm || langChain4jLlm)) {
            throw new IllegalStateException(
                "Invalid AI provider configuration: Demo Mock LLM and a real LLM cannot both be enabled."
            );
        }
    }

    public static boolean isDemoMode(Environment environment) {
        return enabled(environment, "courselingo.ai.asr.mock.enabled")
            && enabled(environment, "courselingo.ai.llm.demo-mock.enabled");
    }

    private static boolean enabled(Environment environment, String property) {
        return Boolean.parseBoolean(environment.getProperty(property, "false"));
    }
}
