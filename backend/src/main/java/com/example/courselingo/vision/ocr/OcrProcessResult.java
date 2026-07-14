package com.example.courselingo.vision.ocr;

record OcrProcessResult(
    int exitCode,
    String stdout,
    String stderr,
    boolean timedOut
) {
}
