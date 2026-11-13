package com.example.courselingo.subtitle.dto;

import java.time.LocalDateTime;

public record TaskFullTextResultView(
    String taskId,
    String sourceLanguage,
    String targetLanguage,
    String sourceFullText,
    String translatedFullText,
    String provider,
    LocalDateTime createdAt,
    LocalDateTime updatedAt,
    java.util.List<AlignedParagraphView> alignedParagraphs
) {
    public TaskFullTextResultView {alignedParagraphs=alignedParagraphs==null?java.util.List.of():java.util.List.copyOf(alignedParagraphs);}
    public TaskFullTextResultView(String taskId,String sourceLanguage,String targetLanguage,String sourceFullText,
            String translatedFullText,String provider,LocalDateTime createdAt,LocalDateTime updatedAt) {
        this(taskId,sourceLanguage,targetLanguage,sourceFullText,translatedFullText,provider,createdAt,updatedAt,java.util.List.of());
    }
}
