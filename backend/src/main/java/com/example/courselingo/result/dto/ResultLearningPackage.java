package com.example.courselingo.result.dto;

import com.example.courselingo.learning.dto.GlossaryItem;
import com.example.courselingo.learning.dto.KeyPointItem;
import com.example.courselingo.learning.dto.QaItem;
import java.util.List;

public record ResultLearningPackage(
    String targetLanguage,
    String title,
    String summary,
    List<KeyPointItem> keyPoints,
    List<GlossaryItem> glossary,
    List<QaItem> qa
) {
}
