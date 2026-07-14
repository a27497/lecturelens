package com.example.courselingo.chapter.service;

import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import java.util.List;

public record CourseChapterEvidenceBundle(
    List<CourseChapterEvidenceItem> evidence,
    String globalContext
) {

    public CourseChapterEvidenceBundle {
        evidence = evidence == null ? List.of() : List.copyOf(evidence);
        globalContext = globalContext == null ? "" : globalContext;
    }
}
