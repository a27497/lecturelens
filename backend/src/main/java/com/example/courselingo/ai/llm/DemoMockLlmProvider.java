package com.example.courselingo.ai.llm;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Deterministic local-only LLM provider for the explicitly enabled public demo profile.
 */
public final class DemoMockLlmProvider implements LlmProvider {

    public static final String PROVIDER_NAME = "demo-mock";
    public static final String MODEL_NAME = "lecturelens-demo-v1";

    private static final String LEARNING_PACKAGE = """
        {"summary":"这是 LectureLens 本地演示学习包，展示课程视频如何被整理为便于阅读的学习资料。","keyPoints":["异步 Pipeline 依次完成转写、翻译与资料生成","时间轴内容可以与原视频配合阅读","学习结果可导出为多种文件格式"],"glossary":[{"term":"异步 Pipeline","definition":"在后台按步骤处理课程视频的任务链路。"},{"term":"时间轴字幕","definition":"带有开始和结束时间的课程文本。"}],"qa":[{"question":"本地演示会调用外部 AI 吗？","answer":"不会，Demo Provider 只返回确定性的本地演示内容。"},{"question":"如何切换到真实 AI？","answer":"使用真实 AI 配置并填写自己的服务密钥。"}]}
        """;

    @Override
    public LlmResult generate(LlmRequest request) {
        LlmRequestValidator.validate(request);
        String content = request.responseFormat() == LlmResponseFormat.TEXT
            ? "这是由本地 Demo Provider 生成的中文演示翻译。"
            : jsonContent(request.metadata());
        return new LlmResult(
            PROVIDER_NAME,
            MODEL_NAME,
            content,
            "stop",
            new LlmUsage(0, 0, 0),
            Duration.ZERO,
            Map.of("demo", true, "externalCalls", 0)
        );
    }

    @Override
    public String providerName() {
        return PROVIDER_NAME;
    }

    @Override
    public String modelNameForDiagnostics() {
        return MODEL_NAME;
    }

    private static String jsonContent(Map<String, Object> metadata) {
        if ("alignedBatch".equals(metadata.get("translationMode"))) {
            return alignedTranslation(segmentCount(metadata.get("sourceSegmentCount")));
        }
        return LEARNING_PACKAGE;
    }

    private static int segmentCount(Object value) {
        if (value instanceof Number number) {
            return Math.max(1, number.intValue());
        }
        if (value instanceof String text) {
            try {
                return Math.max(1, Integer.parseInt(text));
            } catch (NumberFormatException ignored) {
                return 1;
            }
        }
        return 1;
    }

    private static String alignedTranslation(int count) {
        StringBuilder json = new StringBuilder("{\"segments\":[");
        for (int index = 0; index < count; index++) {
            if (index > 0) {
                json.append(',');
            }
            json.append("{\"index\":")
                .append(index)
                .append(",\"text\":\"这是第 ")
                .append(index + 1)
                .append(" 段本地演示翻译，用于验证时间轴对齐。\"}");
        }
        return json.append("]}").toString();
    }
}
