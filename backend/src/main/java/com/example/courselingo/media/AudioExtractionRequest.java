package com.example.courselingo.media;

import java.nio.file.Path;

public record AudioExtractionRequest(
    Path inputVideo,
    Path outputDirectory,
    String outputFileName
) {
}
