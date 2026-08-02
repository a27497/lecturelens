package com.example.courselingo.chapter.service;

import com.example.courselingo.ai.llm.LlmMessage;
import com.example.courselingo.ai.llm.LlmRole;
import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import java.util.List;

public final class CourseChapterPromptFactory {

    private CourseChapterPromptFactory() {
    }

    public static List<LlmMessage> buildMessages(
        List<CourseChapterEvidenceItem> evidence,
        String globalContext,
        int maxChapters
    ) {
        return buildMessages(evidence, globalContext, maxChapters, 24000);
    }

    public static List<LlmMessage> buildMessages(
        List<CourseChapterEvidenceItem> evidence,
        String globalContext,
        int maxChapters,
        int maxPromptChars
    ) {
        String system = systemPrompt();
        int safeLimit = Math.max(4000, Math.min(maxPromptChars, 24000));
        return List.of(
            new LlmMessage(LlmRole.SYSTEM, system),
            new LlmMessage(
                LlmRole.USER,
                buildUserPrompt(evidence, globalContext, maxChapters, Math.max(1000, safeLimit - system.length()))
            )
        );
    }

    private static String systemPrompt() {
        return """
            你是课程结构整理助手。只能根据用户提供的课程 evidence 生成章节，不允许使用课程外知识。
            你必须输出 JSON object，字段为 chapters。章节标题、总结和关键词使用中文。
            每个章节的开始和结束时间必须来自 evidence 的时间范围，不能编造视频外内容。
            如果证据不足，返回 {"chapters":[]}。
            """;
    }

    private static String buildUserPrompt(
        List<CourseChapterEvidenceItem> evidence,
        String globalContext,
        int maxChapters,
        int maxChars
    ) {
        StringBuilder builder = new StringBuilder();
        builder.append("Cover the complete timeline from the first evidence item through the last. ")
            .append("Every chapter must cite at least one evidence index, and every evidence index must be cited. ")
            .append("Keep chapters ordered, non-overlapping, and contiguous with no uncovered time gap. ")
            .append("Long courses must not be summarized only at the beginning. Use no outside knowledge.\n");
        builder.append("请基于以下课程时间窗口生成课程章节，最多 ").append(maxChapters).append(" 章。\n");
        builder.append("输出格式：{\"chapters\":[{\"title\":\"...\",\"summary\":\"...\",\"startTimeMillis\":0,\"endTimeMillis\":180000,\"keywords\":[\"...\"],\"evidenceIndexes\":[0]}]}\n");
        if (globalContext != null && !globalContext.isBlank()) {
            builder.append("全局辅助上下文，仅用于理解主题，不能作为时间边界：")
                .append(truncate(globalContext, 1600)).append('\n');
        }
        builder.append("Evidence:\n");
        List<CourseChapterEvidenceItem> safeEvidence = evidence == null ? List.of() : evidence;
        int fixedChars = builder.length() + 32;
        int perItemChars = safeEvidence.isEmpty()
            ? 0
            : Math.max(160, (maxChars - fixedChars) / safeEvidence.size() - 80);
        for (CourseChapterEvidenceItem item : safeEvidence) {
            StringBuilder block = new StringBuilder();
            block.append('[').append(item.index()).append("] ")
                .append(item.timeText())
                .append(" start=").append(item.startTimeMillis())
                .append(" end=").append(item.endTimeMillis())
                .append('\n')
                .append(truncate(item.text(), perItemChars))
                .append("\n\n");
            if (builder.length() + block.length() > maxChars) {
                break;
            }
            builder.append(block);
        }
        return builder.toString();
    }

    public static int promptChars(List<LlmMessage> messages) {
        return messages == null ? 0 : messages.stream().mapToInt(message -> message.content().length()).sum();
    }

    public static List<LlmMessage> buildRepairMessages(List<LlmMessage> originalMessages) {
        List<LlmMessage> safe = originalMessages == null ? List.of() : originalMessages;
        java.util.ArrayList<LlmMessage> repaired = new java.util.ArrayList<>(safe);
        repaired.add(new LlmMessage(
            LlmRole.USER,
            "上一次输出未通过结构校验。请重新生成完整 JSON object，严格遵守既定 schema、证据索引和时间边界；不要输出解释、Markdown 或代码围栏。"
        ));
        return List.copyOf(repaired);
    }

    public static List<LlmMessage> buildRepairMessages(
        List<LlmMessage> originalMessages,
        CourseChapterCoverageReport report
    ) {
        List<LlmMessage> safe = originalMessages == null ? List.of() : originalMessages;
        CourseChapterCoverageReport safeReport = report == null
            ? CourseChapterCoverageReport.structuralFailure("structured output is invalid")
            : report;
        java.util.ArrayList<LlmMessage> repaired = new java.util.ArrayList<>(safe);
        repaired.add(new LlmMessage(
            LlmRole.USER,
            "The previous output failed chapter coverage validation. Regenerate the complete JSON object. "
                + "timelineCoverage=" + safeReport.timelineCoverageRatio()
                + ", evidenceCoverage=" + safeReport.evidenceCoverageRatio()
                + ", missingEvidenceIndexes=" + safeReport.missingEvidenceIndexes()
                + ", missingTimeRanges=" + safeReport.missingTimeRanges()
                + ", chaptersWithoutEvidence=" + safeReport.chaptersWithoutEvidence()
                + ", maxGapMillis=" + safeReport.maxGapMillis()
                + ", violations=" + safeReport.violations()
                + ". Return JSON only; do not include Markdown, explanations, or provider output."
        ));
        return List.copyOf(repaired);
    }

    private static String truncate(String value, int maxChars) {
        String safe = value == null ? "" : value.replaceAll("\\s+", " ").strip();
        int limit = Math.max(0, maxChars);
        return safe.length() <= limit ? safe : safe.substring(0, limit);
    }
}
