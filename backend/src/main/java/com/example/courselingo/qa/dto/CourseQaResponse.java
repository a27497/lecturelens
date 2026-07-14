package com.example.courselingo.qa.dto;

import java.util.List;

public record CourseQaResponse(
    String recordId,
    String answer,
    List<CourseQaEvidenceItem> evidence,
    CourseQaUsage usage
) {

    public CourseQaResponse {
        evidence = evidence == null ? List.of() : List.copyOf(evidence);
    }
}
