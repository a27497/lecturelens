package com.example.courselingo.qa.service;

import com.example.courselingo.ai.llm.LlmMessage;
import com.example.courselingo.ai.llm.LlmRole;
import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import java.util.List;

final class CourseQaPromptFactory {

    private CourseQaPromptFactory() {
    }

    static List<LlmMessage> buildMessages(String question, List<CourseQaEvidenceItem> evidence) {
        return List.of(
            new LlmMessage(LlmRole.SYSTEM, systemPrompt()),
            new LlmMessage(LlmRole.USER, userPrompt(question, evidence))
        );
    }

    private static String systemPrompt() {
        return """
            You are CourseLingo Pro's course question answering assistant.
            Answer in Chinese only.
            Use only the provided course evidence. Do not invent facts outside the course.
            If the evidence is insufficient, answer exactly: %s
            Return only a valid JSON object. Do not return Markdown or code fences.
            Required JSON schema: {"answer":"...","citedEvidenceIndexes":[0]}
            """.formatted(CourseQaMessages.INSUFFICIENT_EVIDENCE);
    }

    private static String userPrompt(String question, List<CourseQaEvidenceItem> evidence) {
        StringBuilder builder = new StringBuilder();
        builder.append("Question: ").append(question).append('\n');
        builder.append("Course evidence:\n");
        for (int i = 0; i < evidence.size(); i++) {
            CourseQaEvidenceItem item = evidence.get(i);
            builder.append('[').append(i).append("] ")
                .append("time=").append(item.timeText())
                .append(" source=").append(item.sourceType())
                .append(" content=").append(item.snippet());
            if (item.translatedSnippet() != null && !item.translatedSnippet().isBlank()) {
                builder.append(" translated=").append(item.translatedSnippet());
            }
            builder.append('\n');
        }
        builder.append("Return JSON only.");
        return builder.toString();
    }
}
