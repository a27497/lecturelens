package com.example.courselingo.ai.llm;

import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

public final class OpenAiCompatibleRequestOptionsAdapter {

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
        if (QWEN3_FAMILY.matcher(normalized).find()
            && !QWEN3_VISION_FAMILY.matcher(normalized).find()) {
            body.put("enable_thinking", false);
        }
    }
}
