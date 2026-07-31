package com.example.courselingo.qa.service;

import com.example.courselingo.ai.llm.LlmMessage;
import com.example.courselingo.ai.llm.LlmRole;
import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import java.util.List;

final class CourseQaPromptFactory {

    private CourseQaPromptFactory() {
    }

    static List<LlmMessage> buildMessages(String question, List<CourseQaEvidenceItem> evidence) {
        return buildMessages(question, evidence, 12000);
    }

    static List<LlmMessage> buildMessages(String question, List<CourseQaEvidenceItem> evidence, int maxPromptChars) {
        return buildMessages(question, evidence, maxPromptChars, 500);
    }

    static List<LlmMessage> buildMessages(
        String question,
        List<CourseQaEvidenceItem> evidence,
        int maxPromptChars,
        int maxSnippetChars
    ) {
        int safeLimit = Math.max(1000, Math.min(maxPromptChars, 12000));
        int safeSnippetLimit = Math.max(100, Math.min(maxSnippetChars, 1000));
        String system = systemPrompt();
        String user = userPrompt(question, evidence, Math.max(200, safeLimit - system.length()), safeSnippetLimit);
        return List.of(
            new LlmMessage(LlmRole.SYSTEM, system),
            new LlmMessage(LlmRole.USER, user)
        );
    }

    private static String systemPrompt() {
        return """
            You are CourseLingo Pro's course question answering assistant.
            Answer in Chinese only.
            Use only the provided course evidence. Do not invent facts outside the course.
            Keep the answer direct and concise. Cite only evidence that materially supports the answer.
            If the evidence is insufficient, answer exactly: %s
            Return only a valid JSON object. Do not return Markdown or code fences.
            Required JSON schema: {"answer":"...","citedEvidenceIndexes":[0]}
            """.formatted(CourseQaMessages.INSUFFICIENT_EVIDENCE);
    }

    private static String userPrompt(
        String question,
        List<CourseQaEvidenceItem> evidence,
        int maxChars,
        int maxSnippetChars
    ) {
        StringBuilder builder = new StringBuilder();
        builder.append("Question: ").append(truncate(question, 500)).append('\n');
        builder.append("Course evidence:\n");
        for (int i = 0; i < evidence.size(); i++) {
            CourseQaEvidenceItem item = evidence.get(i);
            StringBuilder line = new StringBuilder();
            line.append('[').append(i).append("] ")
                .append("time=").append(item.timeText())
                .append(" source=").append(item.sourceType())
                .append(" content=").append(truncate(item.snippet(), maxSnippetChars));
            if (item.translatedSnippet() != null && !item.translatedSnippet().isBlank()) {
                line.append(" translated=").append(truncate(item.translatedSnippet(), maxSnippetChars));
            }
            line.append('\n');
            if (builder.length() + line.length() + 18 > maxChars) {
                break;
            }
            builder.append(line);
        }
        builder.append("Return JSON only.");
        return builder.length() <= maxChars ? builder.toString() : builder.substring(0, maxChars);
    }

    static int promptChars(List<LlmMessage> messages) {
        return messages == null ? 0 : messages.stream().mapToInt(message -> message.content().length()).sum();
    }

    private static String truncate(String value, int maxChars) {
        String safe = value == null ? "" : value.replaceAll("\\s+", " ").strip();
        return safe.length() <= maxChars ? safe : safe.substring(0, maxChars);
    }
}
