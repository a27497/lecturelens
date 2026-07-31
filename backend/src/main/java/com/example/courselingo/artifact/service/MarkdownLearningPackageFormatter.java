package com.example.courselingo.artifact.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.learning.dto.GlossaryItem;
import com.example.courselingo.learning.dto.KeyPointItem;
import com.example.courselingo.learning.dto.LearningPackageView;
import com.example.courselingo.learning.dto.QaItem;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Comparator;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class MarkdownLearningPackageFormatter {

    private static final TypeReference<List<KeyPointItem>> KEY_POINTS_TYPE = new TypeReference<>() {
    };
    private static final TypeReference<List<GlossaryItem>> GLOSSARY_TYPE = new TypeReference<>() {
    };
    private static final TypeReference<List<QaItem>> QA_TYPE = new TypeReference<>() {
    };

    private final ObjectMapper objectMapper;

    public MarkdownLearningPackageFormatter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public String format(LearningPackageView view) {
        return format(view, List.of(), false);
    }

    public String format(LearningPackageView view, List<ArtifactMultimodalTimelineItem> timeline) {
        return format(view, timeline, true);
    }

    private String format(
        LearningPackageView view,
        List<ArtifactMultimodalTimelineItem> timeline,
        boolean includeTimeline
    ) {
        if (view == null) {
            throw validationFailure("Markdown learning package is required");
        }
        String title = validateText(view.title(), "Markdown title is required");
        String summary = validateText(view.summary(), "Markdown summary is required");
        List<KeyPointItem> keyPoints = readJson(view.keyPointsJson(), KEY_POINTS_TYPE);
        List<GlossaryItem> glossary = readJson(view.glossaryJson(), GLOSSARY_TYPE);
        List<QaItem> qa = readJson(view.qaJson(), QA_TYPE);
        if (keyPoints.isEmpty()) {
            throw validationFailure("Markdown key points are required");
        }

        StringBuilder builder = new StringBuilder();
        builder.append("# ").append(title).append("\n\n")
            .append("## \u6458\u8981\n\n")
            .append(summary).append("\n\n")
            .append("## \u91cd\u70b9\n\n");

        int sequence = 1;
        for (KeyPointItem item : keyPoints.stream().sorted(Comparator.comparingInt(KeyPointItem::index)).toList()) {
            builder.append(sequence++)
                .append(". ")
                .append(validateText(item.text(), "Markdown key point text is required"))
                .append('\n');
        }

        builder.append("\n## \u672f\u8bed\u8868\n\n");
        if (glossary.isEmpty()) {
            builder.append("\u6682\u65e0\u672f\u8bed\n\n");
        } else {
            builder.append("| \u672f\u8bed | \u89e3\u91ca | \u8bd1\u540d |\n")
                .append("| --- | --- | --- |\n");
            for (GlossaryItem item : glossary) {
                OptionalGlossaryItem optionalItem = optionalGlossaryItem(item);
                if (optionalItem.isEmpty()) {
                    continue;
                }
                builder.append("| ")
                    .append(escapeTableCell(optionalItem.term()))
                    .append(" | ")
                    .append(escapeTableCell(optionalItem.definition()))
                    .append(" | ")
                    .append(escapeTableCell(optionalItem.translation()))
                    .append(" |\n");
            }
            builder.append('\n');
        }

        builder.append("## \u95ee\u7b54\n\n");
        if (qa.isEmpty()) {
            builder.append("\u6682\u65e0\u95ee\u7b54\n");
        } else {
            int questionNumber = 1;
            for (QaItem item : qa) {
                builder.append("### Q")
                    .append(questionNumber++)
                    .append(": ")
                    .append(validateText(item.question(), "Markdown question is required"))
                    .append("\n\n")
                    .append(validateText(item.answer(), "Markdown answer is required"))
                    .append('\n');
                if (questionNumber <= qa.size()) {
                    builder.append('\n');
                }
            }
        }
        if (includeTimeline) {
            appendTimeline(builder, timeline);
        }
        return builder.toString();
    }

    private void appendTimeline(StringBuilder builder, List<ArtifactMultimodalTimelineItem> timeline) {
        builder.append("\n## 多模态时间线\n\n");
        if (timeline == null || timeline.isEmpty()) {
            builder.append("- 暂无可用的多模态时间线证据（旧任务兼容）\n");
            return;
        }
        for (ArtifactMultimodalTimelineItem item : timeline) {
            if (item == null) {
                continue;
            }
            builder.append("- [")
                .append(sanitizedTimelineText(item.timeText()))
                .append("]");
            appendTimelineField(builder, "ASR", item.asrText());
            appendTimelineField(builder, "字幕译文", item.translatedText());
            appendTimelineField(builder, "OCR", item.ocrText());
            appendTimelineField(builder, "画面", item.visualSummary());
            appendTimelineField(builder, "融合摘要", item.fusedSummary());
            if (!item.keywords().isEmpty()) {
                appendTimelineField(builder, "关键词", String.join("、", item.keywords()));
            }
            if (!item.evidenceKeyframeIds().isEmpty()) {
                builder.append("；证据关键帧=").append(item.evidenceKeyframeIds());
            }
            if (item.confidence() != null && Double.isFinite(item.confidence())) {
                builder.append("；置信度=").append("%.4f".formatted(Math.max(0.0d, Math.min(item.confidence(), 1.0d))));
            }
            builder.append('\n');
        }
    }

    private void appendTimelineField(StringBuilder builder, String label, String value) {
        String normalized = sanitizedTimelineText(value);
        if (!normalized.isBlank()) {
            builder.append("；").append(label).append('=').append(normalized);
        }
    }

    private String sanitizedTimelineText(String value) {
        return ArtifactSensitiveDataValidator.redactSensitiveData(normalizeText(value));
    }

    private <T> List<T> readJson(String json, TypeReference<List<T>> typeReference) {
        if (json == null || json.isBlank()) {
            throw validationFailure("Markdown learning package content is invalid");
        }
        try {
            List<T> items = objectMapper.readValue(json, typeReference);
            return items == null ? List.of() : items;
        } catch (JsonProcessingException ex) {
            throw validationFailure("Markdown learning package content is invalid");
        }
    }

    private String validateText(String value, String requiredMessage) {
        String normalized = normalizeText(value);
        if (normalized.isBlank()) {
            throw validationFailure(requiredMessage);
        }
        if (ArtifactSensitiveDataValidator.containsSensitiveData(normalized)) {
            throw validationFailure("Markdown learning package content is invalid");
        }
        return normalized;
    }

    private OptionalGlossaryItem optionalGlossaryItem(GlossaryItem item) {
        if (item == null) {
            return OptionalGlossaryItem.empty();
        }
        String term = optionalText(item.term(), "Markdown glossary content is invalid");
        String definition = optionalText(item.definition(), "Markdown glossary content is invalid");
        String translation = optionalText(item.translation(), "Markdown glossary content is invalid");
        if (term.isBlank() && definition.isBlank() && translation.isBlank()) {
            return OptionalGlossaryItem.empty();
        }
        return new OptionalGlossaryItem(term, definition, translation);
    }

    private String optionalText(String value, String invalidMessage) {
        String normalized = normalizeText(value);
        if (!normalized.isBlank() && ArtifactSensitiveDataValidator.containsSensitiveData(normalized)) {
            throw validationFailure(invalidMessage);
        }
        return normalized;
    }

    private String normalizeText(String value) {
        if (value == null) {
            return "";
        }
        StringBuilder builder = new StringBuilder();
        boolean previousSpace = false;
        for (int i = 0; i < value.length(); i++) {
            char current = value.charAt(i);
            boolean asSpace = Character.isWhitespace(current) || Character.isISOControl(current);
            if (asSpace) {
                if (!previousSpace) {
                    builder.append(' ');
                    previousSpace = true;
                }
            } else {
                builder.append(current);
                previousSpace = false;
            }
        }
        return builder.toString().trim();
    }

    private String escapeTableCell(String value) {
        return value.replace("|", "\\|");
    }

    private BusinessException validationFailure(String message) {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, message);
    }

    private record OptionalGlossaryItem(String term, String definition, String translation) {

        private static OptionalGlossaryItem empty() {
            return new OptionalGlossaryItem("", "", "");
        }

        private boolean isEmpty() {
            return term.isBlank() && definition.isBlank() && translation.isBlank();
        }
    }
}
