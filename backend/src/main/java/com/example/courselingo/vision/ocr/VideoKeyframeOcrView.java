package com.example.courselingo.vision.ocr;

public record VideoKeyframeOcrView(
    String status,
    String text,
    String provider,
    String languageHint,
    Double confidence,
    Boolean truncated,
    String message
) {
}
