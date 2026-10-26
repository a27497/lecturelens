package com.example.courselingo.qa.dto;

import java.time.LocalDateTime;
import java.util.List;

/** Public learner history: deliberately excludes model routing and execution metadata. */
public record CourseQaHistoryPage(List<Item> items, String nextCursor) {
    public record Item(String recordId, String question, String answer, String status,
                       LocalDateTime createdAt, List<CourseQaEvidenceItem> evidence, String sourceStatus) { }
}
