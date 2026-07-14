package com.example.courselingo.vision.ocr;

public record OcrResult(
    OcrStatus status,
    String text,
    Double confidence,
    String provider,
    String languageHint,
    Long durationMillis,
    String errorCode,
    String errorMessage
) {

    public static OcrResult empty(String provider, String languageHint, Long durationMillis) {
        return new OcrResult(OcrStatus.EMPTY, "", null, provider, languageHint, durationMillis, null, null);
    }
}
