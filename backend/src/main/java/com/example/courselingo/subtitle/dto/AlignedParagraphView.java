package com.example.courselingo.subtitle.dto;

import java.util.List;

/** Seconds cover the stored interval; provenance describes its precision and origin. */
public record AlignedParagraphView(String id,int paragraphIndex,long startMillis,long endMillis,
    long startSeconds,long endSeconds,String sourceText,String translatedText,
    List<Integer> sourceSegmentIndexes,List<String> timingSources,String shortReason) {
    public AlignedParagraphView {
        sourceSegmentIndexes=List.copyOf(sourceSegmentIndexes);timingSources=List.copyOf(timingSources);
    }
}
