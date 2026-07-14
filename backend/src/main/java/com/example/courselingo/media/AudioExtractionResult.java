package com.example.courselingo.media;

import java.nio.file.Path;

public record AudioExtractionResult(
    Path audioFile,
    String audioFormat,
    int sampleRate,
    int channels
) {
}
