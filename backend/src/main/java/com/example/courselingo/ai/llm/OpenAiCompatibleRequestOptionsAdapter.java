package com.example.courselingo.ai.llm;

import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

public final class OpenAiCompatibleRequestOptionsAdapter {

    // Official current IDs and documented compatibility aliases, not marketing/version guesses.
    private static final Set<String> DEEPSEEK_NON_THINKING_MODELS = Set.of(
        "deepseek-flash", "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"
    );

    private static final Pattern QWEN3_FAMILY = Pattern.compile("(?:^|[/_-])qwen3(?:$|[/_-])");
    private static final Pattern QWEN3_VISION_FAMILY = Pattern.compile(
        "(?:^|[/_-])qwen3[/_-]vl(?:$|[/_-])"
    );

    private OpenAiCompatibleRequestOptionsAdapter() {
    }

    public static void apply(Map<String, Object> body, String model) {
        if (body == null || model == null) {
            return;
        }
        String normalized = model.strip().toLowerCase(Locale.ROOT);
        if (DEEPSEEK_NON_THINKING_MODELS.contains(normalized)) {
            body.put("thinking", Map.of("type", "disabled"));
        }
        if (QWEN3_FAMILY.matcher(normalized).find()
            && !QWEN3_VISION_FAMILY.matcher(normalized).find()) {
            body.put("enable_thinking", false);
        }
    }

    public static boolean supportsDeepSeekThinkingToggle(String model) {
        return model != null && DEEPSEEK_NON_THINKING_MODELS.contains(model.strip().toLowerCase(Locale.ROOT));
    }
}
