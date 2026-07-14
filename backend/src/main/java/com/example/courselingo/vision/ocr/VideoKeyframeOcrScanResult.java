package com.example.courselingo.vision.ocr;

public record VideoKeyframeOcrScanResult(
    int saved,
    int succeeded,
    int empty,
    int failed,
    int skipped
) {
}
