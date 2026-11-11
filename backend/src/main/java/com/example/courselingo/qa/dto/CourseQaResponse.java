package com.example.courselingo.qa.dto;

import java.util.List;
import com.example.courselingo.evidence.LearningScope;

public record CourseQaResponse(
    String recordId,
    String answer,
    List<CourseQaEvidenceItem> evidence,
    CourseQaUsage usage,
    LearningScope learning_scope
) {

    public CourseQaResponse(String recordId, String answer, List<CourseQaEvidenceItem> evidence, CourseQaUsage usage) { this(recordId,answer,evidence,usage,null); }

    public CourseQaResponse {
        evidence = evidence == null ? List.of() : List.copyOf(evidence);
    }
}
