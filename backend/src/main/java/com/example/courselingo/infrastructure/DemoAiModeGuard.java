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
