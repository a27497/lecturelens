package com.example.courselingo.ai.llm;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class OpenAiCompatibleRequestOptionsAdapterTest {

    @Test
    void disablesThinkingForSupportedQwen3TextModelVariants() {
        for (String model : new String[] {
            "Qwen/Qwen3-8B",
            "Qwen/Qwen3-30B-A3B",
            "qwen3-coder"
        }) {
            Map<String, Object> body = new HashMap<>();
            OpenAiCompatibleRequestOptionsAdapter.apply(body, model);
            assertThat(body).containsEntry("enable_thinking", false);
        }
    }

    @Test
    void leavesOtherTextAndVisionFamiliesUntouched() {
        for (String model : new String[] {
            "deepseek-ai/DeepSeek-V4-Pro",
            "Qwen/Qwen3-VL-8B-Instruct",
            "Qwen3_VL_30B_A3B_Instruct",
            "Qwen/Qwen2.5-VL-7B-Instruct",
            "generic-chat-model"
        }) {
            Map<String, Object> body = new HashMap<>();
            OpenAiCompatibleRequestOptionsAdapter.apply(body, model);
            assertThat(body).doesNotContainKey("enable_thinking");
        }
    }
}
