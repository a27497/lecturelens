package com.example.courselingo.qa.service;

import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class CourseQaEvidenceSanitizer {

    private static final String SEGMENT_ASR_PREFIX = "\u672c\u6bb5\u4e3b\u8981\u8bb2\u89e3\uff1a";
    private static final String COURSE_QA_ASR_PREFIX = "\u672c\u6bb5\u8bed\u97f3\u539f\u6587\uff1a";
    private static final String SEGMENT_OCR_PREFIX = "\u753b\u9762\u6587\u5b57\u5305\u62ec\uff1a";
    private static final String SEGMENT_DELIMITER = "\uff1b";
    private static final Pattern SEGMENT_SPLITTER = Pattern.compile("[\uff1b;\\r\\n]+");
    private static final Pattern CJK_PATTERN = Pattern.compile("[\\p{IsHan}]");
    private static final Pattern DIRTY_OCR_PATTERN = Pattern.compile(
        "(?i)(\\{emcee|\\bie\\s+ot\\b|call\\s+me\\s+h+m+a+a?l?i|\\bavd\\s+e\\s+8\\b|\\blas\\s+meh\\b|wate\\s+the\\s+ie\\s+es|\\uFFFD)"
    );

    public List<CourseQaEvidenceItem> sanitize(List<CourseQaEvidenceItem> evidence) {
        if (evidence == null || evidence.isEmpty()) {
            return List.of();
        }
        List<CourseQaEvidenceItem> sanitized = new ArrayList<>();
        for (CourseQaEvidenceItem item : evidence) {
            CourseQaEvidenceItem cleaned = sanitize(item);
            if (cleaned != null) {
                sanitized.add(cleaned);
            }
        }
        return List.copyOf(sanitized);
    }

    public CourseQaEvidenceItem sanitize(CourseQaEvidenceItem item) {
        if (item == null) {
            return null;
        }
        String snippet = sanitizeText(item.sourceType(), item.snippet(), item.confidence());
        String translatedSnippet = sanitizeText(item.sourceType(), item.translatedSnippet(), item.confidence());
        if (snippet.isBlank() && translatedSnippet.isBlank()) {
            return null;
        }
        return new CourseQaEvidenceItem(
            item.sourceType(),
            item.sourceId(),
            item.startTimeMillis(),
            item.endTimeMillis(),
            item.timeText(),
            snippet,
            translatedSnippet,
            item.confidence()
        );
    }

    private static String sanitizeText(String sourceType, String value, Double confidence) {
        String cleaned = cleanText(value);
        if (cleaned.isBlank()) {
            return "";
        }
        if ("OCR".equals(sourceType)) {
            return "";
        }
        List<String> parts = new ArrayList<>();
        for (String rawPart : SEGMENT_SPLITTER.split(cleaned)) {
            String part = cleanText(rawPart);
            if (part.isBlank()) {
                continue;
            }
            if (part.startsWith(SEGMENT_ASR_PREFIX)) {
                addMainOrVoicePart(parts, part.substring(SEGMENT_ASR_PREFIX.length()));
            } else if (part.startsWith(COURSE_QA_ASR_PREFIX)) {
                addVoicePart(parts, part.substring(COURSE_QA_ASR_PREFIX.length()));
            } else if (part.startsWith(SEGMENT_OCR_PREFIX)) {
                continue;
            } else if (containsDirtyOcr(part)) {
                String retained = removeDirtyTail(part);
                if (!retained.isBlank()) {
                    parts.add(retained);
                }
            } else {
                parts.add(part);
            }
        }
        return String.join(SEGMENT_DELIMITER, parts);
    }

    private static void addMainOrVoicePart(List<String> parts, String text) {
        String body = cleanText(text);
        if (body.isBlank()) {
            return;
        }
        parts.add(isMostlyNonChinese(body) ? COURSE_QA_ASR_PREFIX + body : SEGMENT_ASR_PREFIX + body);
    }

    private static void addVoicePart(List<String> parts, String text) {
        String body = cleanText(text);
        if (!body.isBlank()) {
            parts.add(COURSE_QA_ASR_PREFIX + body);
        }
    }

    private static boolean containsDirtyOcr(String value) {
        return DIRTY_OCR_PATTERN.matcher(value == null ? "" : value).find();
    }

    private static String removeDirtyTail(String value) {
        String cleaned = cleanText(value);
        var matcher = DIRTY_OCR_PATTERN.matcher(cleaned);
        if (!matcher.find()) {
            return cleaned;
        }
        return cleanText(cleaned.substring(0, matcher.start()));
    }

    private static boolean isMostlyNonChinese(String value) {
        String cleaned = cleanText(value);
        if (cleaned.isBlank()) {
            return true;
        }
        int cjkCount = 0;
        var matcher = CJK_PATTERN.matcher(cleaned);
        while (matcher.find()) {
            cjkCount++;
        }
        int textChars = 0;
        for (int i = 0; i < cleaned.length(); i++) {
            if (Character.isLetterOrDigit(cleaned.charAt(i))) {
                textChars++;
            }
        }
        return textChars == 0 || cjkCount / (double) textChars < 0.25d;
    }

    private static String cleanText(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").strip();
    }
}
