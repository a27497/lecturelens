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
        return List.of(
            new LlmMessage(LlmRole.SYSTEM, """
                你是课程结构整理助手。只能根据用户提供的课程 evidence 生成章节，不允许使用课程外知识。
                你必须输出 JSON object，字段为 chapters。章节标题、总结和关键词使用中文。
                每个章节的开始和结束时间必须来自 evidence 的时间范围，不能编造视频外内容。
                如果证据不足，返回 {"chapters":[]}。
                """),
            new LlmMessage(LlmRole.USER, buildUserPrompt(evidence, globalContext, maxChapters))
        );
    }

    private static String buildUserPrompt(List<CourseChapterEvidenceItem> evidence, String globalContext, int maxChapters) {
        StringBuilder builder = new StringBuilder();
        builder.append("请基于以下课程时间窗口生成课程章节，最多 ").append(maxChapters).append(" 章。\n");
        builder.append("输出格式：{\"chapters\":[{\"title\":\"...\",\"summary\":\"...\",\"startTimeMillis\":0,\"endTimeMillis\":180000,\"keywords\":[\"...\"],\"evidenceIndexes\":[0]}]}\n");
        if (globalContext != null && !globalContext.isBlank()) {
            builder.append("全局辅助上下文，仅用于理解主题，不能作为时间边界：").append(globalContext).append('\n');
        }
        builder.append("Evidence:\n");
        for (CourseChapterEvidenceItem item : evidence == null ? List.<CourseChapterEvidenceItem>of() : evidence) {
            builder.append('[').append(item.index()).append("] ")
                .append(item.timeText())
                .append(" start=").append(item.startTimeMillis())
                .append(" end=").append(item.endTimeMillis())
                .append('\n')
                .append(item.text())
                .append("\n\n");
        }
        return builder.toString();
    }
}
