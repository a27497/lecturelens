package com.example.courselingo.qa.service;

import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import com.example.courselingo.vision.ocr.OcrTextQualityEvaluator;
import java.util.List;
import java.util.Objects;
import org.springframework.stereotype.Component;

/** Source quality is decided once by CourseEvidence. Historical payloads remain readable without sample-specific rewriting. */
@Component
public class CourseQaEvidenceSanitizer {
    public List<CourseQaEvidenceItem> sanitize(List<CourseQaEvidenceItem> evidence) {
        return evidence == null ? List.of() : evidence.stream().map(this::sanitize).filter(Objects::nonNull).toList();
    }

    public CourseQaEvidenceItem sanitize(CourseQaEvidenceItem item) {
        if (item == null) return null;
        if (item.evidenceId() != null) return item;
        String snippet = normalize(item.snippet());
        String translated = normalize(item.translatedSnippet());
        if (snippet.isBlank() && translated.isBlank()) return null;
        if ("OCR".equals(item.sourceType()) && !OcrTextQualityEvaluator.isUseful(snippet, item.confidence())) return null;
        return new CourseQaEvidenceItem(item.sourceType(), item.sourceId(), item.startTimeMillis(), item.endTimeMillis(),
            item.timeText(), snippet, translated, item.confidence(), item.evidenceId(), item.revision());
    }

    private static String normalize(String value) { return value == null ? "" : value.replaceAll("\\s+", " ").strip(); }
}
